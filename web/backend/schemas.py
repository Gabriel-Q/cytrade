"""Pydantic 数据模型（API 请求/响应）。

这些模型的作用是把后端返回的数据结构固定下来：
- 后端开发者知道接口应该返回哪些字段
- 前端开发者知道可以稳定依赖哪些字段
- FastAPI 可以自动生成接口文档
"""
from typing import Any, Dict, List

try:
    from pydantic import BaseModel
except ImportError:
    class BaseModel:  # type: ignore
        pass


class StrategyInfo(BaseModel):
    """策略列表与详情接口使用的统一响应模型。"""
    strategy_id: str               # 策略实例唯一 ID。
    strategy_name: str             # 策略名称。
    strategy_type: str = ""       # 策略类型/策略类名，不带实例后缀。
    stock_code: str                # 当前策略负责的标的代码。
    stock_name: str = ""          # 标的名称。
    status: str                    # 内部策略状态值。
    status_text: str               # 面向前端展示的状态文本。
    pause_reason: str = ""        # 当前暂停原因；运行中时通常为空。
    unrealized_pnl: float = 0.0    # 浮动盈亏。
    realized_pnl: float = 0.0      # 已实现盈亏。
    total_quantity: int = 0        # 当前总持仓股数。
    avg_cost: float = 0.0          # 平均持仓成本。
    current_price: float = 0.0     # 最新价格。
    create_time: str = ""         # 策略实例创建时间。
    capacity: Dict[str, Any] = {}   # 策略总标的名额配置与当前占用状态。


class StrategyCapacityWaitingItem(BaseModel):
    """容量排队中的单个策略实例摘要。"""
    strategy_id: str
    strategy_name: str
    stock_code: str
    stock_name: str = ""


class StrategyCapacityGroup(BaseModel):
    """按策略类型聚合后的容量概览。"""
    strategy_type: str
    instance_count: int = 0
    used: int = 0
    limit: int = 0
    remaining: int = 0
    occupying_count: int = 0
    waiting_count: int = 0
    waiting_items: List[StrategyCapacityWaitingItem] = []


class PausedStrategyReconciliation(BaseModel):
    """暂停策略的策略仓位与账户仓位对账视图。"""
    strategy_id: str
    strategy_name: str
    stock_code: str
    stock_name: str = ""
    pause_reason: str = ""
    strategy_total_quantity: int = 0
    strategy_available_quantity: int = 0
    account_total_quantity: int = 0
    account_available_quantity: int = 0


class PositionDetail(BaseModel):
    """单个持仓的详细信息。"""
    strategy_id: str                    # 所属策略 ID。
    strategy_name: str                  # 所属策略名称。
    stock_code: str                     # 标的代码。
    stock_name: str = ""               # 标的名称。
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
    stock_name: str = ""                # 证券名称统一字段。
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
    cancellable: bool = False             # 当前是否支持直接发起撤单。
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
    stock_name: str = ""                # 标的名称。

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


class StrategyPositionReplayStep(BaseModel):
    """单笔成交回放后的策略仓位快照。"""
    trade_id: str
    trade_time: str = ""
    trade_day: str = ""
    direction: str
    direction_text: str
    price: float
    quantity: int
    amount: float
    order_remark: str = ""
    total_quantity: int = 0
    available_quantity: int = 0
    avg_cost: float = 0.0
    realized_pnl: float = 0.0
    total_commission: float = 0.0


class StrategyPositionReplay(BaseModel):
    """按成交回放得到的策略仓位诊断结果。"""
    strategy_id: str
    strategy_name: str
    stock_code: str
    stock_name: str = ""
    step_count: int = 0
    final_total_quantity: int = 0
    final_available_quantity: int = 0
    live_total_quantity: int = 0
    live_available_quantity: int = 0
    steps: List[StrategyPositionReplayStep] = []


class SystemStatus(BaseModel):
    """系统状态面板使用的响应模型。"""
    connected: bool            # 交易连接是否可用。
    trading_time: bool         # 当前是否处于交易时段。
    strategy_count: int        # 当前策略数量。
    active_orders: int         # 当前活跃订单数。
    latest_data_time: str = ""   # 最新一笔行情的源时间。
    data_delay_ms: float = 0.0  # 最新一笔行情的延迟毫秒数。
    strategy_process_total_ms: float = 0.0  # 最近一轮行情推送的策略总处理耗时。
    data_latency_threshold_sec: float = 0.0  # 延迟阈值（秒），供前端判断展示状态。
    cpu_pct: float = 0.0       # CPU 使用率。
    mem_pct: float = 0.0       # 内存使用率。
    timestamp: str             # 响应生成时间。


class ActionResponse(BaseModel):
    """执行类接口的通用返回格式。"""
    success: bool              # 是否执行成功。
    message: str               # 给前端展示的结果消息。


__all__ = [
    "StrategyInfo", "PausedStrategyReconciliation", "PositionDetail", "PositionSummary",
    "OrderInfo", "TradeInfo", "StrategyPositionReplayStep", "StrategyPositionReplay",
    "StrategyCapacityWaitingItem", "StrategyCapacityGroup",
    "SystemStatus", "ActionResponse",
]
