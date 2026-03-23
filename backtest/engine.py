"""回测引擎。

这个模块负责把数据回放、策略运行、模拟撮合、持仓更新、结果追踪串起来。
第一阶段引擎采用单进程、单线程、按时间顺序逐批执行。
"""

from __future__ import annotations

from typing import Iterable, Optional, Type

from backtest.data_feed import BacktestDataFeed
from backtest.models import BacktestConfig, BacktestResult
from backtest.report import BacktestReportBuilder
from backtest.tracker import BacktestTracker
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
        self._data_feed.load_data()

        for batch in self._data_feed.iter_batches():
            self._trade_executor.update_clock(batch.data_time)
            self._trade_executor.process_batch(batch.bars)
            self._runner.on_market_data(batch.ticks)
            self._tracker.capture_equity(
                data_time=batch.data_time,
                cash=self._trade_executor.cash,
                market_value=self._current_market_value(),
            )

        self._trade_executor.expire_all_orders()
        snapshots = [strategy.get_snapshot() for strategy in self._runner.get_all_strategies()]
        result = self._tracker.build_result(strategy_snapshots=snapshots)
        return result

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