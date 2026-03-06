"""
XtQuant 交易回调管理
- 作为 xtquant 与框架的中介
- 所有回调均用 try-except 包裹，防止异常导致 QMT 崩溃
- 解析成交/委托信息后转发给 OrderManager / ConnectionManager
隔离外部依赖：将 xtquant 的回调机制与业务逻辑解耦。
异常安全：每个回调方法都用 try-except 包裹，防止回调中抛出的异常导致 QMT 客户端崩溃。
状态映射与数据清洗：将 xtquant 返回的原始数据（如订单状态码、股票代码格式）转换为内部枚举和标准格式。
"""
import logging
from typing import Optional

try:
    from xtquant.xttrader import XtQuantTraderCallback
    _XT_AVAILABLE = True
except ImportError:
    _XT_AVAILABLE = False

    class XtQuantTraderCallback:  # type: ignore
        """Mock 基类"""
        pass

from monitor.logger import get_logger
from config.enums import OrderStatus

logger = get_logger("system")


class MyXtQuantTraderCallback(XtQuantTraderCallback):
    """XtQuant 统一回调处理器"""

    def __init__(self, order_manager=None, connection_manager=None):
        super().__init__()
        self._order_mgr = order_manager
        self._conn_mgr = connection_manager

    def set_order_manager(self, order_manager) -> None:
        self._order_mgr = order_manager

    def set_connection_manager(self, connection_manager) -> None:
        self._conn_mgr = connection_manager

    # ------------------------------------------------------------------ 回调

    def on_disconnected(self) -> None:
        try:
            logger.warning("[Callback] on_disconnected — 触发重连")
            if self._conn_mgr:
                self._conn_mgr.on_disconnected()
        except Exception as e:
            logger.error("[Callback] on_disconnected 异常: %s", e, exc_info=True)

    def on_stock_order(self, order) -> None:
        """委托回报（状态变化）"""
        try:
            if not self._order_mgr:
                return
            status = self._map_order_status(order.order_status)
            self._order_mgr.update_order_status(
                xt_order_id=order.order_id,
                status=status,
                filled_qty=int(order.traded_volume or 0),
                filled_amount=float(order.traded_amount or 0),
                avg_price=float(order.traded_price or 0),
            )
            logger.debug("[Callback] on_stock_order id=%s status=%s", order.order_id, status)
        except Exception as e:
            logger.error("[Callback] on_stock_order 异常: %s", e, exc_info=True)

    def on_stock_trade(self, trade) -> None:
        """成交回报"""
        try:
            if not self._order_mgr:
                return
            trade_info = {
                "trade_id": str(getattr(trade, "traded_id", "") or ""),
                "xt_order_id": int(getattr(trade, "order_id", 0) or 0),
                "stock_code": self._xt_to_code(str(trade.stock_code or "")),
                "direction": str(getattr(trade, "order_type", "BUY")),
                "price": float(getattr(trade, "traded_price", 0) or 0),
                "quantity": int(getattr(trade, "traded_volume", 0) or 0),
                "amount": float(getattr(trade, "traded_amount", 0) or 0),
                "commission": float(getattr(trade, "commission", 0) or 0),
            }
            self._order_mgr.on_trade(trade_info["xt_order_id"], trade_info)
            logger.info("[ORDER] [TRADE] 成交回报 order_id=%s price=%.3f qty=%d",
                        trade_info["xt_order_id"], trade_info["price"], trade_info["quantity"])
        except Exception as e:
            logger.error("[Callback] on_stock_trade 异常: %s", e, exc_info=True)

    def on_order_error(self, order_error) -> None:
        """下单错误"""
        try:
            if not self._order_mgr:
                return
            xt_id = int(getattr(order_error, "order_id", 0) or 0)
            err_msg = str(getattr(order_error, "error_msg", "unknown") or "unknown")
            logger.error("[Callback] 下单失败 order_id=%s msg=%s", xt_id, err_msg)
            self._order_mgr.update_order_status(xt_order_id=xt_id, status=OrderStatus.FAILED)
        except Exception as e:
            logger.error("[Callback] on_order_error 异常: %s", e, exc_info=True)

    def on_cancel_order_error(self, cancel_error) -> None:
        """撤单错误"""
        try:
            xt_id = int(getattr(cancel_error, "order_id", 0) or 0)
            err_msg = str(getattr(cancel_error, "error_msg", "unknown") or "unknown")
            logger.warning("[Callback] 撤单失败 order_id=%s msg=%s", xt_id, err_msg)
        except Exception as e:
            logger.error("[Callback] on_cancel_order_error 异常: %s", e, exc_info=True)

    def on_order_stock_async_response(self, response) -> None:
        """异步下单响应 — 记录柜台返回的 order_id"""
        try:
            if not self._order_mgr:
                return
            seq = int(getattr(response, "seq", 0) or 0)
            xt_id = int(getattr(response, "order_id", 0) or 0)
            logger.debug("[Callback] async_response seq=%d xt_id=%d", seq, xt_id)
            self._order_mgr.on_async_response(seq, xt_id)
        except Exception as e:
            logger.error("[Callback] on_order_stock_async_response 异常: %s", e, exc_info=True)

    def on_account_status(self, status) -> None:
        """账户状态变化"""
        try:
            account_id = str(getattr(status, "account_id", "?") or "?")
            acc_status = str(getattr(status, "status", "?") or "?")
            logger.info("[Callback] 账户状态变化 account=%s status=%s", account_id, acc_status)
        except Exception as e:
            logger.error("[Callback] on_account_status 异常: %s", e, exc_info=True)

    # ------------------------------------------------------------------ Private

    @staticmethod
    def _map_order_status(xt_status) -> OrderStatus:
        """将 xtquant 委托状态映射为内部 OrderStatus"""
        mapping = {
            50: OrderStatus.SUBMITTED,
            51: OrderStatus.SUBMITTED,
            52: OrderStatus.PARTIALLY_FILLED,
            53: OrderStatus.FILLED,
            54: OrderStatus.CANCELLED,
            55: OrderStatus.CANCELLED,
            56: OrderStatus.REJECTED,
            57: OrderStatus.FAILED,
        }
        return mapping.get(int(xt_status or 0), OrderStatus.SUBMITTED)

    @staticmethod
    def _xt_to_code(xt_code: str) -> str:
        """xtquant 格式代码 → 6位数字代码"""
        return xt_code.split(".")[0] if "." in xt_code else xt_code


__all__ = ["MyXtQuantTraderCallback"]
