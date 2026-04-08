"""API 路由定义。

这个模块的每个接口都尽量保持“薄路由”原则：
只负责参数接收、调用核心模块、整理返回值，不在路由里堆积业务逻辑。
"""
from datetime import datetime
from typing import List, Optional

try:
    from fastapi import APIRouter, HTTPException, Query
    _FASTAPI = True
except ImportError:
    _FASTAPI = False
    APIRouter = object
    HTTPException = Exception
    Query = lambda *a, **kw: None  # type: ignore

from web.backend.schemas import (
    StrategyInfo, PausedStrategyReconciliation, PositionDetail, PositionSummary,
    OrderInfo, TradeInfo, StrategyPositionReplay, StrategyPositionReplayStep,
    StrategyCapacityGroup, StrategyCapacityWaitingItem,
    SystemStatus, ActionResponse
)
from config.settings import Settings
from config.enums import OrderDirection
from position.manager import PositionManager
from position.models import PositionInfo
from trading.models import TradeRecord
from core.security_lookup import security_lookup
from web.backend.status_map import (
    order_status_text,
    strategy_status_text,
    order_direction_text,
    order_type_text,
)

# 这些全局变量由 `main.py` 在应用启动时注入。
# 路由模块本身不负责实例化核心对象，只负责读取这些依赖并组织响应。
_strategy_runner = None
_position_manager = None
_order_manager = None
_data_manager = None
_connection_manager = None
_trade_executor = None
_ws_manager = None
_data_subscription = None
_settings = Settings()


def _resolve_stock_name(stock_code: str, fallback: str = "") -> str:
    """统一解析证券名称，优先使用已有回报字段，再回退 xtdata。"""
    resolved = security_lookup.get_name(stock_code, fallback=fallback)
    if resolved:
        return resolved

    for candidate in (
        _resolve_stock_name_from_connection(stock_code),
        _resolve_stock_name_from_storage(stock_code),
    ):
        if candidate:
            return security_lookup.prime_name(stock_code, candidate)

    return ""


def _extract_name_from_payload(payload) -> str:
    """从对象或字典中提取常见的证券名称字段。"""
    if payload is None:
        return ""
    if isinstance(payload, dict):
        for key in ("instrument_name", "stock_name", "name", "InstrumentName"):
            value = str(payload.get(key, "") or "").strip()
            if value:
                return value
        return ""

    for attr in ("instrument_name", "stock_name", "name", "InstrumentName"):
        value = str(getattr(payload, attr, "") or "").strip()
        if value:
            return value
    return ""


def _resolve_stock_name_from_connection(stock_code: str) -> str:
    """从当前账户持仓查询中补齐证券名称。"""
    if not _connection_manager:
        return ""
    try:
        position = _connection_manager.query_stock_position(stock_code)
    except Exception:
        return ""
    return _extract_name_from_payload(position)


def _resolve_stock_name_from_storage(stock_code: str) -> str:
    """从已持久化的订单/成交记录里补齐证券名称。"""
    if not _data_manager:
        return ""

    normalized_code = str(stock_code or "").strip()
    if not normalized_code:
        return ""

    for row in _data_manager.query_orders() or []:
        if str(row.get("stock_code", "") or "").strip() != normalized_code:
            continue
        name = _extract_name_from_payload(row)
        if name:
            return name

    for row in _data_manager.query_trades() or []:
        if str(row.get("stock_code", "") or "").strip() != normalized_code:
            continue
        name = _extract_name_from_payload(row)
        if name:
            return name

    return ""


def _format_strategy_name(strategy_name: str, strategy_id: str) -> str:
    """给策略名称附带策略 ID，便于前端区分同名策略。"""
    name = str(strategy_name or "").strip()
    sid = str(strategy_id or "").strip()
    if not sid:
        return name
    short_sid = sid[-5:]
    if not name:
        return short_sid
    suffix = f" [{short_sid}]"
    if name.endswith(suffix):
        return name
    return f"{name}{suffix}"


def _format_trade_time(traded_time: int | str | None, trade_time: str | None) -> str:
    """把成交时间统一格式化为前端可直接展示的字符串。"""
    digits = "".join(ch for ch in str(traded_time or "") if ch.isdigit())
    if len(digits) in (10, 13):
        try:
            ts = int(digits)
            if len(digits) == 13:
                ts = ts / 1000
            return datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M:%S")
        except (TypeError, ValueError, OSError):
            pass
    if len(digits) >= 14:
        return (
            f"{digits[:4]}-{digits[4:6]}-{digits[6:8]} "
            f"{digits[8:10]}:{digits[10:12]}:{digits[12:14]}"
        )
    if len(digits) >= 8:
        return f"{digits[:4]}-{digits[4:6]}-{digits[6:8]}"

    text = str(trade_time or "").strip()
    if not text:
        return ""
    if "T" in text:
        return text.replace("T", " ")[:19]

    date_digits = "".join(ch for ch in text if ch.isdigit())
    if len(date_digits) >= 8:
        return f"{date_digits[:4]}-{date_digits[4:6]}-{date_digits[6:8]}"
    return text


