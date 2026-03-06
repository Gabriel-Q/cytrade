"""Pydantic 数据模型（API 请求/响应）"""
from datetime import datetime
from typing import Any, Dict, List, Optional

try:
    from pydantic import BaseModel
except ImportError:
    class BaseModel:  # type: ignore
        pass


class StrategyInfo(BaseModel):
    strategy_id: str
    strategy_name: str
    stock_code: str
    status: str
    unrealized_pnl: float = 0.0
    realized_pnl: float = 0.0
    total_quantity: int = 0
    avg_cost: float = 0.0
    current_price: float = 0.0


class PositionDetail(BaseModel):
    strategy_id: str
    strategy_name: str
    stock_code: str
    total_quantity: int
    available_quantity: int
    avg_cost: float
    current_price: float
    market_value: float
    unrealized_pnl: float
    unrealized_pnl_ratio: float
    realized_pnl: float
    total_commission: float
    update_time: str


class PositionSummary(BaseModel):
    positions_count: int
    total_market_value: float
    total_cost: float
    total_unrealized_pnl: float
    total_realized_pnl: float
    total_commission: float
    total_pnl: float


class OrderInfo(BaseModel):
    order_uuid: str
    strategy_id: str
    strategy_name: str
    stock_code: str
    direction: str
    order_type: str
    price: float
    quantity: int
    status: str
    filled_quantity: int
    filled_avg_price: float
    filled_amount: float
    commission: float
    remark: str
    create_time: str
    update_time: str


class SystemStatus(BaseModel):
    connected: bool
    trading_time: bool
    strategy_count: int
    active_orders: int
    cpu_pct: float = 0.0
    mem_pct: float = 0.0
    timestamp: str


class ActionResponse(BaseModel):
    success: bool
    message: str


__all__ = [
    "StrategyInfo", "PositionDetail", "PositionSummary",
    "OrderInfo", "SystemStatus", "ActionResponse",
]
