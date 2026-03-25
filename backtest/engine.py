"""回测引擎。

这个模块负责把数据回放、策略运行、模拟撮合、持仓更新、结果追踪串起来。
第一阶段引擎采用单进程、单线程、按时间顺序逐批执行。
"""

from __future__ import annotations

from typing import Iterable, Optional, Type

import pandas as pd

from backtest.data_feed import BacktestDataFeed
from backtest.models import BacktestConfig, BacktestResult
from backtest.report import BacktestReportBuilder
from backtest.tracker import BacktestTracker
from core.history_data import HistoryDataManager
from config.enums import StrategyStatus
from monitor.logger import get_logger
from strategy.base import BaseStrategy
from strategy.models import StrategyConfig

logger = get_logger("system")


class BacktestEngine:
    """回测主引擎。"""

    def __init__(self, config: BacktestConfig, data_feed: BacktestDataFeed,
                 trade_executor, order_manager, position_manager, runner,
                 tracker: Optional[BacktestTracker] = None,
                 report_builder: Optional[BacktestReportBuilder] = None):
        self._config = config
        self._data_feed = data_feed
        self._trade_executor = trade_executor
        self._order_manager = order_manager
        self._position_manager = position_manager
        self._runner = runner
        self._tracker = tracker or BacktestTracker(config)
        self._report_builder = report_builder or BacktestReportBuilder()

        self._order_manager.set_position_callback(self._position_manager.on_trade_callback)
        self._order_manager.set_strategy_callback(self._dispatch_order_update)
        self._order_manager.set_trade_callback(self._tracker.on_trade)
        self._history_manager = HistoryDataManager()

    def load_strategy_classes(self, strategy_classes: Iterable[Type[BaseStrategy]]) -> None:
        """按策略类创建并装载策略实例。"""
        for strategy_class in strategy_classes:
            selector = strategy_class(StrategyConfig(), self._trade_executor, self._position_manager)
            for config in selector.select_stocks():
                strategy = strategy_class(config, self._trade_executor, self._position_manager)
                self._runner.add_strategy(strategy)

        for strategy in self._runner.get_all_strategies():
            if strategy.status == StrategyStatus.INITIALIZING:
                strategy.start()

    def run(self) -> BacktestResult:
        """执行一轮完整回测。

        运行顺序要求：
        1. 先加载历史批次。
        2. 每个时间点先撮合上一轮挂单。
        3. 再把当前批次行情喂给 StrategyRunner。
        4. 最后记录净值点。
        """
        self._runner._running = True
        batches = self._data_feed.load_data()
        daily_close_map = self._load_portfolio_close_series()
        current_trade_day = ""
        last_batch = None
        total_batches = len(batches)

        for index, batch in enumerate(self._data_feed.iter_batches(), start=1):
            last_batch = batch
            batch_trade_day = self._batch_trade_day(batch)
            if current_trade_day and batch_trade_day and batch_trade_day != current_trade_day:
                self._config.daily_close_equity_series[current_trade_day] = self._compute_daily_close_equity(current_trade_day, daily_close_map)
            if batch_trade_day:
                current_trade_day = batch_trade_day
            self._trade_executor.update_clock(batch.data_time)
            self._trade_executor.process_batch(batch.bars)
            self._runner.on_market_data(batch.ticks)
            position_summary = self._position_manager.get_position_summary()
            self._tracker.capture_equity_with_cost(
                data_time=batch.data_time,
                cash=self._trade_executor.cash,
                market_value=self._current_market_value(),
                invested_capital=float(position_summary.get("total_cost", 0.0) or 0.0),
            )

            if total_batches > 0 and (index == 1 or index % 10000 == 0 or index == total_batches):
                logger.info(
                    "BacktestEngine: 已处理 %d/%d 批次 (%.1f%%) trade_day=%s cash=%.2f market=%.2f",
                    index,
                    total_batches,
                    index * 100.0 / total_batches,
                    batch_trade_day or "-",
                    self._trade_executor.cash,
                    self._current_market_value(),
                )

        if current_trade_day:
            self._config.daily_close_equity_series[current_trade_day] = self._compute_daily_close_equity(current_trade_day, daily_close_map)

        if self._config.force_close_on_end_day and last_batch is not None:
            self._trade_executor.update_clock(last_batch.data_time)
            self._trade_executor.force_close_positions(last_batch.bars)
            position_summary = self._position_manager.get_position_summary()
            self._tracker.capture_equity_with_cost(
                data_time=last_batch.data_time,
                cash=self._trade_executor.cash,
                market_value=self._current_market_value(),
                invested_capital=float(position_summary.get("total_cost", 0.0) or 0.0),
            )
            final_trade_day = self._batch_trade_day(last_batch)
            if final_trade_day and final_trade_day not in self._config.daily_close_equity_series:
                self._config.daily_close_equity_series[final_trade_day] = self._compute_daily_close_equity(final_trade_day, daily_close_map)

        self._trade_executor.expire_all_orders()
        self._config.benchmark_daily_returns = self._load_benchmark_close_series()
        snapshots = [strategy.get_snapshot() for strategy in self._runner.get_all_strategies()]
        result = self._tracker.build_result(strategy_snapshots=snapshots)
        return result

    def _load_benchmark_close_series(self) -> dict[str, float]:
        """读取基准日线收盘序列，并按交易日映射。"""
        benchmark_code = str(getattr(self._config, "benchmark_code", "") or "").strip()
        if not benchmark_code:
            benchmark_code = "510050.SH"

        frames = self._history_manager.get_history_data(
            stock_list=[benchmark_code],
            start_date=self._config.start_date,
            end_date=self._config.end_date,
            period="1d",
            dividend_type="none",
            field_list=["time", "close"],
            fill_data=False,
            show_progress=False,
        )
        normalized_key = self._history_manager.xt_code_to_stock(self._history_manager.stock_code_to_xt(benchmark_code))
        frame = frames.get(normalized_key)
        if frame is None:
            frame = next(iter(frames.values()), None)
        if frame is None or frame.empty:
            return {}

        df = frame.copy()
        if "time" in df.columns:
            raw_time = df["time"]
        elif "trade_time" in df.columns:
            raw_time = df["trade_time"]
        elif "date" in df.columns:
            raw_time = df["date"]
        else:
            raw_time = df.index
        df["trade_day"] = raw_time.map(self._normalize_trade_day_value)
        df["close"] = df.get("close", 0.0)
        df["close"] = df["close"].astype(float)
        df = df[df["trade_day"].astype(bool)].drop_duplicates(subset=["trade_day"], keep="last")
        return {str(row["trade_day"]): float(row["close"]) for _, row in df.iterrows() if float(row["close"]) > 0}

    def _load_portfolio_close_series(self) -> dict[str, dict[str, float]]:
        """读取组合标的的日线收盘价，用于按日末总资产重建逐日收益。"""
        stock_codes = [code for code in self._config.stock_codes if str(code).strip()]
        if not stock_codes:
            return {}

        frames = self._history_manager.get_history_data(
            stock_list=stock_codes,
            start_date=self._config.start_date,
            end_date=self._config.end_date,
            period="1d",
            dividend_type="none",
            field_list=["time", "close"],
            fill_data=False,
            show_progress=False,
        )

        close_map: dict[str, dict[str, float]] = {}
        for stock_code in stock_codes:
            normalized_key = self._history_manager.xt_code_to_stock(self._history_manager.stock_code_to_xt(stock_code))
            frame = frames.get(normalized_key)
            if frame is None:
                frame = frames.get(stock_code)
            if frame is None or frame.empty:
                continue

            df = frame.copy()
            raw_time = df["time"] if "time" in df.columns else (df["trade_time"] if "trade_time" in df.columns else (df["date"] if "date" in df.columns else df.index))
            df["trade_day"] = raw_time.map(self._normalize_trade_day_value)
            df["close"] = df.get("close", 0.0)
            df["close"] = df["close"].astype(float)
            df = df[df["trade_day"].astype(bool)].drop_duplicates(subset=["trade_day"], keep="last")
            for _, row in df.iterrows():
                trade_day = str(row["trade_day"])
                close_value = float(row["close"] or 0.0)
                if close_value <= 0:
                    continue
                close_map.setdefault(trade_day, {})[stock_code] = close_value
        return close_map

    @staticmethod
    def _batch_trade_day(batch) -> str:
        """从批次中提取交易日。"""
        if not batch.bars:
            return ""
        return next(iter(batch.bars.values())).trade_day

    def _compute_daily_close_equity(self, trade_day: str, daily_close_map: dict[str, dict[str, float]]) -> float:
        """按日 K 收盘价计算当日总资产。"""
        close_prices = daily_close_map.get(trade_day, {})
        positions = self._position_manager.get_all_positions()
        market_value = 0.0
        for position in positions.values():
            quantity = int(getattr(position, "total_quantity", 0) or 0)
            stock_code = str(getattr(position, "stock_code", "") or "")
            if quantity <= 0 or not stock_code:
                continue
            close_price = float(close_prices.get(stock_code, getattr(position, "current_price", 0.0) or 0.0) or 0.0)
            market_value += quantity * close_price
        return float(self._trade_executor.cash) + market_value

    @staticmethod
    def _normalize_trade_day_value(value) -> str:
        """把各种时间格式统一转换成 YYYYMMDD。"""
        if value is None:
            return ""

        if hasattr(value, "strftime"):
            try:
                return value.strftime("%Y%m%d")
            except Exception:
                pass

        if isinstance(value, (int, float)):
            numeric_value = int(value)
            if numeric_value <= 0:
                return ""
            if numeric_value >= 10**14:
                timestamp = pd.to_datetime(numeric_value)
                return timestamp.strftime("%Y%m%d")
            if numeric_value >= 10**12:
                timestamp = pd.to_datetime(numeric_value, unit="ms")
                return timestamp.strftime("%Y%m%d")
            if numeric_value >= 10**9:
                timestamp = pd.to_datetime(numeric_value, unit="s")
                return timestamp.strftime("%Y%m%d")
            text = str(numeric_value)
            if len(text) == 8:
                return text

        text = str(value).strip()
        if not text:
            return ""

        digits = "".join(ch for ch in text if ch.isdigit())
        if len(digits) >= 8 and digits[:4] in {"19", "20"}:
            return digits[:8]

        try:
            timestamp = pd.to_datetime(value)
        except Exception:
            return ""
        if pd.isna(timestamp):
            return ""
        return timestamp.strftime("%Y%m%d")

    def write_report(self, result: BacktestResult):
        """输出回测 HTML 报告。"""
        return self._report_builder.write(result, self._config.report_path)

    def _dispatch_order_update(self, order) -> None:
        """同时通知追踪器和策略对象。"""
        self._tracker.on_order(order)
        self._runner.dispatch_order_update(order)

    def _current_market_value(self) -> float:
        positions = self._position_manager.get_all_positions()
        return sum(float(position.market_value or 0.0) for position in positions.values())