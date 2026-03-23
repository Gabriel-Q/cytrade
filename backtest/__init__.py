"""回测模块。

这个包承接第一阶段回测能力，目标是：
1. 用历史数据回放替代实时订阅。
2. 用模拟成交替代真实柜台成交。
3. 复用现有策略、订单、持仓链路。
4. 输出基础绩效指标和 HTML 报告。
"""

from .models import BacktestBar, BacktestBatch, BacktestConfig, BacktestResult, ClosedTrade, DailyReturnPoint, EquityPoint
from .data_feed import BacktestDataFeed
from .executor import BacktestTradeExecutor
from .tracker import BacktestTracker
from .report import BacktestReportBuilder
from .engine import BacktestEngine

__all__ = [
    "BacktestBar",
    "BacktestBatch",
    "BacktestConfig",
    "BacktestDataFeed",
    "BacktestEngine",
    "BacktestReportBuilder",
    "BacktestResult",
    "BacktestTradeExecutor",
    "BacktestTracker",
    "ClosedTrade",
    "DailyReturnPoint",
    "EquityPoint",
]