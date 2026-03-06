"""
订单管理模块
- 追踪每笔订单的全生命周期
- 接收成交回报并通知持仓/策略模块（事件回调）
- 持久化到 SQLite（通过 DataManager）
"""
import threading
from datetime import datetime
from typing import Callable, Dict, List, Optional

from trading.models import Order, TradeRecord
from config.enums import OrderStatus, OrderDirection
from monitor.logger import get_logger

logger = get_logger("trade")


class OrderManager:
    """订单追踪管理器"""

    def __init__(self, data_manager=None):
        self._data_mgr = data_manager
        self._orders: Dict[str, Order] = {}                  # {order_uuid: Order}
        self._xt_to_uuid: Dict[int, str] = {}               # {xt_order_id: order_uuid}
        self._seq_to_uuid: Dict[int, str] = {}              # {async_seq: order_uuid} 临时映射
        self._position_callback: Optional[Callable[[TradeRecord], None]] = None
        self._strategy_callback: Optional[Callable[[Order], None]] = None
        self._lock = threading.Lock()

    # ------------------------------------------------------------------ 注册

    def register_order(self, order: Order) -> None:
        """注册新订单"""
        with self._lock:
            self._orders[order.order_uuid] = order
            if order.xt_order_id:
                self._xt_to_uuid[order.xt_order_id] = order.order_uuid
        if self._data_mgr:
            try:
                self._data_mgr.save_order(order)
            except Exception as e:
                logger.error("OrderManager: 持久化订单失败: %s", e, exc_info=True)
        logger.info("[ORDER] 注册订单 uuid=%s%s code=%s dir=%s price=%.3f qty=%d remark=%s",
                    order.order_uuid[:8], f" xt_id={order.xt_order_id}" if order.xt_order_id else "",
                    order.stock_code, order.direction.value,
                    order.price, order.quantity, order.remark)

    # ------------------------------------------------------------------ 状态更新

    def update_order_status(self, xt_order_id: int, status: OrderStatus,
                             filled_qty: int = 0, filled_amount: float = 0,
                             avg_price: float = 0) -> None:
        """更新订单状态（由 callback 调用）"""
        with self._lock:
            uuid = self._xt_to_uuid.get(xt_order_id)
            if not uuid:
                return
            order = self._orders.get(uuid)
            if not order:
                return
            order.status = status
            if filled_qty:
                order.filled_quantity = filled_qty
            if filled_amount:
                order.filled_amount = filled_amount
            if avg_price:
                order.filled_avg_price = avg_price
            order.update_time = datetime.now()

        if self._data_mgr:
            try:
                self._data_mgr.save_order(order)
            except Exception as e:
                logger.error("OrderManager: 更新持久化失败: %s", e, exc_info=True)

        if self._strategy_callback:
            try:
                self._strategy_callback(order)
            except Exception as e:
                logger.error("OrderManager: 策略回调异常: %s", e, exc_info=True)

        logger.debug("[ORDER] 订单状态变更 uuid=%s status=%s", uuid[:8], status.value)

    def on_trade(self, xt_order_id: int, trade_info: dict) -> None:
        """成交回报入口"""
        try:
            with self._lock:
                uuid = self._xt_to_uuid.get(xt_order_id)
                order = self._orders.get(uuid) if uuid else None

            strategy_id = order.strategy_id if order else ""
            strategy_name = order.strategy_name if order else ""

            direction_str = trade_info.get("direction", "BUY")
            direction = (OrderDirection.BUY
                         if "BUY" in direction_str.upper()
                         else OrderDirection.SELL)

            trade = TradeRecord(
                trade_id=trade_info.get("trade_id", ""),
                order_uuid=uuid or "",
                xt_order_id=xt_order_id,
                strategy_id=strategy_id,
                strategy_name=strategy_name,
                stock_code=trade_info.get("stock_code", ""),
                direction=direction,
                price=float(trade_info.get("price", 0)),
                quantity=int(trade_info.get("quantity", 0)),
                amount=float(trade_info.get("amount", 0)),
                commission=float(trade_info.get("commission", 0)),
                trade_time=datetime.now(),
            )

            # 更新订单已成交量
            if order:
                with self._lock:
                    order.filled_quantity += trade.quantity
                    order.filled_amount += trade.amount
                    if order.filled_quantity > 0:
                        order.filled_avg_price = order.filled_amount / order.filled_quantity
                    if order.filled_quantity >= order.quantity:
                        order.status = OrderStatus.FILLED
                    else:
                        order.status = OrderStatus.PARTIALLY_FILLED
                    order.update_time = datetime.now()

            # 持久化成交
            if self._data_mgr:
                try:
                    self._data_mgr.save_trade(trade)
                    if order:
                        self._data_mgr.save_order(order)
                except Exception as e:
                    logger.error("OrderManager: 成交持久化失败: %s", e, exc_info=True)

            # 通知持仓模块
            if self._position_callback:
                try:
                    self._position_callback(trade)
                except Exception as e:
                    logger.error("OrderManager: 持仓回调异常: %s", e, exc_info=True)

            # 通知策略模块
            if order and self._strategy_callback:
                try:
                    self._strategy_callback(order)
                except Exception as e:
                    logger.error("OrderManager: 策略回调异常: %s", e, exc_info=True)

            logger.info("[ORDER] [TRADE] 成交 uuid=%s code=%s price=%.3f qty=%d",
                        (uuid or "?")[:8], trade.stock_code, trade.price, trade.quantity)

        except Exception as e:
            logger.error("OrderManager: on_trade 处理异常: %s", e, exc_info=True)

    def on_async_response(self, seq: int, xt_order_id: int) -> None:
        """绑定异步下单序列号与柜台订单号"""
        with self._lock:
            uuid = self._seq_to_uuid.pop(seq, None)
            if uuid:
                self._xt_to_uuid[xt_order_id] = uuid
                order = self._orders.get(uuid)
                if order:
                    order.xt_order_id = xt_order_id
                    order.status = OrderStatus.SUBMITTED
                    order.update_time = datetime.now()
        logger.debug("OrderManager: async_response seq=%d → xt_id=%d", seq, xt_order_id)

    def register_seq(self, seq: int, order_uuid: str) -> None:
        """为异步下单注册 seq → uuid 映射"""
        with self._lock:
            self._seq_to_uuid[int(seq)] = order_uuid

    # ------------------------------------------------------------------ 查询

    def get_order(self, order_uuid: str) -> Optional[Order]:
        return self._orders.get(order_uuid)

    def get_order_by_xt_id(self, xt_order_id: int) -> Optional[Order]:
        with self._lock:
            uuid = self._xt_to_uuid.get(xt_order_id)
            return self._orders.get(uuid) if uuid else None

    def get_orders_by_strategy(self, strategy_id: str) -> List[Order]:
        with self._lock:
            return [o for o in self._orders.values() if o.strategy_id == strategy_id]

    def get_active_orders(self) -> List[Order]:
        with self._lock:
            return [o for o in self._orders.values() if o.is_active()]

    # ------------------------------------------------------------------ 回调注册

    def set_position_callback(self, callback: Callable[[TradeRecord], None]) -> None:
        self._position_callback = callback

    def set_strategy_callback(self, callback: Callable[[Order], None]) -> None:
        self._strategy_callback = callback


__all__ = ["OrderManager"]
