"""兼容层：交易日工具已整合到 ``core.trading_calendar``。

保留这个文件的原因是兼容旧代码。
如果外部脚本仍在 ``import date``，它仍然可以继续工作，
只是底层实现已经全部迁移到新的核心模块中了。
"""

from core.trading_calendar import (
    TargetDate,
    add_mark_day,
    add_market_day,
    add_one_market_day,
    date_range,
    is_market_day,
    minus_one_market_day,
    shift_market_day,
)


__all__ = [
    "TargetDate",
    "add_mark_day",
    "add_market_day",
    "add_one_market_day",
    "date_range",
    "is_market_day",
    "minus_one_market_day",
    "shift_market_day",
]