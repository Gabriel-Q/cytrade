"""交易链路共享数据模型。

本模块定义两类最核心的数据对象：

* `Order`：描述一笔委托从创建到终结的完整生命周期。
* `TradeRecord`：描述一笔实际成交回报及其费用拆分。

它们会在回调层、订单管理器、持久化层、Web 接口层之间流转，因此字段
除了统一抽象字段外，也保留了较完整的 xtquant 原始字段，方便排障与追踪。
"""
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, Optional
import uuid

from config.enums import OrderDirection, OrderType, OrderStatus


@dataclass
class Order:
    """订单数据模型。

    这个对象既保存框架内部统一字段，也保存完整的 XtOrder 关键字段。
    这样无论是策略层、持久化层还是问题排查，都能拿到足够完整的信息。
    """
    order_uuid: str = field(default_factory=lambda: str(uuid.uuid4()))  # 框架内部订单唯一标识。
    strategy_id: str = ""  # 发起该委托的策略实例 ID。
    strategy_name: str = ""  # 发起该委托的策略名称。
    stock_code: str = ""  # 统一格式的 6 位证券代码。
    direction: OrderDirection = OrderDirection.BUY  # 买卖方向。
    order_type: OrderType = OrderType.LIMIT  # 订单类型，如限价、市价。
    price: float = 0.0  # 委托价格；按金额下单或市价单时可能仅作参考。
    quantity: int = 0  # 委托数量，单位通常为“股”。
    amount: float = 0.0  # 委托金额；在按金额下单模式下使用。
    status: OrderStatus = OrderStatus.UNREPORTED  # 订单当前统一状态。
    filled_quantity: int = 0  # 当前累计已成交数量。
    filled_amount: float = 0.0  # 当前累计已成交金额。
    filled_avg_price: float = 0.0  # 当前累计成交均价。
    xt_order_id: int = 0  # 柜台侧订单编号。
    account_type: int = 0  # xtquant 返回的账号类型原始值。
    account_id: str = ""  # xtquant 返回的资金账号。
    xt_stock_code: str = ""  # xtquant 原始证券代码，通常包含市场后缀。
    order_sysid: str = ""  # 柜台合同编号或系统委托编号。
    order_time: int = 0  # xtquant 原始委托时间戳/整数时间。
    xt_order_type: int = 0  # xtquant 原始委托类型值。
    price_type: int = 0  # xtquant 原始报价类型值。
    xt_order_status: int = 0  # xtquant 原始状态码。
    status_msg: str = ""  # 柜台返回的状态说明，常用于废单原因展示。
    xt_direction: int = 0  # xtquant 原始买卖方向字段。
    offset_flag: int = 0  # xtquant 原始开平/买卖操作标记。
    secu_account: str = ""  # 对应的股东账号。
    instrument_name: str = ""  # 证券名称，便于界面展示。
    xt_fields: Dict[str, Any] = field(default_factory=dict)  # 完整 XtOrder 公共字段快照。
    remark: str = ""  # 下单备注、触发原因或诊断信息。
    commission: float = 0.0  # 手续费总额，对外兼容字段。
    buy_commission: float = 0.0  # 买入佣金累计值。
    sell_commission: float = 0.0  # 卖出佣金累计值。
    stamp_tax: float = 0.0  # 印花税累计值。
    total_fee: float = 0.0  # 当前累计总交易费用。
    create_time: datetime = field(default_factory=datetime.now)  # 订单创建时间。
    update_time: datetime = field(default_factory=datetime.now)  # 订单最近更新时间。

    def is_active(self) -> bool:
        """判断订单是否仍处于活动状态。

        Returns:
            bool: 如果订单还可能继续收到成交、撤单或状态更新，则返回 `True`。
        """
        return self.status in (
            OrderStatus.UNREPORTED,
            OrderStatus.WAIT_REPORTING,
            OrderStatus.REPORTED,
            OrderStatus.REPORTED_CANCEL,
            OrderStatus.PARTSUCC_CANCEL,
            OrderStatus.PART_SUCC,
        )

    def remaining_quantity(self) -> int:
        """返回订单当前剩余未成交数量。

        Returns:
            int: 使用委托数量减去累计成交数量得到的剩余量。
        """
        return self.quantity - self.filled_quantity


@dataclass
class TradeRecord:
    """描述一笔真实成交回报。

    与 `Order` 不同，成交记录通常是不可变事件：一旦产生，主要用于驱动持仓更新、
    费用统计、日志记录和后续复盘分析。
    """

    account_type: int = 0  # xtquant 返回的账号类型。
    account_id: str = ""  # 该笔成交所属的资金账号。
    order_type: int = 0  # xtquant 原始委托类型。
    trade_id: str = ""  # 交易所返回的成交编号。
    xt_traded_time: int = 0  # xtquant 原始成交时间。
    order_uuid: str = ""  # 关联的内部订单 UUID。
    xt_order_id: int = 0  # 关联的柜台订单号。
    order_sysid: str = ""  # 柜台合同编号。
    strategy_id: str = ""  # 归属策略实例 ID。
    strategy_name: str = ""  # 归属策略名称。
    order_remark: str = ""  # 继承自委托的备注信息。
    stock_code: str = ""  # 统一格式股票代码。
    direction: OrderDirection = OrderDirection.BUY  # 买卖方向。
    xt_direction: int = 0  # xtquant 原始方向字段。
    offset_flag: int = 0  # xtquant 原始交易操作标识。
    price: float = 0.0  # 成交价格。
    quantity: int = 0  # 成交数量。
    amount: float = 0.0  # 成交金额。
    commission: float = 0.0  # 对外统一暴露的手续费字段。
    buy_commission: float = 0.0  # 买入佣金。
    sell_commission: float = 0.0  # 卖出佣金。
    stamp_tax: float = 0.0  # 卖出印花税。
    total_fee: float = 0.0  # 总费用，通常等于佣金加印花税。
    is_t0: bool = False  # 标记该证券是否允许 T+0 回转交易。
    secu_account: str = ""  # 股东账号。
    instrument_name: str = ""  # 证券名称。
    xt_fields: Dict[str, Any] = field(default_factory=dict)  # 完整 XtTrade 公共字段快照。
    trade_time: datetime = field(default_factory=datetime.now)  # 框架记录的成交时间。


__all__ = ["Order", "TradeRecord"]
