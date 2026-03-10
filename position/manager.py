"""持仓管理模块。

本模块专门负责“成交后持仓如何变化”，不负责下单。
这样做的核心好处是：
1. 持仓状态始终以真实成交为准，而不是以委托意图为准。
2. 成本、可用数量、已实现盈亏都可以在同一处统一维护。
3. 便于后续自动化文档工具直接提取持仓口径说明。
"""
import threading
from datetime import datetime
from typing import Callable, Dict, List, Optional

from position.models import PositionInfo, FifoLot
from trading.models import TradeRecord
from config.enums import OrderDirection, CostMethod
from monitor.logger import get_logger

logger = get_logger("trade")


class PositionManager:
    """持仓管理器。

    它只根据“成交结果”更新持仓，不直接发单。
    这样可以保证持仓状态始终以真实成交为准，而不是以委托为准。
    """

    def __init__(self, cost_method: str = "moving_average", data_manager=None, fee_schedule=None):
        """初始化持仓管理器。

        Args:
            cost_method: 成本计算方法，支持移动平均法或 FIFO。
            data_manager: 可选的数据管理器，用于归档策略盈亏。
            fee_schedule: 可选的费率表，用于判断证券是否为 T+0。
        """
        # ``_positions`` 以 ``strategy_id`` 为键保存实时持仓对象。
        # 这里按“一个策略一个标的”的设计组织数据，
        # 可以避免多策略共享同一只股票时互相覆盖状态。
        self._positions: Dict[str, PositionInfo] = {}   # {strategy_id: PositionInfo}
        # ``_cost_method`` 决定卖出时采用移动平均还是 FIFO 口径。
        self._cost_method = CostMethod(cost_method)
        # ``_data_mgr`` 用于在策略结束后持久化盈亏归档信息。
        self._data_mgr = data_manager
        # ``_fee_schedule`` 主要用于判断证券是否支持 T+0。
        self._fee_schedule = fee_schedule
        # ``_lock`` 保护多线程下的持仓字典与持仓对象更新。
        self._lock = threading.Lock()

    # ------------------------------------------------------------------ 成交回调

    def on_trade_callback(self, trade: TradeRecord) -> None:
        """处理成交回报并实时更新持仓。

        这是持仓模块最核心的入口函数，通常由 `OrderManager` 在
        收到真实成交回报后调用。

        Args:
            trade: 已标准化的成交记录对象。
        """
        try:
            strategy_id = trade.strategy_id
            with self._lock:
                # 第一次收到该策略的成交时，先创建一份空持仓骨架。
                if strategy_id not in self._positions:
                    pos = PositionInfo(
                        strategy_id=strategy_id,
                        strategy_name=trade.strategy_name,
                        stock_code=trade.stock_code,
                        is_t0=self._resolve_is_t0(trade.stock_code, trade),
                    )
                    self._positions[strategy_id] = pos
                else:
                    pos = self._positions[strategy_id]
                    # 同一策略后续成交时，仍重新按最新规则刷新 T+0 属性，
                    # 这样费率表调整后，恢复出来的旧状态也能被纠正。
                    pos.is_t0 = self._resolve_is_t0(pos.stock_code, trade)

                # 买入和卖出会影响完全不同的字段，
                # 因此拆成两个私有函数分别维护，便于阅读和测试。
                if trade.direction == OrderDirection.BUY:
                    self._apply_buy(pos, trade)
                else:
                    self._apply_sell(pos, trade)

                # 成交费用统计统一在这里累计，
                # 这样无论采用哪种成本法，费用口径都保持一致。
                pos.total_buy_commission += float(getattr(trade, "buy_commission", 0.0) or 0.0)
                pos.total_sell_commission += float(getattr(trade, "sell_commission", 0.0) or 0.0)
                pos.total_stamp_tax += float(getattr(trade, "stamp_tax", 0.0) or 0.0)
                pos.total_fees += self._trade_total_fee(trade)
                pos.total_commission = pos.total_fees
                pos.update_time = datetime.now()

            logger.info(
                "PositionManager: 持仓更新 strategy=%s code=%s qty=%d avg_cost=%.3f "
                "unrealized_pnl=%.2f realized_pnl=%.2f",
                strategy_id[:8], pos.stock_code, pos.total_quantity,
                pos.avg_cost, pos.unrealized_pnl, pos.realized_pnl
            )

        except Exception as e:
            logger.error("PositionManager: on_trade_callback 异常: %s", e, exc_info=True)

    def update_price(self, stock_code: str, price: float) -> None:
        """更新指定证券的最新价格，并重算浮动盈亏。

        Args:
            stock_code: 6 位证券代码。
            price: 最新成交价或最新行情价。
        """
        with self._lock:
            for pos in self._positions.values():
                if pos.stock_code == stock_code and pos.total_quantity > 0:
                    pos.refresh_market_value(price)

    # ------------------------------------------------------------------ 查询

    def get_position(self, strategy_id: str) -> Optional[PositionInfo]:
        """按策略 ID 获取单个持仓。"""
        with self._lock:
            return self._positions.get(strategy_id)

    def get_all_positions(self) -> Dict[str, PositionInfo]:
        """返回全部持仓的浅拷贝。"""
        with self._lock:
            return dict(self._positions)

    def get_position_summary(self) -> dict:
        """返回全部持仓的汇总统计结果。

        Returns:
            一个普通字典，便于直接给 Web/API 层使用。
        """
        with self._lock:
            # 这里把所有聚合指标一次性算出，
            # 避免上层重复遍历持仓字典。
            total_market = sum(p.market_value for p in self._positions.values())
            total_cost = sum(p.total_cost for p in self._positions.values())
            total_unrealized = sum(p.unrealized_pnl for p in self._positions.values())
            total_realized = sum(p.realized_pnl for p in self._positions.values())
            total_commission = sum(p.total_commission for p in self._positions.values())
            total_buy_commission = sum(p.total_buy_commission for p in self._positions.values())
            total_sell_commission = sum(p.total_sell_commission for p in self._positions.values())
            total_stamp_tax = sum(p.total_stamp_tax for p in self._positions.values())
            return {
                "positions_count": len(self._positions),
                "total_market_value": total_market,
                "total_cost": total_cost,
                "total_unrealized_pnl": total_unrealized,
                "total_realized_pnl": total_realized,
                "total_commission": total_commission,
                "total_buy_commission": total_buy_commission,
                "total_sell_commission": total_sell_commission,
                "total_stamp_tax": total_stamp_tax,
                "total_fees": total_commission,
                "total_pnl": total_unrealized + total_realized,
            }

    def remove_position(self, strategy_id: str) -> None:
        """归档并移除指定策略的持仓。

        Args:
            strategy_id: 需要清理的策略 ID。
        """
        with self._lock:
            pos = self._positions.pop(strategy_id, None)
        if pos and self._data_mgr:
            try:
                pnl_info = {
                    "total_profit": pos.realized_pnl,
                    "total_commission": pos.total_commission,
                    "end_time": datetime.now().isoformat(),
                }
                self._data_mgr.save_strategy_pnl(
                    pos.strategy_id, pos.strategy_name, pos.stock_code, pnl_info
                )
                logger.info("PositionManager: 策略 %s 盈亏已归档", strategy_id[:8])
            except Exception as e:
                logger.error("PositionManager: 盈亏归档失败: %s", e, exc_info=True)

    def restore_position(self, strategy_id: str, position: PositionInfo) -> None:
        """从快照中恢复单个策略持仓。

        Args:
            strategy_id: 策略 ID。
            position: 从状态快照中读取出的持仓对象。
        """
        with self._lock:
            # 恢复时重新计算这些“可推导字段”，
            # 避免旧快照中的冗余值与当前规则不一致。
            position.is_t0 = self._resolve_is_t0(position.stock_code, position)
            position.available_quantity = position.total_quantity
            position.total_commission = position.total_fees or position.total_commission
            self._positions[strategy_id] = position
        logger.info(
            "PositionManager: 持仓已恢复 strategy=%s code=%s qty=%d avg_cost=%.3f",
            strategy_id[:8], position.stock_code, position.total_quantity, position.avg_cost
        )

    # ------------------------------------------------------------------ PRIVATE

    def _apply_buy(self, pos: PositionInfo, trade: TradeRecord) -> None:
        """把一笔买入成交应用到持仓对象上。

        Args:
            pos: 要更新的持仓对象。
            trade: 买入方向的成交记录。
        """
        qty = trade.quantity
        price = trade.price
        amount = trade.amount or (price * qty)
        total_fee = self._trade_total_fee(trade)

        if self._cost_method == CostMethod.MOVING_AVERAGE:
            # 移动平均法下，总成本增加，再用总成本 / 总股数得到新均价。
            pos.total_cost += amount + total_fee
            pos.total_quantity += qty
            if pos.is_t0:
                pos.available_quantity += qty
            pos.avg_cost = pos.total_cost / pos.total_quantity if pos.total_quantity > 0 else 0
        else:  # FIFO
            # FIFO 需要把每次买入拆成独立批次，卖出时再一批批扣减。
            lot_cost = (amount + total_fee) / qty if qty > 0 else price
            pos.fifo_lots.append(FifoLot(quantity=qty, cost_price=lot_cost))
            pos.total_cost += amount + total_fee
            pos.total_quantity += qty
            if pos.is_t0:
                pos.available_quantity += qty
            pos.avg_cost = pos.total_cost / pos.total_quantity if pos.total_quantity > 0 else 0

    def _apply_sell(self, pos: PositionInfo, trade: TradeRecord) -> None:
        """把一笔卖出成交应用到持仓对象上。

        Args:
            pos: 要更新的持仓对象。
            trade: 卖出方向的成交记录。
        """
        qty = trade.quantity
        price = trade.price
        amount = trade.amount or (price * qty)
        total_fee = self._trade_total_fee(trade)
        # 卖出时可真正落袋的是“成交金额减去卖出费用”。
        net_amount = amount - total_fee

        if self._cost_method == CostMethod.MOVING_AVERAGE:
            # 移动平均法：卖出成本 = 当前均价 * 卖出数量。
            cost_sold = pos.avg_cost * qty
            profit = net_amount - cost_sold
            pos.realized_pnl += profit
            pos.total_cost -= cost_sold
            pos.total_quantity -= qty
            pos.available_quantity = max(0, pos.available_quantity - qty)
            if pos.total_quantity <= 0:
                pos.total_cost = 0
                pos.avg_cost = 0
                pos.total_quantity = 0
                pos.available_quantity = 0
        else:  # FIFO
            # FIFO：从最早买入的批次开始逐批扣减，统计实际成本基础。
            remaining = qty
            cost_basis = 0.0
            while remaining > 0 and pos.fifo_lots:
                lot = pos.fifo_lots[0]
                take = min(lot.quantity, remaining)
                cost_basis += take * lot.cost_price
                lot.quantity -= take
                remaining -= take
                if lot.quantity == 0:
                    pos.fifo_lots.pop(0)
            profit = net_amount - cost_basis
            pos.realized_pnl += profit
            pos.total_quantity -= qty
            pos.available_quantity = max(0, pos.available_quantity - qty)
            pos.total_cost = sum(l.quantity * l.cost_price for l in pos.fifo_lots)
            pos.avg_cost = pos.total_cost / pos.total_quantity if pos.total_quantity > 0 else 0

    def _trade_total_fee(self, trade: TradeRecord) -> float:
        """返回一笔成交应计入持仓口径的总费用。"""
        total_fee = float(getattr(trade, "total_fee", 0.0) or 0.0)
        if total_fee > 0:
            return total_fee
        # 兼容旧数据：如果还没有拆分费用字段，则退回旧的 commission 字段。
        return float(getattr(trade, "commission", 0.0) or 0.0)

    def _resolve_is_t0(self, stock_code: str, trade_or_position) -> bool:
        """确定证券是否按 T+0 规则处理。

        优先级：
        1. 成交/持仓对象上的显式 ``is_t0`` 标记。
        2. 费率表中的证券属性配置。
        3. 最终回退为 ``False``。
        """
        explicit = getattr(trade_or_position, "is_t0", None)
        if explicit is True:
            return True
        if self._fee_schedule:
            return self._fee_schedule.is_t0_security(stock_code)
        return bool(explicit)


__all__ = ["PositionManager"]
