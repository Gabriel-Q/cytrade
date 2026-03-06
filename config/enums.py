"""
枚举类型定义
所有模块共用的枚举常量集中在这里
"""
from enum import Enum


class OrderDirection(str, Enum):
    BUY = "BUY"
    SELL = "SELL"


class OrderType(str, Enum):
    LIMIT = "LIMIT"              # 限价单（挂单）
    MARKET = "MARKET"            # 市价单（吃单）
    BY_AMOUNT = "BY_AMOUNT"      # 按金额下单
    BY_QUANTITY = "BY_QUANTITY"  # 按数量下单


class OrderStatus(str, Enum):
    PENDING = "PENDING"                          # 待提交
    SUBMITTED = "SUBMITTED"                      # 已提交
    PARTIALLY_FILLED = "PARTIALLY_FILLED"        # 部分成交
    FILLED = "FILLED"                            # 全部成交
    CANCELLED = "CANCELLED"                      # 已撤单
    REJECTED = "REJECTED"                        # 被拒绝
    FAILED = "FAILED"                            # 下单失败


class StrategyStatus(str, Enum):
    INITIALIZING = "INITIALIZING"    # 初始化中
    RUNNING = "RUNNING"              # 运行中
    PAUSED = "PAUSED"                # 暂停
    STOPPED = "STOPPED"              # 已停止（持仓已清）
    ERROR = "ERROR"                  # 异常


class AlertLevel(str, Enum):
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"


class CostMethod(str, Enum):
    MOVING_AVERAGE = "moving_average"    # 移动平均成本
    FIFO = "fifo"                        # 先进先出


class SubscriptionPeriod(str, Enum):
    TICK = "tick"
    MIN1 = "1m"
    MIN5 = "5m"


__all__ = [
    'OrderDirection', 'OrderType', 'OrderStatus',
    'StrategyStatus', 'AlertLevel', 'CostMethod', 'SubscriptionPeriod',
]
