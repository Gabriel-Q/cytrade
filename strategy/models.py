"""策略层共享数据模型。

本模块中的数据类主要承担两类职责：

1. 描述策略实例初始化时所需的静态配置。
2. 描述策略运行过程中需要跨交易日持久化保存的动态状态。

这些模型会被策略基类、策略运行器以及数据持久化层共同使用，因此
字段命名尽量保持清晰、稳定，便于后续自动化文档工具直接生成说明。
"""
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List

from config.enums import StrategyStatus
from position.models import PositionInfo


@dataclass
class StrategyConfig:
    """描述单个策略实例的核心配置参数。

    这些参数通常在策略创建阶段确定，随后在运行时被策略逻辑反复引用。
    当某个字段取默认值时，通常表示“不启用该约束”或“由策略自行处理”。
    """

    stock_code: str = ""  # 策略绑定的股票代码。
    entry_price: float = 0.0  # 参考开仓价；为 0 时表示不限制触发价格。
    stop_loss_price: float = 0.0  # 固定止损价；为 0 时表示不使用固定止损。
    take_profit_price: float = 0.0  # 固定止盈价；为 0 时表示不使用固定止盈。
    max_position_amount: float = 0.0  # 该标的允许占用的最大持仓金额。
    params: Dict[str, Any] = field(default_factory=dict)  # 供具体策略扩展使用的自定义参数字典。


@dataclass
class StrategySnapshot:
    """描述策略可恢复状态的持久化快照。

    策略运行过程中，除静态配置外还会产生诸如持仓、待完成订单、自定义中间
    状态等动态信息。框架在持久化时会将这些内容统一收敛到该快照对象中，便于
    在重启、跨交易日恢复时尽可能还原现场。
    """

    strategy_id: str = ""  # 策略实例唯一标识。
    strategy_name: str = ""  # 策略展示名称，便于日志和界面识别。
    stock_code: str = ""  # 该快照所属的股票代码。
    status: StrategyStatus = StrategyStatus.INITIALIZING  # 策略当前生命周期状态。
    config: StrategyConfig = field(default_factory=StrategyConfig)  # 策略初始化配置副本。
    position: PositionInfo = field(default_factory=PositionInfo)  # 当前持仓状态快照。
    pending_order_uuids: List[str] = field(default_factory=list)  # 尚未完结的内部订单 UUID 列表。
    custom_state: Dict[str, Any] = field(default_factory=dict)  # 策略自定义持久化状态。
    create_time: datetime = field(default_factory=datetime.now)  # 快照首次创建时间。
    update_time: datetime = field(default_factory=datetime.now)  # 快照最近一次更新时间。


__all__ = ["StrategyConfig", "StrategySnapshot"]
