"""行情数据模型"""
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


@dataclass
class TickData:
    """预处理后的 Tick 行情数据（传给策略的标准格式）"""
    stock_code: str = ""              # 6位数字代码
    last_price: float = 0.0           # 最新价
    open: float = 0.0
    high: float = 0.0
    low: float = 0.0
    pre_close: float = 0.0            # 昨收价
    volume: int = 0                   # 成交量（股）
    amount: float = 0.0               # 成交额（元）
    bid_prices: list = field(default_factory=list)    # 买一~买五价格
    bid_volumes: list = field(default_factory=list)   # 买一~买五数量
    ask_prices: list = field(default_factory=list)    # 卖一~卖五价格
    ask_volumes: list = field(default_factory=list)   # 卖一~卖五数量
    data_time: Optional[datetime] = None   # xtquant 推送的数据时间
    recv_time: Optional[datetime] = None   # 本地接收时间
    latency_ms: float = 0.0               # 延迟（毫秒）

    @property
    def bid1(self) -> float:
        """买一价"""
        return self.bid_prices[0] if self.bid_prices else 0.0

    @property
    def ask1(self) -> float:
        """卖一价"""
        return self.ask_prices[0] if self.ask_prices else 0.0

    @property
    def spread(self) -> float:
        """买卖价差"""
        return self.ask1 - self.bid1


__all__ = ["TickData"]