def _build_strategy_info(strategy, pos=None, capacity_used_override: int | None = None) -> StrategyInfo:
    """统一组装策略响应对象。"""
    raw_create_time = getattr(strategy, "_create_time", "")
    if isinstance(raw_create_time, datetime):
        create_time = raw_create_time.isoformat()
    elif isinstance(raw_create_time, str):
        create_time = raw_create_time
    else:
        create_time = ""

    strategy_cls = type(strategy)
    capacity_config_method = getattr(strategy_cls, "capacity_config", None)
    if callable(capacity_config_method):
        raw_capacity = capacity_config_method() or {}
    else:
        raw_capacity = {}

    capacity_enabled = bool(raw_capacity.get("enabled", False))
    capacity_limit = int(raw_capacity.get("limit", 0) or 0) if capacity_enabled else 0
    capacity_wait_reason = str(raw_capacity.get("wait_reason", "") or "") if capacity_enabled else ""

    if capacity_enabled and capacity_used_override is not None:
        capacity_used = max(0, int(capacity_used_override or 0))
    else:
        active_count_method = getattr(strategy_cls, "active_position_slot_count", None)
        if capacity_enabled and callable(active_count_method):
            try:
                capacity_used = max(0, int(active_count_method() or 0))
            except Exception:
                capacity_used = 0
        else:
            capacity_used = 0

    occupies_method = getattr(strategy, "occupies_position_slot", None)
    if capacity_enabled and callable(occupies_method):
        try:
            capacity_occupying = bool(occupies_method())
        except Exception:
            capacity_occupying = False
    else:
        capacity_occupying = False

    waiting_method = getattr(strategy, "is_waiting_for_position_slot", None)
    if capacity_enabled and callable(waiting_method):
        try:
            capacity_waiting = bool(waiting_method())
        except Exception:
            capacity_waiting = False
    else:
        capacity_waiting = False

    if capacity_waiting:
        capacity_occupying = False

    capacity_remaining = max(capacity_limit - capacity_used, 0) if capacity_enabled else 0

    return StrategyInfo(
        strategy_id=strategy.strategy_id,
        strategy_name=_format_strategy_name(strategy.strategy_name, strategy.strategy_id),
        strategy_type=str(getattr(strategy, "strategy_name", "") or strategy_cls.__name__),
        stock_code=strategy.stock_code,
        stock_name=_resolve_stock_name(strategy.stock_code),
        status=strategy.status.value,
        status_text=strategy_status_text(strategy.status.value),
        pause_reason=str(getattr(strategy, "get_pause_reason", lambda: "")() or ""),
        unrealized_pnl=pos.unrealized_pnl if pos else 0.0,
        realized_pnl=pos.realized_pnl if pos else 0.0,
        total_quantity=pos.total_quantity if pos else 0,
        avg_cost=pos.avg_cost if pos else 0.0,
        current_price=pos.current_price if pos else 0.0,
        create_time=create_time,
        capacity={
            "enabled": capacity_enabled,
            "limit": capacity_limit,
            "used": capacity_used,
            "remaining": capacity_remaining,
            "occupying": capacity_occupying,
            "waiting": capacity_waiting,
            "wait_reason": capacity_wait_reason,
        },
    )


def _collect_strategy_infos() -> list[StrategyInfo]:
    """返回当前全部策略的接口视图。"""
    if not _strategy_runner:
        return []

    strategies = list(_strategy_runner.get_all_strategies())
    capacity_usage_by_class = {}
    for strategy in strategies:
        strategy_cls = type(strategy)
        capacity_config_method = getattr(strategy_cls, "capacity_config", None)
        raw_capacity = capacity_config_method() if callable(capacity_config_method) else {}
        if not bool((raw_capacity or {}).get("enabled", False)):
            continue
        if strategy_cls not in capacity_usage_by_class:
            capacity_usage_by_class[strategy_cls] = 0
        occupies_method = getattr(strategy, "occupies_position_slot", None)
        waiting_method = getattr(strategy, "is_waiting_for_position_slot", None)
        try:
            waiting = bool(waiting_method()) if callable(waiting_method) else False
        except Exception:
            waiting = False
        try:
            occupying = bool(occupies_method()) if callable(occupies_method) else False
        except Exception:
            occupying = False
        if occupying and not waiting:
            capacity_usage_by_class[strategy_cls] += 1

    result = []
    for strategy in strategies:
        pos = _get_position_for_strategy(strategy.strategy_id)
        result.append(_build_strategy_info(strategy, pos, capacity_usage_by_class.get(type(strategy))))
    return result


def _summarize_strategy_capacity(strategy_infos: list[StrategyInfo]) -> list[StrategyCapacityGroup]:
    """按策略类型聚合容量概览。"""
    groups = {}
    for item in strategy_infos:
        capacity = dict(getattr(item, "capacity", {}) or {})
        if not bool(capacity.get("enabled", False)):
            continue
        strategy_type = str(getattr(item, "strategy_type", "") or getattr(item, "strategy_name", "") or "")
        if strategy_type not in groups:
            groups[strategy_type] = {
                "strategy_type": strategy_type,
                "instance_count": 0,
                "used": int(capacity.get("used", 0) or 0),
                "limit": int(capacity.get("limit", 0) or 0),
                "remaining": int(capacity.get("remaining", 0) or 0),
                "occupying_count": 0,
                "waiting_count": 0,
                "waiting_items": [],
            }
        group = groups[strategy_type]
        group["instance_count"] += 1
        group["used"] = int(capacity.get("used", group["used"]) or 0)
        group["limit"] = int(capacity.get("limit", group["limit"]) or 0)
        group["remaining"] = int(capacity.get("remaining", group["remaining"]) or 0)
        if bool(capacity.get("occupying", False)):
            group["occupying_count"] += 1
        if bool(capacity.get("waiting", False)):
            group["waiting_count"] += 1
            group["waiting_items"].append(StrategyCapacityWaitingItem(
                strategy_id=str(item.strategy_id),
                strategy_name=str(item.strategy_name),
                stock_code=str(item.stock_code),
                stock_name=str(item.stock_name or ""),
            ))

    ordered_groups = sorted(groups.values(), key=lambda row: row["strategy_type"])
    return [StrategyCapacityGroup(**row) for row in ordered_groups]


