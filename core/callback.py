"""XtQuant 交易回调适配模块。

这个模块位于 xtquant 与项目内部领域模型之间，主要负责：
1. 接收 XtQuantTrader 的原始回调对象。
2. 把原始字段清洗成项目内部统一格式。
3. 将事件安全地转发给连接管理器和订单管理器。

所有回调都做异常保护，避免回调异常反向影响 QMT 客户端。
"""
from typing import Any, Dict, Optional

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
    """XtQuant 统一回调处理器。

    这个类是“外部交易接口”和“内部业务模块”之间的翻译层：
    - 接收 xtquant 的原始回调对象
    - 抽取关键字段
    - 转换成项目内部统一的数据格式
    - 分发给订单管理器或连接管理器
    """

    def __init__(self, order_manager=None, connection_manager=None):
        """初始化回调适配器。

        Args:
            order_manager: 可选的订单管理器，用于接收订单和成交事件。
            connection_manager: 可选的连接管理器，用于接收断线事件。
        """
        super().__init__()
        # ``_order_mgr`` 负责处理订单状态变化和成交回报。
        self._order_mgr = order_manager
        # ``_conn_mgr`` 负责处理连接断开后的重连流程。
        self._conn_mgr = connection_manager

    def set_order_manager(self, order_manager) -> None:
        """在运行时替换订单管理器引用。"""
        self._order_mgr = order_manager

    def set_connection_manager(self, connection_manager) -> None:
        """在运行时替换连接管理器引用。"""
        self._conn_mgr = connection_manager

    # ------------------------------------------------------------------ 回调

    def on_disconnected(self) -> None:
        """连接断开时通知连接管理器启动重连。"""
        try:
            logger.warning("[Callback] on_disconnected — 触发重连")
            if self._conn_mgr:
                self._conn_mgr.on_disconnected()
        except Exception as e:
            logger.error("[Callback] on_disconnected 异常: %s", e, exc_info=True)

    def on_connected(self) -> None:
        """连接建立成功时记录日志。"""
        try:
            logger.info("[Callback] on_connected — 交易连接已建立")
        except Exception as e:
            logger.error("[Callback] on_connected 异常: %s", e, exc_info=True)

    def on_stock_asset(self, asset) -> None:
        """资产推送回调。

        当前框架主要在启动前主动查询账户资产，这里的推送先做日志记录，
        为未来扩展实时资产面板预留入口。
        """
        try:
            logger.debug(
                "[Callback] on_stock_asset account=%s cash=%s total_asset=%s",
                getattr(asset, "account_id", "?"),
                getattr(asset, "cash", "?"),
                getattr(asset, "total_asset", "?"),
            )
        except Exception as e:
            logger.error("[Callback] on_stock_asset 异常: %s", e, exc_info=True)

    def on_stock_order(self, order) -> None:
        """处理委托状态变化回报。"""
        try:
            if not self._order_mgr:
                return
            # xtquant 返回的是数字状态码，先映射成内部枚举，再交给订单管理器。
            order_info = self._build_xt_order_payload(order)
            status = self._map_order_status(order.order_status)
            self._order_mgr.update_order_status(
                xt_order_id=order.order_id,
                status=status,
                filled_qty=int(order.traded_volume or 0),
                filled_amount=float(getattr(order, "traded_amount", 0) or 0),
                avg_price=float(order.traded_price or 0),
                order_info=order_info,
            )
            logger.debug("[Callback] on_stock_order id=%s status=%s", order.order_id, status)
        except Exception as e:
            logger.error("[Callback] on_stock_order 异常: %s", e, exc_info=True)

    def on_stock_trade(self, trade) -> None:
        """处理成交回报。"""
        try:
            if not self._order_mgr:
                return
            # 先把 XtTrade 对象拆成普通字典，便于后续统一处理和扩展字段。
            trade_info = {
                "account_type": int(getattr(trade, "account_type", 0) or 0),
                "account_id": str(getattr(trade, "account_id", "") or ""),
                "strategy_id": str(getattr(trade, "strategy_id", "") or ""),
                "stock_code": self._xt_to_code(str(trade.stock_code or "")),
                "order_type": int(getattr(trade, "order_type", 0) or 0),
                "traded_id": str(getattr(trade, "traded_id", "") or ""),
                "traded_time": int(getattr(trade, "traded_time", 0) or 0),
                "traded_price": float(getattr(trade, "traded_price", 0) or 0),
                "traded_volume": int(getattr(trade, "traded_volume", 0) or 0),
                "traded_amount": float(getattr(trade, "traded_amount", 0) or 0),
                "order_id": int(getattr(trade, "order_id", 0) or 0),
                "order_sysid": str(getattr(trade, "order_sysid", "") or ""),
                "strategy_name": str(getattr(trade, "strategy_name", "") or ""),
                "order_remark": str(getattr(trade, "order_remark", "") or ""),
                "direction": int(getattr(trade, "direction", 0) or 0),
                "offset_flag": int(getattr(trade, "offset_flag", 0) or 0),
                "commission": float(getattr(trade, "commission", 0.0) or 0.0),
                "secu_account": str(getattr(trade, "secu_account", "") or ""),
                "instrument_name": str(getattr(trade, "instrument_name", "") or ""),
                "xt_fields": self._extract_public_attrs(trade),
            }
            # 再补齐项目内部更易理解的统一字段名，
            # 这样后续业务层不必感知 XtTrade 的命名差异。
            trade_info.update({
                "trade_id": trade_info["traded_id"],
                "xt_order_id": trade_info["order_id"],
                "price": trade_info["traded_price"],
                "quantity": trade_info["traded_volume"],
                "amount": trade_info["traded_amount"],
            })
            self._order_mgr.on_trade(trade_info["order_id"], trade_info)
            logger.info("[ORDER] [TRADE] 成交回报 order_id=%s price=%.3f qty=%d",
                        trade_info["order_id"], trade_info["traded_price"], trade_info["traded_volume"])
        except Exception as e:
            logger.error("[Callback] on_stock_trade 异常: %s", e, exc_info=True)

    def on_order_error(self, order_error) -> None:
        """处理下单错误回报。"""
        try:
            if not self._order_mgr:
                return
            xt_id = int(getattr(order_error, "order_id", 0) or 0)
            err_msg = str(getattr(order_error, "error_msg", "unknown") or "unknown")
            logger.error("[Callback] 下单失败 order_id=%s msg=%s", xt_id, err_msg)
            self._order_mgr.update_order_status(
                xt_order_id=xt_id,
                status=OrderStatus.JUNK,
                order_info={
                    "status_msg": err_msg,
                    "order_status": 57,
                },
            )
        except Exception as e:
            logger.error("[Callback] on_order_error 异常: %s", e, exc_info=True)

    def on_cancel_error(self, cancel_error) -> None:
        """撤单错误。"""
        try:
            xt_id = int(getattr(cancel_error, "order_id", 0) or 0)
            err_msg = str(getattr(cancel_error, "error_msg", "unknown") or "unknown")
            logger.warning("[Callback] 撤单失败 order_id=%s msg=%s", xt_id, err_msg)
        except Exception as e:
            logger.error("[Callback] on_cancel_error 异常: %s", e, exc_info=True)

    def on_cancel_order_error(self, cancel_error) -> None:
        """兼容旧命名，内部转发到 ``on_cancel_error()``。"""
        self.on_cancel_error(cancel_error)

    def on_order_stock_async_response(self, response) -> None:
        """处理异步下单响应，并绑定本地订单与柜台订单号。"""
        try:
            if not self._order_mgr:
                return
            seq = int(getattr(response, "seq", 0) or 0)
            xt_id = int(getattr(response, "order_id", 0) or 0)
            logger.debug("[Callback] async_response seq=%d xt_id=%d", seq, xt_id)
            self._order_mgr.on_async_response(seq, xt_id)
        except Exception as e:
            logger.error("[Callback] on_order_stock_async_response 异常: %s", e, exc_info=True)

    def on_cancel_order_stock_async_response(self, response) -> None:
        """异步撤单响应。

        当前主要记录日志；真正的撤单状态结果仍以后续委托回报/撤单错误回报为准。
        """
        try:
            logger.debug(
                "[Callback] cancel_async_response seq=%s order_id=%s cancel_result=%s error=%s",
                getattr(response, "seq", 0),
                getattr(response, "order_id", 0),
                getattr(response, "cancel_result", "?"),
                getattr(response, "error_msg", ""),
            )
        except Exception as e:
            logger.error("[Callback] on_cancel_order_stock_async_response 异常: %s", e, exc_info=True)

    def on_account_status(self, status) -> None:
        """处理账户状态变化事件。"""
        try:
            account_id = str(getattr(status, "account_id", "?") or "?")
            acc_status = str(getattr(status, "status", "?") or "?")
            logger.info("[Callback] 账户状态变化 account=%s status=%s", account_id, acc_status)
        except Exception as e:
            logger.error("[Callback] on_account_status 异常: %s", e, exc_info=True)

    def on_stock_position(self, position) -> None:
        """持仓推送回调。

        当前持仓以成交回报链路为主进行维护，这里先保留日志，方便后续比对。
        """
        try:
            logger.debug(
                "[Callback] on_stock_position code=%s volume=%s can_use=%s",
                self._xt_to_code(str(getattr(position, "stock_code", "") or "")),
                getattr(position, "volume", 0),
                getattr(position, "can_use_volume", 0),
            )
        except Exception as e:
            logger.error("[Callback] on_stock_position 异常: %s", e, exc_info=True)

    # ------------------------------------------------------------------ Private

    @staticmethod
    def _map_order_status(xt_status) -> OrderStatus:
        """将 xtquant 原始订单状态码映射为内部 `OrderStatus`。"""
        mapping = {
            48: OrderStatus.UNREPORTED,
            49: OrderStatus.WAIT_REPORTING,
            50: OrderStatus.REPORTED,
            51: OrderStatus.REPORTED_CANCEL,
            52: OrderStatus.PARTSUCC_CANCEL,
            53: OrderStatus.PART_CANCEL,
            54: OrderStatus.CANCELED,
            55: OrderStatus.PART_SUCC,
            56: OrderStatus.SUCCEEDED,
            57: OrderStatus.JUNK,
            255: OrderStatus.UNKNOWN,
        }
        return mapping.get(int(xt_status or 0), OrderStatus.UNKNOWN)

    @staticmethod
    def _xt_to_code(xt_code: str) -> str:
        """把 xtquant 代码格式转换为项目内部 6 位证券代码。"""
        return xt_code.split(".")[0] if "." in xt_code else xt_code

    @staticmethod
    def _extract_public_attrs(obj) -> Dict[str, Any]:
        """提取对象上的公开属性，用于保存原始 xtquant 快照。

        这样做的目的是在不强依赖 xtquant 内部类定义的前提下，
        为后续问题排查保留更多原始上下文。
        """
        result: Dict[str, Any] = {}
        for name in dir(obj):
            if name.startswith("_"):
                continue
            try:
                value = getattr(obj, name)
            except Exception:
                continue
            if callable(value):
                continue
            result[name] = value
        return result

    def _build_xt_order_payload(self, order) -> Dict[str, Any]:
        """构造包含完整 XtOrder 信息的标准化字典。

        Returns:
            可直接传给 `OrderManager.update_order_status()` 的普通字典。
        """
        xt_stock_code = str(getattr(order, "stock_code", "") or "")
        return {
            "account_type": int(getattr(order, "account_type", 0) or 0),
            "account_id": str(getattr(order, "account_id", "") or ""),
            "xt_stock_code": xt_stock_code,
            "stock_code": self._xt_to_code(xt_stock_code),
            "order_id": int(getattr(order, "order_id", 0) or 0),
            "order_sysid": str(getattr(order, "order_sysid", "") or ""),
            "order_time": int(getattr(order, "order_time", 0) or 0),
            "order_type": int(getattr(order, "order_type", 0) or 0),
            "order_volume": int(getattr(order, "order_volume", 0) or 0),
            "price_type": int(getattr(order, "price_type", 0) or 0),
            "price": float(getattr(order, "price", 0.0) or 0.0),
            "traded_volume": int(getattr(order, "traded_volume", 0) or 0),
            "traded_price": float(getattr(order, "traded_price", 0.0) or 0.0),
            "traded_amount": float(getattr(order, "traded_amount", 0.0) or 0.0),
            "order_status": int(getattr(order, "order_status", 0) or 0),
            "status_msg": str(getattr(order, "status_msg", "") or ""),
            "strategy_name": str(getattr(order, "strategy_name", "") or ""),
            "order_remark": str(getattr(order, "order_remark", "") or ""),
            "direction": int(getattr(order, "direction", 0) or 0),
            "offset_flag": int(getattr(order, "offset_flag", 0) or 0),
            "secu_account": str(getattr(order, "secu_account", "") or ""),
            "instrument_name": str(getattr(order, "instrument_name", "") or ""),
            "xt_fields": self._extract_public_attrs(order),
        }


__all__ = ["MyXtQuantTraderCallback"]
