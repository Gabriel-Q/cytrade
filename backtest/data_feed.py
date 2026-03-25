"""回测数据回放器。

这个模块负责：
1. 预加载历史分钟数据或 tick 数据。
2. 按时间顺序整理为 BacktestBatch。
3. 以与实时订阅相近的方式向上游提供 TickData 批次。
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable, Iterator
from datetime import datetime, time
from typing import Dict, List, Optional

import pandas as pd

from backtest.models import BacktestBar, BacktestBatch, BacktestConfig
from core.history_data import HistoryDataManager
from monitor.logger import get_logger

logger = get_logger("system")


class BacktestDataFeed:
    """历史数据回放器。

    第一阶段支持两种回放粒度：
    1. ``1m``: 用分钟 OHLCV 构造“分钟级模拟 tick”。
    2. ``tick``: 直接用历史 tick 构造真实 tick 回放，同时保留用于撮合的逐笔价格快照。
    """

    def __init__(self, config: BacktestConfig, history_manager: Optional[HistoryDataManager] = None):
        self._config = config
        self._history_manager = history_manager or HistoryDataManager()
        self._data_callback: Optional[Callable[[Dict[str, object]], None]] = None
        self._batches: List[BacktestBatch] = []
        self._loaded = False
        self._running = False

    def set_data_callback(self, callback: Callable[[Dict[str, object]], None]) -> None:
        """保留与实时订阅器相似的回调接口。"""
        self._data_callback = callback

    def load_data(self) -> List[BacktestBatch]:
        """加载并整理历史数据。

        实现阶段需要完成：
        1. 拉取分钟数据。
        2. 标准化时间列和 OHLCV 列。
        3. 生成按时间聚合的 BacktestBatch 列表。
        """
        if self._loaded:
            return list(self._batches)

        field_list = self._field_list_for_period(self._config.period)
        raw_frames = self._history_manager.get_history_data(
            stock_list=self._config.stock_codes,
            start_date=self._config.start_date,
            end_date=self._config.end_date,
            period=self._config.period,
            dividend_type="none" if self._config.period == "tick" else "front",
            field_list=field_list,
            fill_data=False,
            show_progress=False,
        )

        by_time: dict[datetime, dict[str, BacktestBar]] = defaultdict(dict)
        for stock_code, frame in raw_frames.items():
            prepared = self._prepare_frame(stock_code, frame, self._config.period)
            if prepared.empty:
                continue

            for row in prepared.to_dict("records"):
                bar = BacktestBar(
                    stock_code=stock_code,
                    data_time=row["data_time"],
                    trade_day=row["trade_day"],
                    open_price=float(row["open"]),
                    high_price=float(row["high"]),
                    low_price=float(row["low"]),
                    close_price=float(row["close"]),
                    volume=int(row["volume"]),
                    amount=float(row["amount"]),
                    pre_close=float(row["pre_close"]),
                    day_open=float(row["day_open"]),
                    day_high=float(row["day_high"]),
                    day_low=float(row["day_low"]),
                    cumulative_volume=int(row["cumulative_volume"]),
                    cumulative_amount=float(row["cumulative_amount"]),
                    bid_prices=list(row.get("bid_prices", []) or []),
                    bid_volumes=list(row.get("bid_volumes", []) or []),
                    ask_prices=list(row.get("ask_prices", []) or []),
                    ask_volumes=list(row.get("ask_volumes", []) or []),
                )
                by_time[bar.data_time][stock_code] = bar

        self._batches = []
        for data_time in sorted(by_time.keys()):
            bars = by_time[data_time]
            ticks = {code: bar.to_tick() for code, bar in bars.items()}
            self._batches.append(BacktestBatch(data_time=data_time, ticks=ticks, bars=bars))

        self._loaded = True
        logger.info("BacktestDataFeed: 已加载 %d 个批次，%d 只股票",
                    len(self._batches), len(self._config.stock_codes))
        return list(self._batches)

    def iter_batches(self) -> Iterator[BacktestBatch]:
        """按时间顺序遍历批次。"""
        if not self._loaded:
            self.load_data()
        yield from self._batches

    def run(self) -> None:
        """按回调方式顺序推送批次。"""
        if not self._loaded:
            self.load_data()
        self._running = True
        for batch in self._batches:
            if not self._running:
                break
            if self._data_callback:
                self._data_callback(batch.ticks)

    def stop(self) -> None:
        """停止回放。"""
        self._running = False

    @staticmethod
    def _prepare_frame(stock_code: str, frame: pd.DataFrame, period: str) -> pd.DataFrame:
        """把原始历史数据标准化为回放所需结构。"""
        if str(period).lower() == "tick":
            return BacktestDataFeed._prepare_tick_frame(stock_code, frame)
        return BacktestDataFeed._prepare_bar_frame(stock_code, frame)

    @staticmethod
    def _prepare_bar_frame(stock_code: str, frame: pd.DataFrame) -> pd.DataFrame:
        """把原始分钟数据标准化为分钟级回放结构。"""
        if frame is None or frame.empty:
            return pd.DataFrame()

        df = frame.copy()
        if "time" in df.columns:
            raw_time = df["time"]
        elif "trade_time" in df.columns:
            raw_time = df["trade_time"]
        elif "date" in df.columns:
            raw_time = df["date"]
        else:
            raw_time = pd.Series(df.index, index=df.index)

        df["data_time"] = raw_time.map(BacktestDataFeed._to_datetime)
        for column in ("open", "high", "low", "close", "volume", "amount"):
            if column not in df.columns:
                df[column] = 0.0
            df[column] = pd.to_numeric(df[column], errors="coerce").fillna(0.0)

        df = df[df["data_time"].notna()].copy()
        if df.empty:
            return df

        df = df.sort_values("data_time").reset_index(drop=True)
        df["trade_day"] = df["data_time"].dt.strftime("%Y%m%d")
        df["day_open"] = df.groupby("trade_day")["open"].transform("first")
        df["day_high"] = df.groupby("trade_day")["high"].cummax()
        df["day_low"] = df.groupby("trade_day")["low"].cummin()
        df["cumulative_volume"] = df.groupby("trade_day")["volume"].cumsum()
        if (df["amount"] <= 0).all():
            df["amount"] = df["close"] * df["volume"]
        df["cumulative_amount"] = df.groupby("trade_day")["amount"].cumsum()

        daily_close = df.groupby("trade_day")["close"].last()
        prev_close_map = daily_close.shift(1).to_dict()
        df["pre_close"] = df["trade_day"].map(prev_close_map).fillna(df["day_open"])
        df["stock_code"] = stock_code
        df["bid_prices"] = [[] for _ in range(len(df))]
        df["bid_volumes"] = [[] for _ in range(len(df))]
        df["ask_prices"] = [[] for _ in range(len(df))]
        df["ask_volumes"] = [[] for _ in range(len(df))]
        return df

    @staticmethod
    def _prepare_tick_frame(stock_code: str, frame: pd.DataFrame) -> pd.DataFrame:
        """把原始 tick 数据标准化为逐笔回放结构。

        这里区分两套口径：
        1. 给策略的 ``TickData``: 使用 tick 自带的日内 open/high/low/volume/amount。
        2. 给撮合器的 ``BacktestBar``: 使用当前逐笔成交价作为 open/high/low/close，
           避免把“日内最高/最低价”误当成当前这一笔就能成交的价格区间。
        """
        if frame is None or frame.empty:
            return pd.DataFrame()

        df = frame.copy()
        if "time" in df.columns:
            raw_time = df["time"]
        elif "trade_time" in df.columns:
            raw_time = df["trade_time"]
        elif "date" in df.columns:
            raw_time = df["date"]
        else:
            raw_time = pd.Series(df.index, index=df.index)

        df["data_time"] = raw_time.map(BacktestDataFeed._to_datetime)
        tick_price_col = "lastPrice" if "lastPrice" in df.columns else ("last_price" if "last_price" in df.columns else "close")
        pre_close_col = "lastClose" if "lastClose" in df.columns else ("preClose" if "preClose" in df.columns else "pre_close")

        df["last_price"] = pd.to_numeric(df.get(tick_price_col, 0.0), errors="coerce").fillna(0.0)
        df["tick_open"] = pd.to_numeric(df.get("open", df["last_price"]), errors="coerce").fillna(df["last_price"])
        df["tick_high"] = pd.to_numeric(df.get("high", df["last_price"]), errors="coerce").fillna(df["last_price"])
        df["tick_low"] = pd.to_numeric(df.get("low", df["last_price"]), errors="coerce").fillna(df["last_price"])
        df["pre_close"] = pd.to_numeric(df.get(pre_close_col, df["tick_open"]), errors="coerce").fillna(df["tick_open"])
        df["cumulative_volume"] = pd.to_numeric(df.get("volume", 0.0), errors="coerce").fillna(0.0).astype(int)
        df["cumulative_amount"] = pd.to_numeric(df.get("amount", 0.0), errors="coerce").fillna(0.0)

        df = df[df["data_time"].notna()].copy()
        if df.empty:
            return df

        df = df.sort_values("data_time").reset_index(drop=True)
        df = df[df["data_time"].map(BacktestDataFeed._is_regular_trading_time)].copy()
        if df.empty:
            return df

        bid1 = df.apply(lambda row: BacktestDataFeed._first_level_value(row, "bidPrice"), axis=1)
        ask1 = df.apply(lambda row: BacktestDataFeed._first_level_value(row, "askPrice"), axis=1)
        effective_price = pd.Series(
            [BacktestDataFeed._first_positive(value_list) for value_list in zip(df["last_price"], ask1, bid1, df["pre_close"])],
            index=df.index,
        )
        effective_open = pd.Series(
            [BacktestDataFeed._first_positive(value_list) for value_list in zip(df["tick_open"], effective_price, ask1, bid1, df["pre_close"])],
            index=df.index,
        )
        effective_high = pd.Series(
            [BacktestDataFeed._first_positive(value_list) for value_list in zip(df["tick_high"], effective_price, effective_open)],
            index=df.index,
        )
        effective_low = pd.Series(
            [BacktestDataFeed._first_positive(value_list) for value_list in zip(df["tick_low"], effective_price, effective_open)],
            index=df.index,
        )
        df["last_price"] = effective_price.fillna(0.0)
        df["tick_open"] = effective_open.fillna(df["last_price"])
        df["tick_high"] = effective_high.fillna(df["last_price"])
        df["tick_low"] = effective_low.fillna(df["last_price"])
        df = df[df["last_price"] > 0].copy()
        if df.empty:
            return df

        df["trade_day"] = df["data_time"].dt.strftime("%Y%m%d")
        df["open"] = df["last_price"]
        df["high"] = df["last_price"]
        df["low"] = df["last_price"]
        df["close"] = df["last_price"]
        df["volume"] = 0
        df["amount"] = 0.0
        df["day_open"] = df["tick_open"]
        df["day_high"] = df["tick_high"]
        df["day_low"] = df["tick_low"]
        df["stock_code"] = stock_code
        df["bid_prices"] = df.apply(lambda row: BacktestDataFeed._extract_level_values(row, "bidPrice", 5), axis=1)
        df["bid_volumes"] = df.apply(lambda row: BacktestDataFeed._extract_level_values(row, "bidVol", 5, cast_int=True), axis=1)
        df["ask_prices"] = df.apply(lambda row: BacktestDataFeed._extract_level_values(row, "askPrice", 5), axis=1)
        df["ask_volumes"] = df.apply(lambda row: BacktestDataFeed._extract_level_values(row, "askVol", 5, cast_int=True), axis=1)
        return df

    @staticmethod
    def _field_list_for_period(period: str) -> List[str]:
        """根据周期选择更贴近原始数据结构的字段列表。"""
        if str(period).lower() == "tick":
            return [
                "time", "lastPrice", "open", "high", "low", "lastClose", "volume", "amount",
                "bidPrice", "bidVol", "askPrice", "askVol",
            ]
        return ["time", "open", "high", "low", "close", "volume", "amount"]

    @staticmethod
    def _extract_level_values(row: pd.Series, base_name: str, level_count: int, cast_int: bool = False) -> list:
        """从可能存在的盘口列中抽取买卖五档。

        兼容两种常见格式：
        1. 单列数组形式，例如 ``bidPrice`` / ``askPrice``。
        2. 展开列形式，例如 ``bidPrice1`` ... ``bidPrice5``。
        """
        direct = row.get(base_name)
        if isinstance(direct, (list, tuple)):
            values = list(direct)[:level_count]
        else:
            values = []
            for index in range(1, level_count + 1):
                value = row.get(f"{base_name}{index}")
                if value is None or (isinstance(value, float) and pd.isna(value)):
                    continue
                values.append(value)
        if cast_int:
            return [int(float(value)) for value in values]
        return [float(value) for value in values]

    @staticmethod
    def _first_level_value(row: pd.Series, base_name: str) -> float:
        """取盘口一档价格，兼容数组列和展开列两种形式。"""
        values = BacktestDataFeed._extract_level_values(row, base_name, 1)
        return float(values[0]) if values else 0.0

    @staticmethod
    def _first_positive(values) -> float:
        """从候选价格中选出第一个正数，作为当前 tick 的有效价格。"""
        for value in values:
            try:
                numeric = float(value)
            except (TypeError, ValueError):
                continue
            if numeric > 0:
                return numeric
        return 0.0

    @staticmethod
    def _is_regular_trading_time(value: datetime) -> bool:
        """过滤掉盘前集合竞价和午间休市时段，只保留连续交易时段。"""
        if not isinstance(value, datetime):
            return False
        current_time = value.time()
        morning_open = time(9, 30)
        morning_close = time(11, 30)
        afternoon_open = time(13, 0)
        afternoon_close = time(15, 0)
        return (morning_open <= current_time <= morning_close) or (afternoon_open <= current_time <= afternoon_close)

    @staticmethod
    def _to_datetime(value) -> datetime | pd.NaT:
        """尽量宽松地把多种时间表示转换为 datetime。"""
        if value is None or value == "":
            return pd.NaT
        if isinstance(value, pd.Timestamp):
            return value.to_pydatetime()
        if isinstance(value, datetime):
            return value
        if isinstance(value, (int, float)):
            integer_value = int(value)
            text = str(integer_value)
            if len(text) >= 14:
                try:
                    return datetime.strptime(text[:14], "%Y%m%d%H%M%S")
                except ValueError:
                    pass
            if integer_value > 10**12:
                return datetime.fromtimestamp(integer_value / 1000.0)
            if integer_value > 10**9:
                return datetime.fromtimestamp(integer_value)
        try:
            return pd.to_datetime(value).to_pydatetime()
        except Exception:
            return pd.NaT
