"""证券基础信息查询工具。"""
import re
import threading

try:
    from xtquant import xtdata
    _XT_AVAILABLE = True
except ImportError:
    xtdata = None  # type: ignore
    _XT_AVAILABLE = False


class SecurityLookup:
    """按证券代码解析证券名称，并做进程内缓存。"""

    def __init__(self):
        self._lock = threading.Lock()
        self._name_cache: dict[str, str] = {}

    def get_name(self, stock_code: str, fallback: str = "") -> str:
        """返回证券名称；解析失败时退回 fallback。"""
        normalized_code = self._normalize_code(stock_code)
        fallback_name = self._normalize_name(fallback)
        if not normalized_code:
            return fallback_name

        with self._lock:
            cached = self._name_cache.get(normalized_code)
        if cached:
            return cached

        resolved = fallback_name or self._resolve_from_xtdata(normalized_code)
        if resolved:
            with self._lock:
                self._name_cache[normalized_code] = resolved
        return resolved

    def prime_name(self, stock_code: str, stock_name: str) -> str:
        """把外部已知的证券名称预热进缓存。"""
        normalized_code = self._normalize_code(stock_code)
        normalized_name = self._normalize_name(stock_name)
        if normalized_code and normalized_name:
            with self._lock:
                self._name_cache[normalized_code] = normalized_name
        return normalized_name

    def _resolve_from_xtdata(self, stock_code: str) -> str:
        if not _XT_AVAILABLE or xtdata is None:
            return ""

        xt_code = self._to_xt_code(stock_code)

        instrument_detail = getattr(xtdata, "get_instrument_detail", None)
        if callable(instrument_detail):
            try:
                detail = instrument_detail(xt_code)
                name = self._extract_name(detail)
                if name:
                    return name
            except Exception:
                pass

        get_full_tick = getattr(xtdata, "get_full_tick", None)
        if callable(get_full_tick):
            try:
                tick_map = get_full_tick([xt_code]) or {}
                tick_info = tick_map.get(xt_code) or tick_map.get(stock_code) or {}
                name = self._extract_name(tick_info)
                if name:
                    return name
            except Exception:
                pass

        return ""

    @staticmethod
    def _extract_name(payload) -> str:
        if isinstance(payload, str):
            return SecurityLookup._normalize_name(payload)
        if not isinstance(payload, dict):
            return ""
        for key in (
            "InstrumentName",
            "instrument_name",
            "instrumentName",
            "stock_name",
            "stockName",
            "name",
        ):
            value = SecurityLookup._normalize_name(payload.get(key, ""))
            if value:
                return value
        return ""

    @staticmethod
    def _normalize_name(stock_name: str) -> str:
        value = re.sub(r"\s+", " ", str(stock_name or "").strip())
        if not value:
            return ""
        if any("\u4e00" <= ch <= "\u9fff" for ch in value):
            return re.sub(r"\s+", "", value)
        return value

    @staticmethod
    def _normalize_code(stock_code: str) -> str:
        raw = str(stock_code or "").strip()
        if "." in raw:
            raw = raw.split(".", 1)[0]
        return raw

    @staticmethod
    def _to_xt_code(stock_code: str) -> str:
        code = SecurityLookup._normalize_code(stock_code)
        if not code:
            return ""
        if code.startswith(("5", "6", "9", "11")):
            return f"{code}.SH"
        return f"{code}.SZ"


security_lookup = SecurityLookup()


__all__ = ["SecurityLookup", "security_lookup"]