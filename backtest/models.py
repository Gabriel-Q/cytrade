"""回测共享数据模型。

第一阶段回测需要两类核心对象：
1. 回放时使用的分钟级 bar / 批次对象。
2. 回测完成后输出的净值点与结果对象。

这些对象只描述数据结构，不包含业务流程。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List

from core.models import TickData
from strategy.models import StrategySnapshot


@dataclass
class BacktestConfig:
    """回测配置。

    第一阶段只覆盖最小可用参数：
    - 标的列表
    - 起止日期
    - 数据周期
    - 初始资金
    - 滑点
    - 报告输出路径
    """

    stock_codes: List[str] = field(default_factory=list)
    start_date: str = ""
    end_date: str = ""
    period: str = "1m"
    initial_cash: float = 1_000_000.0
    slippage: float = 0.01
    report_path: str = "backtest_report.html"


@dataclass
class BacktestBar:
    """回测内部使用的分钟级 bar。

    这个对象保留两套信息：
    1. 当前分钟 bar 自身的 OHLCV。
    2. 为模拟实时行情准备的“日内累计视角”字段。
    """

    stock_code: str = ""
    data_time: datetime = field(default_factory=datetime.now)
    trade_day: str = ""
    open_price: float = 0.0
    high_price: float = 0.0
    low_price: float = 0.0
    close_price: float = 0.0
    volume: int = 0
    amount: float = 0.0
    pre_close: float = 0.0
    day_open: float = 0.0
    day_high: float = 0.0
    day_low: float = 0.0
    cumulative_volume: int = 0
    cumulative_amount: float = 0.0

    def to_tick(self) -> TickData:
        """把分钟级 bar 转成策略可消费的 TickData。

        第一阶段用“分钟级模拟 tick”驱动策略：
        - last_price 用当前分钟收盘价
        - open/high/low 用当日视角字段
        - volume/amount 用日内累计字段
        """
        return TickData(
            stock_code=self.stock_code,
            last_price=float(self.close_price),
            open=float(self.day_open),
            high=float(self.day_high),
            low=float(self.day_low),
            pre_close=float(self.pre_close),
            volume=int(self.cumulative_volume),
            amount=float(self.cumulative_amount),
            data_time=self.data_time,
            recv_time=self.data_time,
            latency_ms=0.0,
        )


@dataclass
class BacktestBatch:
    """同一时间点的一批回放数据。"""

    data_time: datetime = field(default_factory=datetime.now)
    ticks: Dict[str, TickData] = field(default_factory=dict)
    bars: Dict[str, BacktestBar] = field(default_factory=dict)


@dataclass
class EquityPoint:
    """净值曲线上的一个时点。"""

    data_time: datetime = field(default_factory=datetime.now)
    cash: float = 0.0
    market_value: float = 0.0
    equity: float = 0.0
    drawdown: float = 0.0


@dataclass
class DailyReturnPoint:
    """逐日收益序列上的一个时点。"""

    trade_day: str = ""
    equity: float = 0.0
    daily_return: float = 0.0


@dataclass
class ClosedTrade:
    """一笔已经闭合的 round-trip 交易明细。"""

    strategy_id: str = ""
    strategy_name: str = ""
    stock_code: str = ""
    entry_time: datetime = field(default_factory=datetime.now)
    exit_time: datetime = field(default_factory=datetime.now)
    quantity: int = 0
    entry_price: float = 0.0
    exit_price: float = 0.0
    entry_amount: float = 0.0
    exit_amount: float = 0.0
    buy_fee: float = 0.0
    sell_fee: float = 0.0
    pnl: float = 0.0
    return_ratio: float = 0.0
    holding_days: float = 0.0


@dataclass
class BacktestResult:
    """回测结果汇总。

    第一阶段先聚焦：
    - 基本绩效指标
    - 净值点列表
    - 订单和成交明细
    - 期末策略快照
    """

    config: BacktestConfig = field(default_factory=BacktestConfig)
    metrics: Dict[str, float] = field(default_factory=dict)
    equity_curve: List[EquityPoint] = field(default_factory=list)
    daily_returns: List[DailyReturnPoint] = field(default_factory=list)
    closed_trades: List[ClosedTrade] = field(default_factory=list)
    orders: List[dict] = field(default_factory=list)
    trades: List[dict] = field(default_factory=list)
    strategy_snapshots: List[StrategySnapshot] = field(default_factory=list)
