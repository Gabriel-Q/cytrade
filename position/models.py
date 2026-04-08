"""持仓数据模型。

这些模型只描述“持仓是什么样子”，不负责具体业务逻辑。
真正的买卖更新逻辑在 ``position.manager`` 中实现。
"""
from dataclasses import dataclass, field
from datetime import datetime
from typing import List


@dataclass
class FifoLot:
    """先进先出（FIFO）成本追踪单位：一次买入批次。

    在 FIFO 成本法下，持仓不会只保留一个平均成本，
    而是把每次买入拆成独立 lot，卖出时按时间顺序逐批扣减。
    """
    quantity: int = 0
    cost_price: float = 0.0
    buy_time: datetime = field(default_factory=datetime.now)


@dataclass
class PositionInfo:
    """单个策略的持仓信息（内存中实时维护）。

    可以把它理解成“某个策略实例当前手里这只票的完整状态”。
    它既包含数量和成本，也包含盈亏、费用和 FIFO 批次信息。
    """
    strategy_id: str = ""
    strategy_name: str = ""
    stock_code: str = ""
    total_quantity: int = 0              # 总持仓数量
    sellable_base_quantity: int = 0      # 理论可卖基线（不含账户临时冻结影响）
    available_quantity: int = 0          # 可用数量（T+1 规则下可能低于 total）
    is_t0: bool = False                  # 是否允许当日回转（T+0）
    avg_cost: float = 0.0               # 移动平均成本价
     
    total_cost: float = 0.0             # 当前持仓总成本
    current_price: float = 0.0          # 最新价格
    market_value: float = 0.0           # 当前市值
    unrealized_pnl: float = 0.0         # 浮动盈亏（元）
    unrealized_pnl_ratio: float = 0.0   # 浮动盈亏比例
    realized_pnl: float = 0.0           # 已实现盈亏
    total_commission: float = 0.0       # 累计手续费
    total_buy_commission: float = 0.0   # 累计买入佣金
    total_sell_commission: float = 0.0  # 累计卖出佣金
    total_stamp_tax: float = 0.0        # 累计印花税
    total_fees: float = 0.0             # 累计总费用
    fifo_lots: List[FifoLot] = field(default_factory=list)  # FIFO 批次列表
    update_time: datetime = field(default_factory=datetime.now)

    def refresh_market_value(self, price: float) -> None:
        """更新最新价并重算浮动盈亏。

        注意：这里不会修改已实现盈亏，
        因为已实现盈亏只会在真实卖出成交时发生变化。
        """
        # current_price / market_value / unrealized_pnl 都属于“可由最新价直接推导”的实时字段。
        self.current_price = price
        self.market_value = self.total_quantity * price
        if self.total_cost > 0:
            self.unrealized_pnl = self.market_value - self.total_cost
            self.unrealized_pnl_ratio = self.unrealized_pnl / self.total_cost
        self.update_time = datetime.now()


__all__ = ["PositionInfo", "FifoLot"] 
