def _format_order_info_from_row(row: dict) -> OrderInfo:
    """把 SQLite 中的订单记录转换为 API 响应对象。"""
    direction = str(row.get("direction", "") or "")
    order_type = str(row.get("order_type", "") or "")
    stock_code = str(row.get("stock_code", "") or "")
    submitted_at = str(row.get("create_time", "") or "")
    reported_price = float(row.get("price", 0.0) or 0.0)
    submitted_price = 0.0 if order_type == "MARKET" else reported_price
    display_price_text = "最新价" if order_type == "MARKET" else f"{submitted_price:.3f}"
    return OrderInfo(
        order_uuid=str(row.get("order_uuid", "") or ""),
        xt_order_id=int(row.get("xt_order_id", 0) or 0),
        account_type=int(row.get("account_type", 0) or 0),
        account_id=str(row.get("account_id", "") or ""),
        strategy_id=str(row.get("strategy_id", "") or ""),
        strategy_name=_format_strategy_name(
            str(row.get("strategy_name", "") or ""),
            str(row.get("strategy_id", "") or ""),
        ),
        stock_code=stock_code,
        stock_name=_resolve_stock_name(stock_code, str(row.get("instrument_name", "") or "")),
        xt_stock_code=str(row.get("xt_stock_code", "") or ""),
        direction=direction,
        direction_text=order_direction_text(direction),
        order_type=order_type,
        order_type_text=order_type_text(order_type),
        xt_order_type=int(row.get("xt_order_type", 0) or 0),
        price_type=int(row.get("price_type", 0) or 0),
        price=reported_price,
        submitted_price=submitted_price,
        reported_price=reported_price,
        display_price_text=display_price_text,
        quantity=int(row.get("quantity", 0) or 0),
        status=str(row.get("status", "") or ""),
        status_text=order_status_text(str(row.get("status", "") or "")),
        cancellable=False,
        xt_order_status=int(row.get("xt_order_status", 0) or 0),
        status_msg=str(row.get("status_msg", "") or ""),
        order_sysid=str(row.get("order_sysid", "") or ""),
        order_time=int(row.get("order_time", 0) or 0),
        xt_direction=int(row.get("xt_direction", 0) or 0),
        offset_flag=int(row.get("offset_flag", 0) or 0),
        secu_account=str(row.get("secu_account", "") or ""),
        instrument_name=str(row.get("instrument_name", "") or ""),
        filled_quantity=int(row.get("filled_quantity", 0) or 0),
        filled_avg_price=float(row.get("filled_avg_price", 0.0) or 0.0),
        filled_amount=float(row.get("filled_amount", 0.0) or 0.0),
        commission=float(row.get("commission", 0.0) or 0.0),
        buy_commission=float(row.get("buy_commission", 0.0) or 0.0),
        sell_commission=float(row.get("sell_commission", 0.0) or 0.0),
        stamp_tax=float(row.get("stamp_tax", 0.0) or 0.0),
        total_fee=float(row.get("total_fee", row.get("commission", 0.0)) or 0.0),
        remark=str(row.get("remark", "") or ""),
        xt_fields={},
        submitted_at=submitted_at,
        create_time=submitted_at,
        update_time=str(row.get("update_time", "") or ""),
    )


def _format_order_info_from_object(order) -> OrderInfo:
    """把内存中的订单对象转换为 API 响应对象。"""
    stock_name = _resolve_stock_name(order.stock_code, getattr(order, "instrument_name", ""))
    order_type = order.order_type.value
    submitted_at = order.create_time.isoformat()
    reported_price = float(getattr(order, "price", 0.0) or 0.0)
    submitted_price = 0.0 if order_type == "MARKET" else reported_price
    display_price_text = "最新价" if order_type == "MARKET" else f"{submitted_price:.3f}"
    return OrderInfo(
        order_uuid=order.order_uuid,
        xt_order_id=order.xt_order_id,
        account_type=getattr(order, "account_type", 0),
        account_id=getattr(order, "account_id", ""),
        strategy_id=order.strategy_id,
        strategy_name=_format_strategy_name(order.strategy_name, order.strategy_id),
        stock_code=order.stock_code,
        stock_name=stock_name,
        xt_stock_code=getattr(order, "xt_stock_code", ""),
        direction=order.direction.value,
        direction_text=order_direction_text(order.direction.value),
        order_type=order_type,
        order_type_text=order_type_text(order_type),
        xt_order_type=getattr(order, "xt_order_type", 0),
        price_type=getattr(order, "price_type", 0),
        price=reported_price,
        submitted_price=submitted_price,
        reported_price=reported_price,
        display_price_text=display_price_text,
        quantity=order.quantity,
        status=order.status.value,
        status_text=order_status_text(order.status.value),
        cancellable=bool(order.is_active()),
        xt_order_status=getattr(order, "xt_order_status", 0),
        status_msg=getattr(order, "status_msg", ""),
        order_sysid=getattr(order, "order_sysid", ""),
        order_time=getattr(order, "order_time", 0),
        xt_direction=getattr(order, "xt_direction", 0),
        offset_flag=getattr(order, "offset_flag", 0),
        secu_account=getattr(order, "secu_account", ""),
        instrument_name=getattr(order, "instrument_name", ""),
        filled_quantity=order.filled_quantity,
        filled_avg_price=order.filled_avg_price,
        filled_amount=order.filled_amount,
        commission=order.commission,
        buy_commission=getattr(order, "buy_commission", 0.0),
        sell_commission=getattr(order, "sell_commission", 0.0),
        stamp_tax=getattr(order, "stamp_tax", 0.0),
        total_fee=getattr(order, "total_fee", order.commission),
        remark=order.remark,
        xt_fields=dict(getattr(order, "xt_fields", {}) or {}),
        submitted_at=submitted_at,
        create_time=submitted_at,
        update_time=order.update_time.isoformat(),
    )


def _format_sync_action_message(summary: dict) -> str:
    """把主动同步结果整理成前端可直接展示的消息。"""
    return (
        "主动同步完成："
        f"补录成交 {int(summary.get('trades_synced', 0) or 0)} 笔，"
        f"修正委托 {int(summary.get('orders_synced', 0) or 0)} 笔，"
        f"恢复终态 {int(summary.get('state_recovered', 0) or 0)} 笔"
    )


def _load_orders_for_api(strategy_id: Optional[str] = None) -> list[OrderInfo]:
    """合并数据库历史订单与内存最新状态。"""
    merged: dict[str, OrderInfo] = {}
    ordered_ids: list[str] = []

    if _data_manager:
        for row in _data_manager.query_orders(strategy_id=strategy_id) or []:
            item = _format_order_info_from_row(row)
            merged[item.order_uuid] = item
            ordered_ids.append(item.order_uuid)

    memory_orders = []
    if _order_manager:
        memory_orders = (
            _order_manager.get_orders_by_strategy(strategy_id)
            if strategy_id else list(_order_manager._orders.values())
        )

    for order in memory_orders:
        item = _format_order_info_from_object(order)
        if item.order_uuid not in merged:
            ordered_ids.append(item.order_uuid)
        merged[item.order_uuid] = item

    return [merged[order_uuid] for order_uuid in ordered_ids if order_uuid in merged]


