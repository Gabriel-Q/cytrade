"""行情数据模型。

``TickData`` 是项目内部统一使用的行情对象。
无论底层行情来自 xtquant 还是测试模拟数据，最终都会整理成这个结构，
这样策略层就不需要了解底层数据源的细节差异。
"""
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


@dataclass
class TickData:
    """预处理后的 Tick 行情数据。

    这是策略层唯一需要理解的行情结构。
    """
    stock_code: str = ""              # 证券代码，统一为 6 位数字格式。
    last_price: float = 0.0           # 最新成交价。
    open: float = 0.0                 # 当日开盘价。
    high: float = 0.0                 # 当日最高价。
    low: float = 0.0                  # 当日最低价。
    pre_close: float = 0.0            # 昨日收盘价。
    volume: int = 0                   # 成交量，单位为股。
    amount: float = 0.0               # 成交额，单位为元。
    bid_prices: list = field(default_factory=list)    # 买一到买五价格列表。
    bid_volumes: list = field(default_factory=list)   # 买一到买五挂单量列表。
    ask_prices: list = field(default_factory=list)    # 卖一到卖五价格列表。
    ask_volumes: list = field(default_factory=list)   # 卖一到卖五挂单量列表。
    data_time: Optional[datetime] = None   # 数据源原始时间戳。
    recv_time: Optional[datetime] = None   # 本地接收该行情的时间。
    latency_ms: float = 0.0               # 从数据源到本地的延迟毫秒数。

    @property
    def bid1(self) -> float:
        """返回买一价。

        如果当前没有盘口数据，返回 ``0.0``，避免上层频繁判空。
        """
        return self.bid_prices[0] if self.bid_prices else 0.0

    @property
    def ask1(self) -> float:
        """返回卖一价。"""
        return self.ask_prices[0] if self.ask_prices else 0.0

    @property
    def spread(self) -> float:
        """返回买卖价差，即 ``卖一价 - 买一价``。"""
        return self.ask1 - self.bid1


__all__ = ["TickData"]
