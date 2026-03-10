"""Pydantic 数据模型（API 请求/响应）。

这些模型的作用是把后端返回的数据结构固定下来：
- 后端开发者知道接口应该返回哪些字段
- 前端开发者知道可以稳定依赖哪些字段
- FastAPI 可以自动生成接口文档
"""
from typing import Any, Dict

try:
    from pydantic import BaseModel
except ImportError:
    class BaseModel:  # type: ignore
        pass


class StrategyInfo(BaseModel):
    """策略列表与详情接口使用的统一响应模型。"""
    strategy_id: str               # 策略实例唯一 ID。
    strategy_name: str             # 策略名称。
    stock_code: str                # 当前策略负责的标的代码。
    status: str                    # 内部策略状态值。
    status_text: str               # 面向前端展示的状态文本。
    unrealized_pnl: float = 0.0    # 浮动盈亏。
    realized_pnl: float = 0.0      # 已实现盈亏。
    total_quantity: int = 0        # 当前总持仓股数。
    avg_cost: float = 0.0          # 平均持仓成本。
    current_price: float = 0.0     # 最新价格。


class PositionDetail(BaseModel):
    """单个持仓的详细信息。"""
    strategy_id: str                    # 所属策略 ID。
    strategy_name: str                  # 所属策略名称。
    stock_code: str                     # 标的代码。
    total_quantity: int                 # 总持仓数量。
    available_quantity: int             # 当前可卖数量。
    is_t0: bool = False                 # 是否按 T+0 规则处理。
    avg_cost: float                     # 平均持仓成本。
    current_price: float                # 最新价格。
    market_value: float                 # 当前市值。
    unrealized_pnl: float               # 浮动盈亏。
    unrealized_pnl_ratio: float         # 浮动盈亏比例。
    realized_pnl: float                 # 已实现盈亏。
    total_commission: float             # 总费用汇总。
    total_buy_commission: float = 0.0   # 累计买入佣金。
    total_sell_commission: float = 0.0  # 累计卖出佣金。
    total_stamp_tax: float = 0.0        # 累计印花税。
    total_fees: float = 0.0             # 累计总费用。
    update_time: str                    # 最后更新时间。


class PositionSummary(BaseModel):
    """全部持仓的汇总统计信息。"""
    positions_count: int                 # 持仓条目数量。
    total_market_value: float            # 总市值。
    total_cost: float                    # 总成本。
    total_unrealized_pnl: float          # 总浮动盈亏。
    total_realized_pnl: float            # 总已实现盈亏。
    total_commission: float              # 总费用。
    total_buy_commission: float = 0.0    # 总买入佣金。
    total_sell_commission: float = 0.0   # 总卖出佣金。
    total_stamp_tax: float = 0.0         # 总印花税。
    total_fees: float = 0.0              # 总费用别名字段。
    total_pnl: float                     # 总盈亏。


class OrderInfo(BaseModel):
    """订单展示模型。"""
    order_uuid: str                       # 内部订单 UUID。
    xt_order_id: int = 0                  # 柜台订单号。
    account_type: int = 0                 # 账号类型原始值。
    account_id: str = ""                 # 资金账号。
    strategy_id: str                      # 所属策略 ID。
    strategy_name: str                    # 所属策略名称。
    stock_code: str                       # 内部证券代码。
    xt_stock_code: str = ""              # Xt 原始证券代码。
    direction: str                        # 内部买卖方向值。
    direction_text: str                   # 展示用方向文本。
    order_type: str                       # 内部订单类型值。
    order_type_text: str                  # 展示用订单类型文本。
    xt_order_type: int = 0                # Xt 原始订单类型。
    price_type: int = 0                   # Xt 原始报价类型。
    price: float                          # 委托价格。
    quantity: int                         # 委托数量。
    status: str                           # 内部订单状态值。
    status_text: str                      # 展示用订单状态文本。
    xt_order_status: int = 0              # Xt 原始状态码。
    status_msg: str = ""                 # 状态说明或失败原因。
    order_sysid: str = ""                # 柜台合同编号。
    order_time: int = 0                   # Xt 原始委托时间。
    xt_direction: int = 0                 # Xt 原始方向值。
    offset_flag: int = 0                  # Xt 原始开平方向值。
    secu_account: str = ""               # 股东代码。
    instrument_name: str = ""            # 证券名称。
    filled_quantity: int                  # 已成交数量。
    filled_avg_price: float               # 已成交均价。
    filled_amount: float                  # 已成交金额。
    commission: float                     # 总费用。
    buy_commission: float = 0.0           # 买入佣金。
    sell_commission: float = 0.0          # 卖出佣金。
    stamp_tax: float = 0.0                # 印花税。
    total_fee: float = 0.0                # 总费用明细字段。
    remark: str                           # 备注。
    xt_fields: Dict[str, Any] = {}        # 原始 Xt 字段快照。
    create_time: str                      # 创建时间。
    update_time: str                      # 更新时间。


class TradeInfo(BaseModel):
    """成交展示模型。

    这里既保留了本项目内部关注的字段，也保留了部分 XtTrade 原始字段，
    方便问题排查和前端扩展展示。
    """
    trade_id: str                         # 成交编号。
    xt_order_id: int                      # 关联柜台订单号。
    order_uuid: str                       # 关联内部订单 UUID。
    strategy_id: str                      # 所属策略 ID。
    strategy_name: str                    # 所属策略名称。
    stock_code: str                       # 标的代码。

    account_type: int                     # 账号类型。
    account_id: str                       # 资金账号。
    order_type: int                       # Xt 原始订单类型。
    traded_time: int                      # Xt 原始成交时间。
    order_sysid: str                      # 柜台合同编号。
    order_remark: str                     # 委托备注。
    xt_direction: int                     # Xt 原始方向值。
    offset_flag: int                      # Xt 原始开平方向值。

    direction: str                        # 内部买卖方向值。
    direction_text: str                   # 展示用方向文本。
    price: float                          # 成交价。
    quantity: int                         # 成交量。
    amount: float                         # 成交额。
    commission: float                     # 总费用。
    buy_commission: float = 0.0           # 买入佣金。
    sell_commission: float = 0.0          # 卖出佣金。
    stamp_tax: float = 0.0                # 印花税。
    total_fee: float = 0.0                # 总费用。
    is_t0: bool = False                   # 是否按 T+0 标记。
    trade_time: str                       # 标准化成交时间字符串。


class SystemStatus(BaseModel):
    """系统状态面板使用的响应模型。"""
    connected: bool            # 交易连接是否可用。
    trading_time: bool         # 当前是否处于交易时段。
    strategy_count: int        # 当前策略数量。
    active_orders: int         # 当前活跃订单数。
    cpu_pct: float = 0.0       # CPU 使用率。
    mem_pct: float = 0.0       # 内存使用率。
    timestamp: str             # 响应生成时间。


class ActionResponse(BaseModel):
    """执行类接口的通用返回格式。"""
    success: bool              # 是否执行成功。
    message: str               # 给前端展示的结果消息。


__all__ = [
    "StrategyInfo", "PositionDetail", "PositionSummary",
    "OrderInfo", "TradeInfo", "SystemStatus", "ActionResponse",
]