def _position_detail_from_position(position: PositionInfo) -> PositionDetail:
    """把持仓对象统一格式化为 API 响应。"""
    return PositionDetail(
        strategy_id=position.strategy_id,
        strategy_name=_format_strategy_name(position.strategy_name, position.strategy_id),
        stock_code=position.stock_code,
        stock_name=_resolve_stock_name(position.stock_code),
        total_quantity=position.total_quantity,
        sellable_base_quantity=_effective_sellable_base_quantity(position),
        available_quantity=position.available_quantity,
        is_t0=position.is_t0,
        avg_cost=position.avg_cost,
        current_price=position.current_price,
        market_value=position.market_value,
        unrealized_pnl=position.unrealized_pnl,
        unrealized_pnl_ratio=position.unrealized_pnl_ratio,
        realized_pnl=position.realized_pnl,
        total_commission=position.total_commission,
        total_buy_commission=position.total_buy_commission,
        total_sell_commission=position.total_sell_commission,
        total_stamp_tax=position.total_stamp_tax,
        total_fees=position.total_fees,
        update_time=position.update_time.isoformat(),
    )


def _position_from_row(row: dict) -> PositionInfo:
    """把 SQLite 中的持仓快照转换为内存持仓对象。"""
    position = PositionInfo(
        strategy_id=str(row.get("strategy_id", "") or ""),
        strategy_name=str(row.get("strategy_name", "") or ""),
        stock_code=str(row.get("stock_code", "") or ""),
        total_quantity=int(row.get("total_quantity", 0) or 0),
        sellable_base_quantity=int(row.get("sellable_base_quantity", row.get("available_quantity", 0)) or 0),
        available_quantity=int(row.get("available_quantity", 0) or 0),
        is_t0=bool(row.get("is_t0", 0)),
        avg_cost=float(row.get("avg_cost", 0.0) or 0.0),
        total_cost=float(row.get("total_cost", 0.0) or 0.0),
        current_price=float(row.get("current_price", 0.0) or 0.0),
        market_value=float(row.get("market_value", 0.0) or 0.0),
        unrealized_pnl=float(row.get("unrealized_pnl", 0.0) or 0.0),
        unrealized_pnl_ratio=float(row.get("unrealized_pnl_ratio", 0.0) or 0.0),
        realized_pnl=float(row.get("realized_pnl", 0.0) or 0.0),
        total_commission=float(row.get("total_commission", 0.0) or 0.0),
        total_buy_commission=float(row.get("total_buy_commission", 0.0) or 0.0),
        total_sell_commission=float(row.get("total_sell_commission", 0.0) or 0.0),
        total_stamp_tax=float(row.get("total_stamp_tax", 0.0) or 0.0),
        total_fees=float(row.get("total_fees", 0.0) or 0.0),
        update_time=datetime.fromisoformat(str(row.get("update_time", "") or datetime.now().isoformat()).replace(" ", "T")),
    )
    return PositionManager.normalize_restored_position(position)


def _effective_sellable_base_quantity(position: PositionInfo | None) -> int:
    """兼容老对象，推导接口层应展示的理论可卖基线。"""
    if not position:
        return 0
    total_quantity = max(0, int(getattr(position, "total_quantity", 0) or 0))
    available_quantity = max(0, int(getattr(position, "available_quantity", 0) or 0))
    explicit_sellable_base = max(0, int(getattr(position, "sellable_base_quantity", 0) or 0))
    return min(total_quantity, max(explicit_sellable_base, available_quantity))


def _collect_live_positions() -> list[PositionInfo]:
    """优先读取当前进程内存中的持仓。"""
    if not _position_manager:
        return []
    positions = []
    for pos in _position_manager.get_all_positions().values():
        if not _position_manager._is_managed_position(pos):
            continue
        if pos.total_quantity <= 0:
            continue
        positions.append(pos)
    return positions


def _is_managed_position_info(position: PositionInfo) -> bool:
    """判断接口层持仓对象是否属于受管策略。"""
    return bool(str(getattr(position, "strategy_id", "") or "").strip() or str(getattr(position, "strategy_name", "") or "").strip())


def _is_managed_trade_row(row: dict) -> bool:
    """判断成交记录是否具备可唯一归属的策略 ID。"""
    return bool(str(row.get("strategy_id", "") or "").strip())


def _dedupe_trade_rows(rows: list[dict]) -> list[dict]:
    """按 trade_id 去重成交记录，避免重复成交污染展示和持仓回放。"""
    deduped: list[dict] = []
    seen_trade_ids: set[str] = set()
    for row in rows or []:
        trade_id = str(row.get("trade_id", "") or row.get("traded_id", "") or "").strip()
        if trade_id:
            if trade_id in seen_trade_ids:
                continue
            seen_trade_ids.add(trade_id)
        deduped.append(row)
    return deduped


def _trade_day_from_row(row: dict) -> str:
    """提取成交所属交易日，统一成 YYYYMMDD。"""
    for field in ("traded_time", "trade_time"):
        digits = "".join(ch for ch in str(row.get(field, "") or "") if ch.isdigit())
        if len(digits) < 8:
            continue
        if len(digits) in (10, 13):
            try:
                ts = int(digits)
                if len(digits) == 13:
                    ts = ts / 1000
                return datetime.fromtimestamp(ts).strftime("%Y%m%d")
            except (TypeError, ValueError, OSError):
                continue
        trade_day = digits[:8]
        if trade_day.startswith(("19", "20")):
            return trade_day
    return ""


def _get_strategy_trade_rows(strategy_id: str) -> list[dict]:
    """读取某个策略的全部受管成交，并按时间顺序排序。"""
    if not _data_manager:
        return []
    rows = _dedupe_trade_rows([
        row for row in (_data_manager.query_trades(strategy_id=strategy_id) or [])
        if _is_managed_trade_row(row)
    ])
    return sorted(
        rows,
        key=lambda row: (
            _trade_day_from_row(row),
            int(row.get("traded_time", 0) or 0),
            str(row.get("trade_id", "") or ""),
        ),
    )


