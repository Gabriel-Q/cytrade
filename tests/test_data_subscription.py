"""
数据订阅模块测试
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import unittest
from unittest.mock import MagicMock

from core.data_subscription import DataSubscriptionManager


class TestDataSubscriptionManager(unittest.TestCase):

    def test_resubscribe_all_restores_grouped_and_whole_market_subscriptions(self):
        mgr = DataSubscriptionManager()
        mgr._subscriptions = {
            "000001": "tick",
            "000002": "1m",
            "600000": "tick",
        }
        mgr._whole_market = True
        mgr.subscribe_stocks = MagicMock()
        mgr.subscribe_whole_market = MagicMock()

        mgr.resubscribe_all()

        mgr.subscribe_whole_market.assert_called_once_with()
        calls = mgr.subscribe_stocks.call_args_list
        self.assertEqual(len(calls), 2)

        actual = {(tuple(args[0]), args[1]) for args, _ in calls}
        self.assertEqual(actual, {
            (("000001", "600000"), "tick"),
            (("000002",), "1m"),
        })


if __name__ == "__main__":
    unittest.main(verbosity=2)
