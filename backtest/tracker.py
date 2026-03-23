"""回测指标追踪器。

第一阶段负责：
1. 记录订单和成交。
2. 记录净值曲线。
3. 计算基础绩效指标。
"""

from __future__ import annotations

from collections import defaultdict
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime
from math import sqrt
from typing import Dict, List

from backtest.models import BacktestConfig, BacktestResult, ClosedTrade, DailyReturnPoint, EquityPoint
from config.enums import OrderDirection
from trading.models import Order, TradeRecord


@dataclass
class _OpenLot:
    """回测统计阶段内部使用的未平仓买入批次。"""

    strategy_id: str
    strategy_name: str
    stock_code: str
    entry_time: datetime
    quantity: int
    unit_cost: float
    entry_price: float
    buy_fee: float


class BacktestTracker:
    """第一阶段回测结果追踪器。"""

    def __init__(self, config: BacktestConfig):
        self._config = config
        self._equity_curve: List[EquityPoint] = []
        self._orders: List[Order] = []
        self._trades: List[TradeRecord] = []

    def on_order(self, order: Order) -> None:
        """记录订单变化。"""
        self._orders.append(deepcopy(order))

    def on_trade(self, trade: TradeRecord) -> None:
        """记录成交事件。"""
        self._trades.append(deepcopy(trade))

    def capture_equity(self, data_time: datetime, cash: float, market_value: float) -> None:
        """记录一个净值时点。"""
        equity = float(cash) + float(market_value)
        self._equity_curve.append(
            EquityPoint(
                data_time=data_time,
                cash=float(cash),
                market_value=float(market_value),
                equity=equity,
                drawdown=0.0,
            )
        )

    def build_result(self, strategy_snapshots=None) -> BacktestResult:
        """汇总回测结果。"""
        equity_curve = self._build_drawdown_curve()
        daily_returns = self._build_daily_returns(equity_curve)
        trade_stats = self._build_trade_statistics()
        metrics = self._build_metrics(equity_curve, daily_returns, trade_stats)
        return BacktestResult(
            config=self._config,
            metrics=metrics,
            equity_curve=equity_curve,
            daily_returns=daily_returns,
            closed_trades=trade_stats["closed_trades"],
            orders=[self._serialize_order(order) for order in self._orders],
            trades=[self._serialize_trade(trade) for trade in self._trades],
            strategy_snapshots=list(strategy_snapshots or []),
        )

    def _build_drawdown_curve(self, ) -> List[EquityPoint]:
        peak = 0.0
        points: List[EquityPoint] = []
        for point in self._equity_curve:
            peak = max(peak, point.equity)
            drawdown = 0.0 if peak <= 0 else (peak - point.equity) / peak
            points.append(
                EquityPoint(
                    data_time=point.data_time,
                    cash=point.cash,
                    market_value=point.market_value,
                    equity=point.equity,
                    drawdown=drawdown,
                )
            )
        return points

    def _build_daily_returns(self, equity_curve: List[EquityPoint]) -> List[DailyReturnPoint]:
        """把分钟级净值曲线收敛为逐日净值和逐日收益。"""
        last_point_by_day: dict[str, EquityPoint] = {}
        for point in equity_curve:
            trade_day = point.data_time.strftime("%Y-%m-%d")
            last_point_by_day[trade_day] = point

        previous_equity = 0.0
        daily_returns: List[DailyReturnPoint] = []
        for trade_day in sorted(last_point_by_day.keys()):
            point = last_point_by_day[trade_day]
            daily_return = 0.0 if previous_equity <= 0 else (point.equity - previous_equity) / previous_equity
            daily_returns.append(
                DailyReturnPoint(
                    trade_day=trade_day,
                    equity=point.equity,
                    daily_return=daily_return,
                )
            )
            previous_equity = point.equity
        return daily_returns

    def _build_metrics(self, equity_curve: List[EquityPoint], daily_returns: List[DailyReturnPoint], trade_stats: Dict[str, object]) -> Dict[str, float]:
        if not equity_curve:
            return {}

        starting_equity = float(self._config.initial_cash)
        ending_equity = equity_curve[-1].equity
        total_return = 0.0 if starting_equity <= 0 else (ending_equity - starting_equity) / starting_equity
        max_drawdown = max((point.drawdown for point in equity_curve), default=0.0)
        total_fee = sum(float(trade.total_fee or 0.0) for trade in self._trades)
        trade_count = len(self._trades)
        order_count = len(self._orders)

        first_time = equity_curve[0].data_time
        last_time = equity_curve[-1].data_time
        total_days = max((last_time - first_time).total_seconds() / 86400.0, 1.0)
        annualized_return = (1 + total_return) ** (365.0 / total_days) - 1 if starting_equity > 0 and ending_equity > 0 else 0.0

        returns = [point.daily_return for point in daily_returns[1:] if point.equity > 0]
        avg_return = sum(returns) / len(returns) if returns else 0.0
        variance = sum((value - avg_return) ** 2 for value in returns) / len(returns) if returns else 0.0
        sharpe = (avg_return / sqrt(variance)) * sqrt(252) if variance > 0 else 0.0

        day_win_count = sum(1 for item in daily_returns[1:] if item.daily_return > 0)
        day_loss_count = sum(1 for item in daily_returns[1:] if item.daily_return < 0)
        best_day_return = max((item.daily_return for item in daily_returns[1:]), default=0.0)
        worst_day_return = min((item.daily_return for item in daily_returns[1:]), default=0.0)

        return {
            "starting_equity": starting_equity,
            "ending_equity": ending_equity,
            "total_return": total_return,
            "annualized_return": annualized_return,
            "max_drawdown": max_drawdown,
            "trade_count": float(trade_count),
            "order_count": float(order_count),
            "total_fee": total_fee,
            "trading_days": float(len(daily_returns)),
            "avg_daily_return": avg_return,
            "best_day_return": best_day_return,
            "worst_day_return": worst_day_return,
            "daily_win_rate": (day_win_count / (day_win_count + day_loss_count)) if (day_win_count + day_loss_count) > 0 else 0.0,
            "closed_trade_count": float(trade_stats["closed_trade_count"]),
            "winning_trade_count": float(trade_stats["winning_trade_count"]),
            "losing_trade_count": float(trade_stats["losing_trade_count"]),
            "win_rate": float(trade_stats["win_rate"]),
            "avg_win_pnl": float(trade_stats["avg_win_pnl"]),
            "avg_loss_pnl": float(trade_stats["avg_loss_pnl"]),
            "profit_loss_ratio": float(trade_stats["profit_loss_ratio"]),
            "profit_factor": float(trade_stats["profit_factor"]),
            "total_realized_pnl": float(trade_stats["total_realized_pnl"]),
            "sharpe": sharpe,
        }

    def _build_trade_statistics(self) -> Dict[str, object]:
        """按成交配对计算更贴近实盘复盘的收益统计。"""
        open_lots: dict[tuple[str, str], list[_OpenLot]] = defaultdict(list)
        closed_trade_pnls: List[float] = []
        closed_trades: List[ClosedTrade] = []

        trades = sorted(
            self._trades,
            key=lambda item: (
                item.trade_time,
                item.xt_traded_time,
                item.trade_id,
            ),
        )
        for trade in trades:
            quantity = int(trade.quantity or 0)
            if quantity <= 0:
                continue

            trade_amount = float(trade.amount or (trade.price * quantity))
            total_fee = float(trade.total_fee or 0.0)
            key = (trade.strategy_id, trade.stock_code)

            if trade.direction == OrderDirection.BUY:
                unit_cost = (trade_amount + total_fee) / quantity
                open_lots[key].append(
                    _OpenLot(
                        strategy_id=trade.strategy_id,
                        strategy_name=trade.strategy_name,
                        stock_code=trade.stock_code,
                        entry_time=trade.trade_time,
                        quantity=quantity,
                        unit_cost=unit_cost,
                        entry_price=float(trade.price or 0.0),
                        buy_fee=total_fee,
                    )
                )
                continue

            remaining = quantity
            sell_unit_net = (trade_amount - total_fee) / quantity
            lots = open_lots[key]
            while remaining > 0 and lots:
                lot = lots[0]
                matched = min(remaining, lot.quantity)
                entry_amount = matched * lot.entry_price
                exit_amount = matched * float(trade.price or 0.0)
                allocated_buy_fee = lot.buy_fee * (matched / (lot.quantity or matched)) if lot.buy_fee > 0 else 0.0
                allocated_sell_fee = total_fee * (matched / quantity) if total_fee > 0 else 0.0
                pnl = matched * (sell_unit_net - lot.unit_cost)
                holding_days = max((trade.trade_time - lot.entry_time).total_seconds() / 86400.0, 0.0)
                return_ratio = 0.0 if entry_amount + allocated_buy_fee <= 0 else pnl / (entry_amount + allocated_buy_fee)

                closed_trade = ClosedTrade(
                    strategy_id=lot.strategy_id,
                    strategy_name=lot.strategy_name,
                    stock_code=lot.stock_code,
                    entry_time=lot.entry_time,
                    exit_time=trade.trade_time,
                    quantity=matched,
                    entry_price=lot.entry_price,
                    exit_price=float(trade.price or 0.0),
                    entry_amount=entry_amount,
                    exit_amount=exit_amount,
                    buy_fee=allocated_buy_fee,
                    sell_fee=allocated_sell_fee,
                    pnl=pnl,
                    return_ratio=return_ratio,
                    holding_days=holding_days,
                )
                closed_trades.append(closed_trade)
                closed_trade_pnls.append(pnl)

                remaining -= matched
                original_lot_quantity = lot.quantity
                lot.quantity -= matched
                if original_lot_quantity > 0 and lot.buy_fee > 0:
                    lot.buy_fee = max(0.0, lot.buy_fee - allocated_buy_fee)
                if lot.quantity <= 0:
                    lots.pop(0)

        winning = [value for value in closed_trade_pnls if value > 0]
        losing = [value for value in closed_trade_pnls if value < 0]
        avg_win_pnl = sum(winning) / len(winning) if winning else 0.0
        avg_loss_abs = abs(sum(losing) / len(losing)) if losing else 0.0
        total_profit = sum(winning)
        total_loss_abs = abs(sum(losing))
        profit_loss_ratio = avg_win_pnl / avg_loss_abs if avg_loss_abs > 0 else (float("inf") if avg_win_pnl > 0 else 0.0)
        profit_factor = total_profit / total_loss_abs if total_loss_abs > 0 else (float("inf") if total_profit > 0 else 0.0)

        return {
            "closed_trade_count": float(len(closed_trade_pnls)),
            "winning_trade_count": float(len(winning)),
            "losing_trade_count": float(len(losing)),
            "win_rate": (len(winning) / len(closed_trade_pnls)) if closed_trade_pnls else 0.0,
            "avg_win_pnl": avg_win_pnl,
            "avg_loss_pnl": avg_loss_abs,
            "profit_loss_ratio": 0.0 if profit_loss_ratio == float("inf") else profit_loss_ratio,
            "profit_factor": 0.0 if profit_factor == float("inf") else profit_factor,
            "total_realized_pnl": sum(closed_trade_pnls),
            "closed_trades": closed_trades,
        }

    @staticmethod
    def _serialize_order(order: Order) -> dict:
        return {
            "order_uuid": order.order_uuid,
            "strategy_id": order.strategy_id,
            "strategy_name": order.strategy_name,
            "stock_code": order.stock_code,
            "direction": order.direction.value,
            "order_type": order.order_type.value,
            "price": order.price,
            "quantity": order.quantity,
            "amount": order.amount,
            "status": order.status.value,
            "filled_quantity": order.filled_quantity,
            "filled_amount": order.filled_amount,
            "filled_avg_price": order.filled_avg_price,
            "remark": order.remark,
            "create_time": order.create_time.isoformat() if order.create_time else "",
            "update_time": order.update_time.isoformat() if order.update_time else "",
        }

    @staticmethod
    def _serialize_trade(trade: TradeRecord) -> dict:
        return {
            "trade_id": trade.trade_id,
            "order_uuid": trade.order_uuid,
            "strategy_id": trade.strategy_id,
            "strategy_name": trade.strategy_name,
            "stock_code": trade.stock_code,
            "direction": trade.direction.value,
            "price": trade.price,
            "quantity": trade.quantity,
            "amount": trade.amount,
            "total_fee": trade.total_fee,
            "trade_time": trade.trade_time.isoformat() if trade.trade_time else "",
        }