def _replay_strategy_position_from_trades(strategy_id: str) -> StrategyPositionReplay | None:
    """按成交记录回放单个策略的仓位变化，用于诊断恢复结果。"""
    trade_rows = _get_strategy_trade_rows(strategy_id)
    strategy = _strategy_runner.get_strategy(strategy_id) if _strategy_runner else None
    if not trade_rows and not strategy:
        return None

    temp_mgr = PositionManager(cost_method="moving_average")
    steps: list[StrategyPositionReplayStep] = []
    current_day = ""

    for row in trade_rows:
        trade_day = _trade_day_from_row(row)
        if trade_day and trade_day != current_day:
            temp_mgr.unlock_available_quantities(trade_day)
            current_day = trade_day

        direction = OrderDirection(str(row.get("direction", OrderDirection.BUY.value) or OrderDirection.BUY.value))
        trade = TradeRecord(
            account_type=int(row.get("account_type", 0) or 0),
            account_id=str(row.get("account_id", "") or ""),
            order_type=int(row.get("order_type", 0) or 0),
            trade_id=str(row.get("trade_id", "") or ""),
            xt_traded_time=int(row.get("traded_time", 0) or 0),
            order_uuid=str(row.get("order_uuid", "") or ""),
            xt_order_id=int(row.get("xt_order_id", 0) or 0),
            order_sysid=str(row.get("order_sysid", "") or ""),
            strategy_id=str(row.get("strategy_id", "") or ""),
            strategy_name=str(row.get("strategy_name", "") or ""),
            order_remark=str(row.get("order_remark", "") or ""),
            stock_code=str(row.get("stock_code", "") or ""),
            direction=direction,
            xt_direction=int(row.get("xt_direction", 0) or 0),
            offset_flag=int(row.get("offset_flag", 0) or 0),
            price=float(row.get("price", 0.0) or 0.0),
            quantity=int(row.get("quantity", 0) or 0),
            amount=float(row.get("amount", 0.0) or 0.0),
            commission=float(row.get("commission", 0.0) or 0.0),
            buy_commission=float(row.get("buy_commission", 0.0) or 0.0),
            sell_commission=float(row.get("sell_commission", 0.0) or 0.0),
            stamp_tax=float(row.get("stamp_tax", 0.0) or 0.0),
            total_fee=float(row.get("total_fee", row.get("commission", 0.0)) or 0.0),
            is_t0=bool(row.get("is_t0", 0)),
        )
        temp_mgr.on_trade_callback(trade)
        position = temp_mgr.get_position(strategy_id)

        steps.append(StrategyPositionReplayStep(
            trade_id=trade.trade_id,
            trade_time=_format_trade_time(trade.xt_traded_time, str(row.get("trade_time", "") or "")),
            trade_day=trade_day,
            direction=direction.value,
            direction_text=order_direction_text(direction.value),
            price=trade.price,
            quantity=trade.quantity,
            amount=trade.amount,
            order_remark=trade.order_remark,
            total_quantity=int(getattr(position, "total_quantity", 0) or 0),
            sellable_base_quantity=_effective_sellable_base_quantity(position),
            available_quantity=int(getattr(position, "available_quantity", 0) or 0),
            avg_cost=float(getattr(position, "avg_cost", 0.0) or 0.0),
            realized_pnl=float(getattr(position, "realized_pnl", 0.0) or 0.0),
            total_commission=float(getattr(position, "total_commission", 0.0) or 0.0),
        ))

    final_position = temp_mgr.get_position(strategy_id)
    if final_position and current_day:
        PositionManager.normalize_restored_position(final_position, source_trade_day=current_day)
    live_position = _get_position_for_strategy(strategy_id)
    stock_code = ""
    strategy_name = ""
    if strategy:
        stock_code = str(getattr(strategy, "stock_code", "") or "")
        strategy_name = str(getattr(strategy, "strategy_name", "") or "")
    if trade_rows:
        stock_code = stock_code or str(trade_rows[-1].get("stock_code", "") or "")
        strategy_name = strategy_name or str(trade_rows[-1].get("strategy_name", "") or "")

    return StrategyPositionReplay(
        strategy_id=strategy_id,
        strategy_name=_format_strategy_name(strategy_name, strategy_id),
        stock_code=stock_code,
        stock_name=_resolve_stock_name(stock_code),
        step_count=len(steps),
        final_total_quantity=int(getattr(final_position, "total_quantity", 0) or 0),
        final_sellable_base_quantity=_effective_sellable_base_quantity(final_position),
        final_available_quantity=int(getattr(final_position, "available_quantity", 0) or 0),
        live_total_quantity=int(getattr(live_position, "total_quantity", 0) or 0),
        live_sellable_base_quantity=_effective_sellable_base_quantity(live_position),
        live_available_quantity=int(getattr(live_position, "available_quantity", 0) or 0),
        steps=steps,
    )


def _rebuild_positions_from_trades() -> list[PositionInfo]:
    """当快照持仓缺失时，用成交记录回放重建当前持仓视图。"""
    if not _data_manager:
        return []
    rows = _dedupe_trade_rows(_data_manager.query_trades())
    if not rows:
        return []

    temp_mgr = PositionManager(cost_method="moving_average")
    sorted_rows = sorted(
        rows,
        key=lambda row: (
            _trade_day_from_row(row),
            int(row.get("traded_time", 0) or 0),
            str(row.get("trade_id", "") or ""),
        ),
    )

    current_day = ""
    for row in sorted_rows:
        trade_day = _trade_day_from_row(row)
        if trade_day and trade_day != current_day:
            temp_mgr.unlock_available_quantities(trade_day)
            current_day = trade_day
        direction = OrderDirection(str(row.get("direction", OrderDirection.BUY.value) or OrderDirection.BUY.value))
        trade = TradeRecord(
            account_type=int(row.get("account_type", 0) or 0),
            account_id=str(row.get("account_id", "") or ""),
            order_type=int(row.get("order_type", 0) or 0),
            trade_id=str(row.get("trade_id", "") or ""),
            xt_traded_time=int(row.get("traded_time", 0) or 0),
            order_uuid=str(row.get("order_uuid", "") or ""),
            xt_order_id=int(row.get("xt_order_id", 0) or 0),
            order_sysid=str(row.get("order_sysid", "") or ""),
            strategy_id=str(row.get("strategy_id", "") or ""),
            strategy_name=str(row.get("strategy_name", "") or ""),
            order_remark=str(row.get("order_remark", "") or ""),
            stock_code=str(row.get("stock_code", "") or ""),
            direction=direction,
            xt_direction=int(row.get("xt_direction", 0) or 0),
            offset_flag=int(row.get("offset_flag", 0) or 0),
            price=float(row.get("price", 0.0) or 0.0),
            quantity=int(row.get("quantity", 0) or 0),
            amount=float(row.get("amount", 0.0) or 0.0),
            commission=float(row.get("commission", 0.0) or 0.0),
            buy_commission=float(row.get("buy_commission", 0.0) or 0.0),
            sell_commission=float(row.get("sell_commission", 0.0) or 0.0),
            stamp_tax=float(row.get("stamp_tax", 0.0) or 0.0),
            total_fee=float(row.get("total_fee", row.get("commission", 0.0)) or 0.0),
            is_t0=bool(row.get("is_t0", 0)),
        )
        temp_mgr.on_trade_callback(trade)

    rebuilt = [
        pos for pos in temp_mgr.get_all_positions().values()
        if temp_mgr._is_managed_position(pos) and pos.total_quantity > 0
    ]
    if _data_manager:
        for pos in rebuilt:
            _data_manager.save_position(pos)
    return rebuilt


