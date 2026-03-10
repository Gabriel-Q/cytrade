"""StrategyRunner 测试。"""
import os
import sys
import unittest
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from config.enums import StrategyStatus
from core.models import TickData
from position.models import PositionInfo
from strategy.base import BaseStrategy
from strategy.models import StrategyConfig
from strategy.runner import StrategyRunner


class DummyStrategy(BaseStrategy):
    strategy_name = "DummyStrategy"

    def on_tick(self, tick: TickData):
        return None

    def select_stocks(self):
        return [StrategyConfig(stock_code="000001")]


class TestStrategyRunner(unittest.TestCase):

    def test_start_skips_activation_on_non_trading_day(self):
        data_sub = MagicMock()
        runner = StrategyRunner(data_subscription=data_sub, strategy_classes=[])
        runner._load_state = MagicMock(return_value=False)
        runner.run_stock_selection = MagicMock()
        runner._start_scheduler = MagicMock()

        with patch.object(runner, "is_trading_day", return_value=False):
            runner.start()

        runner.run_stock_selection.assert_called_once()
        data_sub.set_data_callback.assert_called_once_with(runner.on_market_data)
        data_sub.subscribe_stocks.assert_not_called()
        self.assertEqual(runner.get_all_strategies(), [])

    def test_add_strategy_auto_starts_on_trading_day(self):
        data_sub = MagicMock()
        runner = StrategyRunner(data_subscription=data_sub)
        runner._running = True
        strategy = DummyStrategy(StrategyConfig(stock_code="000001"))

        with patch.object(runner, "is_trading_day", return_value=True):
            runner.add_strategy(strategy)

        self.assertEqual(strategy.status, StrategyStatus.RUNNING)
        data_sub.subscribe_stocks.assert_called_once_with(["000001"])

    def test_run_stock_selection_deduplicates_same_strategy_stock(self):
        data_sub = MagicMock()
        runner = StrategyRunner(
            data_subscription=data_sub,
            trade_executor=MagicMock(),
            position_manager=MagicMock(),
            strategy_classes=[DummyStrategy],
        )
        runner._running = True

        with patch.object(runner, "is_trading_day", return_value=True), \
             patch("strategy.runner.ProcessPoolExecutor", side_effect=RuntimeError("no subprocess")):
            runner.run_stock_selection()
            runner.run_stock_selection()

        strategies = runner.get_all_strategies()
        self.assertEqual(len(strategies), 1)
        self.assertEqual(strategies[0].status, StrategyStatus.RUNNING)

    def test_start_warns_when_strategy_limits_exceed_account_state(self):
        data_sub = MagicMock()
        position_mgr = MagicMock()
        connection_mgr = MagicMock()
        connection_mgr.is_connected.return_value = True
        connection_mgr.query_stock_asset.return_value = MagicMock(cash=5_000.0, total_asset=20_000.0)
        connection_mgr.query_stock_positions.return_value = [
            MagicMock(stock_code="000001.SZ", volume=400, can_use_volume=300)
        ]
        position_mgr.get_all_positions.return_value = {
            "s1": PositionInfo(
                strategy_id="s1",
                strategy_name="DummyStrategy",
                stock_code="000001",
                total_quantity=500,
                available_quantity=350,
            )
        }

        runner = StrategyRunner(
            data_subscription=data_sub,
            trade_executor=MagicMock(),
            position_manager=position_mgr,
            connection_manager=connection_mgr,
            strategy_classes=[],
        )
        strategy = DummyStrategy(StrategyConfig(stock_code="000001", max_position_amount=8_000.0))
        runner._strategies = [strategy]
        runner._load_state = MagicMock(return_value=True)
        runner.run_stock_selection = MagicMock()
        runner._start_scheduler = MagicMock()
        alert_callback = MagicMock()
        runner.set_alert_callback(alert_callback)

        with patch.object(runner, "is_trading_day", return_value=True):
            runner.start()

        self.assertGreaterEqual(alert_callback.call_count, 3)
        messages = [call.args[1] for call in alert_callback.call_args_list]
        self.assertTrue(any("最大资金" in message for message in messages))
        self.assertTrue(any("超过账户实际持仓" in message for message in messages))
        self.assertTrue(any("超过账户实际可用持仓" in message for message in messages))


if __name__ == "__main__":
    unittest.main(verbosity=2)