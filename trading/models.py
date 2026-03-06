"""交易相关数据模型（Order、TradeRecord）"""
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional
import uuid

from config.enums import OrderDirection, OrderType, OrderStatus


@dataclass
class Order:
    """订单数据模型

    内部使用 order_uuid 追踪；xt_order_id 为柜台返回的订单号
    """
    order_uuid: str = field(default_factory=lambda: str(uuid.uuid4()))
    strategy_id: str = ""
    strategy_name: str = ""
    stock_code: str = ""                          # 6位数字代码
    direction: OrderDirection = OrderDirection.BUY
    order_type: OrderType = OrderType.LIMIT
    price: float = 0.0                            # 委托价格（限价）
    quantity: int = 0                             # 委托数量（股）
    amount: float = 0.0                           # 委托金额（按金额下单时使用）
    status: OrderStatus = OrderStatus.PENDING
    filled_quantity: int = 0                      # 已成交数量
    filled_amount: float = 0.0                    # 已成交金额
    filled_avg_price: float = 0.0                 # 成交均价
    xt_order_id: int = 0                          # 柜台订单号
    remark: str = ""                              # 下单备注/原因
    commission: float = 0.0                       # 手续费
    create_time: datetime = field(default_factory=datetime.now)
    update_time: datetime = field(default_factory=datetime.now)

    def is_active(self) -> bool:
        """是否为活跃订单（未终结）"""
        return self.status in (
            OrderStatus.PENDING,
            OrderStatus.SUBMITTED,
            OrderStatus.PARTIALLY_FILLED,
        )

    def remaining_quantity(self) -> int:
        """未成交数量"""
        return self.quantity - self.filled_quantity


@dataclass
class TradeRecord:
    """成交记录 — 每笔实际成交对应一条"""
    trade_id: str = ""                            # 成交编号（来自交易所）
    order_uuid: str = ""                          # 关联的内部订单UUID
    xt_order_id: int = 0                          # 关联的柜台订单号
    strategy_id: str = ""
    strategy_name: str = ""
    stock_code: str = ""
    direction: OrderDirection = OrderDirection.BUY
    price: float = 0.0                            # 成交价
    quantity: int = 0                             # 成交数量
    amount: float = 0.0                           # 成交金额
    commission: float = 0.0                       # 手续费
    trade_time: datetime = field(default_factory=datetime.now)


__all__ = ["Order", "TradeRecord"]