def _load_positions_for_api() -> list[PositionInfo]:
    """返回接口层应展示的持仓视图。"""
    live_positions = _collect_live_positions()
    if live_positions:
        return live_positions
    if _data_manager:
        stored_rows = _data_manager.query_positions()
        if stored_rows:
            stored_positions = [
                _position_from_row(row) for row in stored_rows
            ]
            managed_positions = [
                position for position in stored_positions
                if _is_managed_position_info(position)
            ]
            if managed_positions:
                return managed_positions
        rebuilt = _rebuild_positions_from_trades()
        if rebuilt:
            return rebuilt
    return []


def _get_position_for_strategy(strategy_id: str) -> PositionInfo | None:
    """按策略 ID 获取接口层应展示的持仓对象。"""
    if _position_manager:
        position = _position_manager.get_position(strategy_id)
        if position and int(getattr(position, "total_quantity", 0) or 0) > 0:
            return position
    for position in _load_positions_for_api():
        if position.strategy_id == strategy_id:
            return position
    return None


def _summarize_positions(positions: list[PositionInfo]) -> dict:
    """对持仓列表做接口所需的汇总统计。"""
    total_market = sum(pos.market_value for pos in positions)
    total_cost = sum(pos.total_cost for pos in positions)
    total_unrealized = sum(pos.unrealized_pnl for pos in positions)
    total_realized = sum(pos.realized_pnl for pos in positions)
    total_commission = sum(pos.total_commission for pos in positions)
    total_buy_commission = sum(pos.total_buy_commission for pos in positions)
    total_sell_commission = sum(pos.total_sell_commission for pos in positions)
    total_stamp_tax = sum(pos.total_stamp_tax for pos in positions)
    total_sellable_base_quantity = sum(_effective_sellable_base_quantity(pos) for pos in positions)
    total_available_quantity = sum(max(0, int(getattr(pos, "available_quantity", 0) or 0)) for pos in positions)
    return {
        "positions_count": len(positions),
        "total_market_value": total_market,
        "total_cost": total_cost,
        "total_unrealized_pnl": total_unrealized,
        "total_realized_pnl": total_realized,
        "total_commission": total_commission,
        "total_buy_commission": total_buy_commission,
        "total_sell_commission": total_sell_commission,
        "total_stamp_tax": total_stamp_tax,
        "total_fees": total_commission,
        "total_sellable_base_quantity": total_sellable_base_quantity,
        "total_available_quantity": total_available_quantity,
        "total_frozen_quantity": max(total_sellable_base_quantity - total_available_quantity, 0),
        "total_pnl": total_unrealized + total_realized,
    }

if _FASTAPI:
    router = APIRouter()
else:
    router = None


