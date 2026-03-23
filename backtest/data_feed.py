"""回测数据回放器。

这个模块负责：
1. 预加载历史分钟数据。
2. 按时间顺序整理为 BacktestBatch。
3. 以与实时订阅相近的方式向上游提供 TickData 批次。
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable, Iterator
from datetime import datetime
from typing import Dict, List, Optional

import pandas as pd

from backtest.models import BacktestBar, BacktestBatch, BacktestConfig
from core.history_data import HistoryDataManager
from monitor.logger import get_logger

logger = get_logger("system")


class BacktestDataFeed:
    """历史数据回放器。

    第一阶段只支持 1 分钟回放。
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

        raw_frames = self._history_manager.get_history_data(
            stock_list=self._config.stock_codes,
            start_date=self._config.start_date,
            end_date=self._config.end_date,
            period=self._config.period,
            dividend_type="front",
            field_list=["time", "open", "high", "low", "close", "volume", "amount"],
            fill_data=False,
            show_progress=False,
        )

        by_time: dict[datetime, dict[str, BacktestBar]] = defaultdict(dict)
        for stock_code, frame in raw_frames.items():
            prepared = self._prepare_frame(stock_code, frame)
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
    def _prepare_frame(stock_code: str, frame: pd.DataFrame) -> pd.DataFrame:
        """把原始分钟数据标准化为回放所需结构。"""
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
        return df

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
