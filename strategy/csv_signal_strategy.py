"""基于 CSV 配置文件的示例策略。

这个示例策略的目标不是追求复杂的交易逻辑，
而是向初学者展示：
1. 如何把“外部文件配置”转换成多个 ``StrategyConfig``。
2. 如何让一个 CSV 中的每一行都对应一个独立策略实例。
3. 如何复用 ``BaseStrategy`` 已有的止损、止盈、下单链路。

CSV 表头约定如下：
- 股票代码
- 开仓价格
- 买入数量
- 止损位（百分比）
- 止盈位（百分比）

其中“止损位（百分比）”“止盈位（百分比）”支持以下写法：
- ``5``      表示 5%
- ``5%``     表示 5%
- ``0.05``   表示 5%
"""
from __future__ import annotations

import csv
from pathlib import Path
from typing import List, Optional

from core.models import TickData
from monitor.logger import get_logger
from strategy.base import BaseStrategy
from strategy.models import StrategyConfig

logger = get_logger("trade")


class CsvSignalStrategy(BaseStrategy):
    """读取 CSV 配置并生成多个单标的策略实例的示例策略。"""

    strategy_name = "CsvSignalStrategy"
    max_positions = 50
    max_total_amount = 1_000_000.0

    def __init__(self, config: StrategyConfig,
                 trade_executor=None, position_manager=None):
        """初始化 CSV 示例策略。

        每个策略实例只负责一个证券代码，
        需要的买入数量等附加参数统一放在 ``config.params`` 中。
        """
        super().__init__(config, trade_executor, position_manager)
        self._buy_quantity = int(self.config.params.get("buy_quantity", 0) or 0)
        self._csv_path = str(self.config.params.get("csv_path") or self._default_csv_path())

    def select_stocks(self) -> List[StrategyConfig]:
        """从 CSV 文件读取所有标的配置。

        返回值中的每个 ``StrategyConfig`` 都会在 ``StrategyRunner`` 中
        被创建为一个独立的策略实例，因此天然满足“一行一个标的”的需求。
        """
        csv_path = Path(self.config.params.get("csv_path") or self._default_csv_path())
        if not csv_path.exists():
            logger.warning("CsvSignalStrategy: CSV 文件不存在，跳过选股: %s", csv_path)
            return []

        configs: List[StrategyConfig] = []
        with csv_path.open("r", encoding="utf-8-sig", newline="") as fp:
            reader = csv.DictReader(fp)
            for row_no, row in enumerate(reader, start=2):
                try:
                    stock_code = self._normalize_stock_code(row.get("股票代码", ""))
                    entry_price = float(row.get("开仓价格", 0) or 0)
                    buy_quantity = int(float(row.get("买入数量", 0) or 0))
                    stop_loss_pct = self._parse_percent(row.get("止损位（百分比）", 0))
                    take_profit_pct = self._parse_percent(row.get("止盈位（百分比）", 0))

                    if not stock_code or entry_price <= 0 or buy_quantity <= 0:
                        logger.warning(
                            "CsvSignalStrategy: 第 %d 行配置无效，已跳过: %s",
                            row_no,
                            row,
                        )
                        continue

                    stop_loss_price = round(entry_price * (1 - stop_loss_pct), 3) if stop_loss_pct > 0 else 0.0
                    take_profit_price = round(entry_price * (1 + take_profit_pct), 3) if take_profit_pct > 0 else 0.0
                    configs.append(
                        StrategyConfig(
                            stock_code=stock_code,
                            entry_price=entry_price,
                            stop_loss_price=stop_loss_price,
                            take_profit_price=take_profit_price,
                            params={
                                "buy_quantity": buy_quantity,
                                "stop_loss_pct": stop_loss_pct,
                                "take_profit_pct": take_profit_pct,
                                "csv_path": str(csv_path),
                                "source_row": row_no,
                            },
                        )
                    )
                except Exception as exc:
                    logger.warning(
                        "CsvSignalStrategy: 解析第 %d 行失败，已跳过: %s; error=%s",
                        row_no,
                        row,
                        exc,
                    )
        return configs

    def on_tick(self, tick: TickData) -> Optional[dict]:
        """根据 CSV 配置生成买入信号。

        逻辑尽量保持简单：
        - 还没有持仓、也没有挂单时
        - 当前价小于等于 ``entry_price``
        - 且买入数量至少为 100 股
        则触发一次买入信号。

        止损和止盈不在这里手写，
        而是复用 ``BaseStrategy._check_risk()`` 中的通用逻辑。
        """
        if self._has_position_or_pending_order():
            return None
        if self.config.entry_price <= 0:
            return None

        quantity = int(self._buy_quantity // 100) * 100
        if quantity < 100:
            return None

        if tick.last_price <= self.config.entry_price:
            return {
                "action": "BUY",
                "price": tick.last_price,
                "quantity": quantity,
                "remark": (
                    f"CSV 开仓信号 entry={self.config.entry_price:.3f} "
                    f"qty={quantity} source={Path(self._csv_path).name}"
                ),
            }
        return None

    def _get_custom_state(self) -> dict:
        """保存 CSV 策略需要的最小自定义状态。"""
        return {
            "buy_quantity": self._buy_quantity,
            "csv_path": self._csv_path,
        }

    def _restore_custom_state(self, state: dict) -> None:
        """从快照恢复 CSV 策略的附加状态。"""
        self._buy_quantity = int(state.get("buy_quantity", self._buy_quantity) or 0)
        self._csv_path = str(state.get("csv_path", self._csv_path) or self._default_csv_path())

    def _has_position_or_pending_order(self) -> bool:
        """判断当前策略是否已有持仓或未完成订单。"""
        if self._pending_orders:
            return True
        if not self._position_mgr:
            return False
        position = self._position_mgr.get_position(self.strategy_id)
        return bool(position and int(getattr(position, "total_quantity", 0) or 0) > 0)

    @staticmethod
    def _default_csv_path() -> Path:
        """返回示例 CSV 的默认路径。"""
        return Path(__file__).resolve().parent.parent / "config" / "example_strategy_signals.csv"

    @staticmethod
    def _normalize_stock_code(value: str) -> str:
        """把 CSV 中的证券代码规范化为 6 位内部代码。"""
        text = str(value or "").strip()
        if "." in text:
            text = text.split(".")[0]
        return text

    @staticmethod
    def _parse_percent(value) -> float:
        """把多种百分比写法统一转换为小数。

        例如：
        - ``5`` -> ``0.05``
        - ``5%`` -> ``0.05``
        - ``0.05`` -> ``0.05``
        """
        if value in (None, ""):
            return 0.0
        text = str(value).strip()
        if not text:
            return 0.0
        if text.endswith("%"):
            return float(text[:-1]) / 100.0
        number = float(text)
        return number / 100.0 if number >= 1 else number


__all__ = ["CsvSignalStrategy"]
