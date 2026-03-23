"""回测成交执行器。

这个模块替代真实交易执行器，负责：
1. 接收策略层发出的内部订单。
2. 在后续分钟 bar 中判断是否成交。
3. 生成模拟成交并回调 OrderManager。
4. 维护回测现金余额。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, Optional

from backtest.models import BacktestBar
from config.enums import OrderDirection, OrderStatus, OrderType
from config.fee_schedule import FeeSchedule
from monitor.logger import get_logger
from trading.models import Order
from trading.order_manager import OrderManager

logger = get_logger("trade")


@dataclass
class PendingBacktestOrder:
    """回测内部待撮合订单。

    这里把 Order 和其进入撮合队列的时间绑在一起，
    便于实现“下一根 bar 才开始判断成交”的规则。
    """

    order: Order
    submitted_at: datetime = field(default_factory=datetime.now)


class BacktestTradeExecutor:
    """第一阶段回测成交执行器。"""

    _LOT_SIZE = 100

    def __init__(self, order_mgr: OrderManager, position_mgr=None,
                 fee_schedule: Optional[FeeSchedule] = None,
                 initial_cash: float = 1_000_000.0,
                 slippage: float = 0.01):
        self._order_mgr = order_mgr
        self._position_mgr = position_mgr
        self._fee_schedule = fee_schedule
        self._cash = float(initial_cash)
        self._slippage = float(slippage)
        self._current_time: Optional[datetime] = None
        self._next_xt_order_id = 1
        self._pending_orders: Dict[str, PendingBacktestOrder] = {}

    @property
    def cash(self) -> float:
        """返回当前剩余现金。"""
        return self._cash

    def update_clock(self, current_time: datetime) -> None:
        """更新当前回测时钟。"""
        self._current_time = current_time

    def buy_limit(self, strategy_id: str, strategy_name: str,
                  stock_code: str, price: float,
                  quantity: int, remark: str = "") -> Order:
        """创建限价买单。"""
        order = self._new_order(
            strategy_id=strategy_id,
            strategy_name=strategy_name,
            stock_code=stock_code,
            direction=OrderDirection.BUY,
            order_type=OrderType.LIMIT,
            price=price,
            quantity=quantity,
            amount=0.0,
            remark=remark or f"回测限价买入 {stock_code}",
        )
        return self._submit_order(order)

    def buy_market(self, strategy_id: str, strategy_name: str,
                   stock_code: str, quantity: int, remark: str = "") -> Order:
        """创建市价买单。"""
        order = self._new_order(
            strategy_id=strategy_id,
            strategy_name=strategy_name,
            stock_code=stock_code,
            direction=OrderDirection.BUY,
            order_type=OrderType.MARKET,
            price=0.0,
            quantity=quantity,
            amount=0.0,
            remark=remark or f"回测市价买入 {stock_code}",
        )
        return self._submit_order(order)

    def buy_by_amount(self, strategy_id: str, strategy_name: str,
                      stock_code: str, price: float,
                      amount: float, remark: str = "") -> Order:
        """按金额换算股数后创建买单。"""
        if price <= 0:
            return self._failed_order(strategy_id, strategy_name, stock_code, OrderDirection.BUY, "price=0")
        quantity = int(amount // price // self._LOT_SIZE) * self._LOT_SIZE
        if quantity <= 0:
            return self._failed_order(strategy_id, strategy_name, stock_code, OrderDirection.BUY, "金额不足一手")
        order = self._new_order(
            strategy_id=strategy_id,
            strategy_name=strategy_name,
            stock_code=stock_code,
            direction=OrderDirection.BUY,
            order_type=OrderType.BY_AMOUNT,
            price=price,
            quantity=quantity,
            amount=amount,
            remark=remark or f"回测按金额买入 {stock_code}",
        )
        return self._submit_order(order)

    def sell_limit(self, strategy_id: str, strategy_name: str,
                   stock_code: str, price: float,
                   quantity: int, remark: str = "") -> Order:
        """创建限价卖单。"""
        order = self._new_order(
            strategy_id=strategy_id,
            strategy_name=strategy_name,
            stock_code=stock_code,
            direction=OrderDirection.SELL,
            order_type=OrderType.LIMIT,
            price=price,
            quantity=quantity,
            amount=0.0,
            remark=remark or f"回测限价卖出 {stock_code}",
        )
        return self._submit_order(order)

    def sell_market(self, strategy_id: str, strategy_name: str,
                    stock_code: str, quantity: int, remark: str = "") -> Order:
        """创建市价卖单。"""
        order = self._new_order(
            strategy_id=strategy_id,
            strategy_name=strategy_name,
            stock_code=stock_code,
            direction=OrderDirection.SELL,
            order_type=OrderType.MARKET,
            price=0.0,
            quantity=quantity,
            amount=0.0,
            remark=remark or f"回测市价卖出 {stock_code}",
        )
        return self._submit_order(order)

    def close_position(self, strategy_id: str, strategy_name: str,
                       stock_code: str, remark: str = "") -> Order:
        """按当前可用仓位创建平仓卖单。"""
        available = 0
        if self._position_mgr:
            position = self._position_mgr.get_position(strategy_id)
            if position:
                available = int(position.available_quantity or 0)
        if available <= 0:
            return self._failed_order(strategy_id, strategy_name, stock_code, OrderDirection.SELL, "无可用持仓")
        return self.sell_market(strategy_id, strategy_name, stock_code, available, remark or f"回测平仓 {stock_code}")

    def cancel_order(self, order_uuid: str, remark: str = "") -> bool:
        """撤销尚未成交的回测订单。"""
        pending = self._pending_orders.pop(order_uuid, None)
        if not pending:
            return False
        self._order_mgr.update_order_status(pending.order.xt_order_id, OrderStatus.CANCELED)
        logger.info("BacktestTradeExecutor: 撤销订单 uuid=%s remark=%s", order_uuid[:8], remark)
        return True

    def process_batch(self, bars: Dict[str, BacktestBar]) -> None:
        """用当前批次 bar 处理上一轮挂出的订单。"""
        current_time = self._current_time
        if current_time is None:
            return

        terminal_order_ids: list[str] = []
        for order_uuid, pending in list(self._pending_orders.items()):
            order = pending.order
            if pending.submitted_at >= current_time:
                continue
            bar = bars.get(order.stock_code)
            if not bar:
                continue

            fill_price = self._resolve_fill_price(order, bar)
            if fill_price is None:
                continue

            if not self._can_fill(order, fill_price):
                self._order_mgr.update_order_status(order.xt_order_id, OrderStatus.JUNK)
                terminal_order_ids.append(order_uuid)
                continue

            self._apply_cash_change(order, fill_price)
            trade_amount = fill_price * order.quantity
            trade_info = {
                "account_type": 0,
                "account_id": "BACKTEST",
                "order_type": 0,
                "traded_id": f"BT-{order.xt_order_id}-{int(bar.data_time.timestamp())}",
                "traded_time": int(bar.data_time.strftime("%Y%m%d%H%M%S")),
                "order_sysid": str(order.xt_order_id),
                "strategy_name": order.strategy_name,
                "order_remark": order.remark,
                "stock_code": order.stock_code,
                "direction": order.direction.value,
                "price": fill_price,
                "traded_price": fill_price,
                "quantity": order.quantity,
                "traded_volume": order.quantity,
                "amount": trade_amount,
                "traded_amount": trade_amount,
            }
            self._order_mgr.on_trade(order.xt_order_id, trade_info)
            terminal_order_ids.append(order_uuid)

        for order_uuid in terminal_order_ids:
            self._pending_orders.pop(order_uuid, None)

    def expire_all_orders(self, reason: str = "回测结束") -> None:
        """把尚未成交的订单全部标记为已撤。"""
        for order_uuid in list(self._pending_orders.keys()):
            self.cancel_order(order_uuid, reason)

    def _new_order(self, strategy_id: str, strategy_name: str, stock_code: str,
                   direction: OrderDirection, order_type: OrderType, price: float,
                   quantity: int, amount: float, remark: str) -> Order:
        return Order(
            strategy_id=strategy_id,
            strategy_name=strategy_name,
            stock_code=stock_code,
            direction=direction,
            order_type=order_type,
            price=float(price),
            quantity=int(quantity),
            amount=float(amount),
            remark=remark,
            create_time=self._current_time or datetime.now(),
            update_time=self._current_time or datetime.now(),
        )

    def _submit_order(self, order: Order) -> Order:
        order.xt_order_id = self._next_xt_order_id
        self._next_xt_order_id += 1
        order.status = OrderStatus.WAIT_REPORTING
        self._order_mgr.register_order(order)
        self._order_mgr.update_order_status(order.xt_order_id, OrderStatus.REPORTED)
        self._pending_orders[order.order_uuid] = PendingBacktestOrder(
            order=order,
            submitted_at=self._current_time or datetime.now(),
        )
        return order

    def _resolve_fill_price(self, order: Order, bar: BacktestBar) -> float | None:
        if order.direction == OrderDirection.BUY:
            if order.order_type == OrderType.MARKET:
                return bar.open_price + self._slippage
            if bar.low_price <= order.price:
                return float(order.price)
            return None

        if order.order_type == OrderType.MARKET:
            return max(0.001, bar.open_price - self._slippage)
        if bar.high_price >= order.price:
            return float(order.price)
        return None

    def _can_fill(self, order: Order, fill_price: float) -> bool:
        trade_amount = fill_price * order.quantity
        fee = self._fee_schedule.calculate(order.stock_code, order.direction, trade_amount) if self._fee_schedule else None
        total_fee = fee.total_fee if fee else 0.0
        if order.direction == OrderDirection.BUY:
            return self._cash >= trade_amount + total_fee
        if not self._position_mgr:
            return False
        position = self._position_mgr.get_position(order.strategy_id)
        available = int(position.available_quantity or 0) if position else 0
        return available >= order.quantity

    def _apply_cash_change(self, order: Order, fill_price: float) -> None:
        trade_amount = fill_price * order.quantity
        fee = self._fee_schedule.calculate(order.stock_code, order.direction, trade_amount) if self._fee_schedule else None
        total_fee = fee.total_fee if fee else 0.0
        if order.direction == OrderDirection.BUY:
            self._cash -= trade_amount + total_fee
        else:
            self._cash += trade_amount - total_fee

    @staticmethod
    def _failed_order(strategy_id: str, strategy_name: str, stock_code: str,
                      direction: OrderDirection, reason: str) -> Order:
        return Order(
            strategy_id=strategy_id,
            strategy_name=strategy_name,
            stock_code=stock_code,
            direction=direction,
            status=OrderStatus.JUNK,
            remark=f"[JUNK] {reason}",
        )