if _FASTAPI and router is not None:

    # ------------------------------------------------------------------ 策略

    @router.get("/strategies", response_model=List[StrategyInfo], tags=["策略"])
    async def get_strategies():
        """返回当前全部策略列表。"""
        return _collect_strategy_infos()

    @router.post("/strategies/maintenance/rebuild-runtime-state", response_model=ActionResponse, tags=["策略"])
    async def rebuild_runtime_state():
        """清空全部策略运行态并立即按当前实例重建。"""
        if not _strategy_runner:
            raise HTTPException(status_code=503, detail="StrategyRunner 未初始化")
        result = getattr(_strategy_runner, "rebuild_runtime_state", lambda: {"removed": 0, "persisted": 0})()
        removed = int((result or {}).get("removed", 0) or 0)
        persisted = int((result or {}).get("persisted", 0) or 0)
        return ActionResponse(
            success=True,
            message=f"已清空运行态记录 {removed} 条，并重新持久化当前策略 {persisted} 个",
        )

    @router.get("/system/capacity-summary", response_model=List[StrategyCapacityGroup], tags=["系统"])
    async def get_capacity_summary():
        """按策略类型返回容量概览。"""
        return _summarize_strategy_capacity(_collect_strategy_infos())

    @router.get("/strategies/paused-reconciliation", response_model=List[PausedStrategyReconciliation], tags=["策略"])
    async def get_paused_strategy_reconciliation():
        """返回所有暂停策略的持仓对账信息。"""
        if not _strategy_runner:
            return []
        rows = []
        for item in _strategy_runner.get_paused_strategy_reconciliation():
            rows.append(PausedStrategyReconciliation(
                strategy_id=str(item.get("strategy_id", "") or ""),
                strategy_name=_format_strategy_name(
                    str(item.get("strategy_name", "") or ""),
                    str(item.get("strategy_id", "") or ""),
                ),
                stock_code=str(item.get("stock_code", "") or ""),
                stock_name=_resolve_stock_name(str(item.get("stock_code", "") or "")),
                pause_reason=str(item.get("pause_reason", "") or ""),
                strategy_total_quantity=int(item.get("strategy_total_quantity", 0) or 0),
                strategy_sellable_base_quantity=int(item.get("strategy_sellable_base_quantity", item.get("strategy_available_quantity", 0)) or 0),
                strategy_available_quantity=int(item.get("strategy_available_quantity", 0) or 0),
                account_total_quantity=int(item.get("account_total_quantity", 0) or 0),
                account_available_quantity=int(item.get("account_available_quantity", 0) or 0),
            ))
        return rows

    @router.get("/strategies/{strategy_id}", response_model=StrategyInfo, tags=["策略"])
    async def get_strategy(strategy_id: str):
        """获取单个策略详情。"""
        if not _strategy_runner:
            raise HTTPException(status_code=503, detail="StrategyRunner 未初始化")
        s = _strategy_runner.get_strategy(strategy_id)
        if not s:
            raise HTTPException(status_code=404, detail="策略不存在")
        pos = _get_position_for_strategy(strategy_id)
        return _build_strategy_info(s, pos)

    @router.get("/strategies/{strategy_id}/position-replay", response_model=StrategyPositionReplay, tags=["策略"])
    async def get_strategy_position_replay(strategy_id: str):
        """按成交回放单个策略的仓位变化，用于排查恢复/对账问题。"""
        replay = _replay_strategy_position_from_trades(strategy_id)
        if not replay:
            raise HTTPException(status_code=404, detail="策略不存在或无可回放成交")
        return replay

    @router.post("/strategies/{strategy_id}/pause", response_model=ActionResponse, tags=["策略"])
    async def pause_strategy(strategy_id: str):
        """暂停指定策略。"""
        if not _strategy_runner:
            raise HTTPException(status_code=503, detail="StrategyRunner 未初始化")
        s = _strategy_runner.get_strategy(strategy_id)
        if not s:
            raise HTTPException(status_code=404, detail="策略不存在")
        s.pause(reason="Web 手动暂停")
        return ActionResponse(success=True, message=f"策略 {strategy_id[:8]} 已暂停")

    @router.post("/strategies/{strategy_id}/resume", response_model=ActionResponse, tags=["策略"])
    async def resume_strategy(strategy_id: str):
        """恢复指定策略。"""
        if not _strategy_runner:
            raise HTTPException(status_code=503, detail="StrategyRunner 未初始化")
        s = _strategy_runner.get_strategy(strategy_id)
        if not s:
            raise HTTPException(status_code=404, detail="策略不存在")
        s.resume()
        return ActionResponse(success=True, message=f"策略 {strategy_id[:8]} 已恢复")

    @router.post("/strategies/{strategy_id}/clear-runtime-state", response_model=ActionResponse, tags=["策略"])
    async def clear_strategy_runtime_state(strategy_id: str):
        """清空单个策略实例的持久化运行态。"""
        if not _strategy_runner:
            raise HTTPException(status_code=503, detail="StrategyRunner 未初始化")
        s = _strategy_runner.get_strategy(strategy_id)
        if not s:
            raise HTTPException(status_code=404, detail="策略不存在")
        removed = int(getattr(s, "clear_persistent_state", lambda: 0)() or 0)
        return ActionResponse(
            success=True,
            message=f"策略 {strategy_id[:8]} 已清空运行态记录 {removed} 条"
        )

    @router.post("/strategies/{strategy_id}/close", response_model=ActionResponse, tags=["策略"])
    async def close_strategy(strategy_id: str):
        """对指定策略发出强制平仓指令。"""
        if not _strategy_runner:
            raise HTTPException(status_code=503, detail="StrategyRunner 未初始化")
        s = _strategy_runner.get_strategy(strategy_id)
        if not s:
            raise HTTPException(status_code=404, detail="策略不存在")
        s.close_position(remark="Web 强制平仓")
        return ActionResponse(success=True, message=f"策略 {strategy_id[:8]} 平仓指令已发送")

    @router.post("/strategies/{strategy_id}/cancel-entry-and-release", response_model=ActionResponse, tags=["策略"])
    async def cancel_strategy_entry_and_release(strategy_id: str):
        """撤销未成交建仓单，并在安全时释放名额。"""
        if not _strategy_runner:
            raise HTTPException(status_code=503, detail="StrategyRunner 未初始化")
        result = _strategy_runner.cancel_entry_orders_and_recover(
            strategy_id,
            remark="Web 手动撤销建仓单并释放名额",
        )
        return ActionResponse(
            success=bool(result.get("success", False)),
            message=str(result.get("message", "")),
        )

    # ------------------------------------------------------------------ 持仓

    @router.get("/positions", response_model=List[PositionDetail], tags=["持仓"])
    async def get_positions():
        """获取全部持仓明细。"""
        return [_position_detail_from_position(pos) for pos in _load_positions_for_api()]

    @router.get("/positions/summary", response_model=PositionSummary, tags=["持仓"])
    async def get_position_summary():
        """获取持仓汇总统计。"""
        if _position_manager:
            live_positions = _collect_live_positions()
            if live_positions:
                return PositionSummary(**_summarize_positions(live_positions))
        positions = _load_positions_for_api()
        if not positions:
            return PositionSummary(**{k: 0 for k in PositionSummary.model_fields})
        summary = _summarize_positions(positions)
        return PositionSummary(**summary)

    # ------------------------------------------------------------------ 订单

    @router.get("/orders", response_model=List[OrderInfo], tags=["订单"])
    async def get_orders(strategy_id: Optional[str] = Query(None)):
        """获取订单列表，可按策略过滤。"""
        if not _order_manager and not _data_manager:
            return []
        return _load_orders_for_api(strategy_id=strategy_id)

    @router.get("/orders/{order_uuid}", response_model=OrderInfo, tags=["订单"])
    async def get_order(order_uuid: str):
        """获取单个订单详情。"""
        if not _order_manager and not _data_manager:
            raise HTTPException(status_code=503, detail="OrderManager 未初始化")
        o = _order_manager.get_order(order_uuid) if _order_manager else None
        if o:
            return _format_order_info_from_object(o)

        if _data_manager:
            rows = _data_manager.query_orders(order_uuids=[order_uuid])
            if rows:
                return _format_order_info_from_row(rows[0])

        raise HTTPException(status_code=404, detail="订单不存在")

    @router.post("/orders/{order_uuid}/cancel", response_model=ActionResponse, tags=["订单"])
    async def cancel_order(order_uuid: str):
        """提交指定订单的撤单请求。"""
        if not _order_manager or not _trade_executor:
            raise HTTPException(status_code=503, detail="OrderManager/TradeExecutor 未初始化")
        o = _order_manager.get_order(order_uuid)
        if not o:
            raise HTTPException(status_code=404, detail="订单不存在")
        if not o.is_active():
            return ActionResponse(success=False, message="订单已终结，无法撤单")

        # 通过 TradeExecutor 走真实撤单链路
        try:
            ok = _trade_executor.cancel_order(order_uuid, remark="Web撤单")
            if not ok:
                return ActionResponse(success=False, message=f"撤单请求失败 {order_uuid[:8]}")
            return ActionResponse(success=True, message=f"撤单请求已发送 {order_uuid[:8]}")
        except Exception as e:
            return ActionResponse(success=False, message=f"撤单失败: {str(e)}")

    # ------------------------------------------------------------------ 成交

    @router.get("/trades", response_model=List[TradeInfo], tags=["成交"])
    async def get_trades(strategy_id: Optional[str] = Query(None),
                         start_date: Optional[str] = Query(None),
                         end_date: Optional[str] = Query(None)):
        """获取成交记录列表，支持按策略和日期过滤。"""
        if not _data_manager:
            return []
        records = _dedupe_trade_rows(_data_manager.query_trades(strategy_id, start_date, end_date))
        result = []
        for t in records:
            if not _is_managed_trade_row(t):
                continue
            direction = str(t.get("direction", "") or "")
            traded_time = int(t.get("traded_time", 0) or 0)
            stock_name = _resolve_stock_name(str(t.get("stock_code", "") or ""), str(t.get("instrument_name", "") or ""))
            result.append(TradeInfo(
                trade_id=str(t.get("trade_id", "") or ""),
                xt_order_id=int(t.get("xt_order_id", 0) or 0),
                order_uuid=str(t.get("order_uuid", "") or ""),
                strategy_id=str(t.get("strategy_id", "") or ""),
                strategy_name=_format_strategy_name(
                    str(t.get("strategy_name", "") or ""),
                    str(t.get("strategy_id", "") or ""),
                ),
                stock_code=str(t.get("stock_code", "") or ""),
                stock_name=stock_name,
                account_type=int(t.get("account_type", 0) or 0),
                account_id=str(t.get("account_id", "") or ""),
                order_type=int(t.get("order_type", 0) or 0),
                traded_time=traded_time,
                order_sysid=str(t.get("order_sysid", "") or ""),
                order_trace_id=str(t.get("order_trace_id", "") or ""),
                order_remark=str(t.get("order_remark", "") or ""),
                remark=str(t.get("remark", "") or ""),
                xt_direction=int(t.get("xt_direction", 0) or 0),
                offset_flag=int(t.get("offset_flag", 0) or 0),
                direction=direction,
                direction_text=order_direction_text(direction),
                price=float(t.get("price", 0) or 0),
                quantity=int(t.get("quantity", 0) or 0),
                amount=float(t.get("amount", 0) or 0),
                commission=float(t.get("commission", 0) or 0),
                buy_commission=float(t.get("buy_commission", 0) or 0),
                sell_commission=float(t.get("sell_commission", 0) or 0),
                stamp_tax=float(t.get("stamp_tax", 0) or 0),
                total_fee=float(t.get("total_fee", t.get("commission", 0)) or 0),
                is_t0=bool(t.get("is_t0", 0)),
                trade_time=_format_trade_time(traded_time, str(t.get("trade_time", "") or "")),
            ))
        return result

    # ------------------------------------------------------------------ 系统

    @router.get("/system/status", response_model=SystemStatus, tags=["系统"])
    async def get_system_status():
        """获取系统运行状态概览。"""
        connected = _connection_manager.is_connected() if _connection_manager else False
        trading_time = _strategy_runner.is_trading_time() if _strategy_runner else False
        strategy_count = len(_strategy_runner.get_all_strategies()) if _strategy_runner else 0
        active_orders = len(_order_manager.get_active_orders()) if _order_manager else 0
        latest_data_status = (_data_subscription.get_latest_data_status()
                              if _data_subscription and hasattr(_data_subscription, "get_latest_data_status")
                              else {})
        latest_data_time = latest_data_status.get("latest_data_time")
        data_delay_ms = float(latest_data_status.get("data_delay_ms", 0.0) or 0.0)
        strategy_process_total_ms = (
            float(_strategy_runner.get_last_round_total_process_ms() or 0.0)
            if _strategy_runner and hasattr(_strategy_runner, "get_last_round_total_process_ms")
            else 0.0
        )

        try:
            # `psutil` 是可选依赖，缺失时退回 0，避免影响核心接口可用性。
            import psutil
            cpu = psutil.cpu_percent(interval=0.1)
            mem = psutil.virtual_memory().percent
        except Exception:
            cpu = mem = 0.0

        return SystemStatus(
            connected=connected,
            trading_time=trading_time,
            strategy_count=strategy_count,
            active_orders=active_orders,
            latest_data_time=(latest_data_time.isoformat() if isinstance(latest_data_time, datetime)
                              else str(latest_data_time or "")),
            data_delay_ms=data_delay_ms,
            strategy_process_total_ms=strategy_process_total_ms,
            data_latency_threshold_sec=float(_settings.DATA_LATENCY_THRESHOLD_SEC or 0.0),
            cpu_pct=cpu,
            mem_pct=mem,
            timestamp=datetime.now().isoformat(),
        )

    @router.post("/system/sync-orders-and-trades", response_model=ActionResponse, tags=["系统"])
    async def sync_orders_and_trades():
        """主动拉取一次柜台委托/成交并刷新本地状态。"""
        if not _strategy_runner:
            raise HTTPException(status_code=503, detail="StrategyRunner 未初始化")
        if not _connection_manager or not _connection_manager.is_connected():
            return ActionResponse(success=False, message="交易连接未建立，无法执行主动同步")

        summary = _strategy_runner.sync_orders_and_trades_once(reason="web_manual")
        return ActionResponse(success=True, message=_format_sync_action_message(summary))

    @router.get("/system/logs", tags=["系统"])
    async def get_logs(lines: int = Query(100)):
        """读取最近 N 行系统日志。"""
        import os
        from monitor.logger import find_latest_log_file

        log_file = find_latest_log_file("system")
        if not log_file or not os.path.exists(log_file):
            return {"logs": []}
        try:
            with open(log_file, "r", encoding="utf-8") as f:
                all_lines = f.readlines()
            return {"logs": all_lines[-lines:]}
        except Exception as e:
            return {"logs": [], "error": str(e)}
