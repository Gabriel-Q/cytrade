"""
订单管理模块测试
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import unittest
from unittest.mock import MagicMock

from trading.order_manager import OrderManager
from trading.models import Order
from config.enums import OrderDirection, OrderType, OrderStatus


def _mk_order(strategy_id="s1", xt_order_id=0):
    return Order(
        strategy_id=strategy_id,
        strategy_name="TestStrategy",
        stock_code="000001",
        direction=OrderDirection.BUY,
        order_type=OrderType.LIMIT,
        price=10.0,
        quantity=100,
        xt_order_id=xt_order_id,
        status=OrderStatus.SUBMITTED,
    )


class TestOrderManager(unittest.TestCase):

    def setUp(self):
        self.data_mgr = MagicMock()
        self.order_mgr = OrderManager(data_manager=self.data_mgr)

    def test_register_and_get_order(self):
        order = _mk_order(xt_order_id=123)
        self.order_mgr.register_order(order)
        found = self.order_mgr.get_order(order.order_uuid)
        self.assertIsNotNone(found)
        self.assertEqual(found.xt_order_id, 123)

    def test_update_order_status(self):
        order = _mk_order(xt_order_id=1001)
        self.order_mgr.register_order(order)
        self.order_mgr.update_order_status(
            xt_order_id=1001,
            status=OrderStatus.PARTIALLY_FILLED,
            filled_qty=50,
            filled_amount=500.0,
            avg_price=10.0,
        )
        updated = self.order_mgr.get_order(order.order_uuid)
        self.assertEqual(updated.status, OrderStatus.PARTIALLY_FILLED)
        self.assertEqual(updated.filled_quantity, 50)

    def test_on_trade_triggers_callbacks(self):
        order = _mk_order(xt_order_id=2002)
        self.order_mgr.register_order(order)

        pos_cb = MagicMock()
        strategy_cb = MagicMock()
        self.order_mgr.set_position_callback(pos_cb)
        self.order_mgr.set_strategy_callback(strategy_cb)

        trade_info = {
            "trade_id": "T1",
            "xt_order_id": 2002,
            "stock_code": "000001",
            "direction": "BUY",
            "price": 10.0,
            "quantity": 100,
            "amount": 1000.0,
            "commission": 1.0,
        }
        self.order_mgr.on_trade(2002, trade_info)

        pos_cb.assert_called_once()
        strategy_cb.assert_called_once()
        updated = self.order_mgr.get_order(order.order_uuid)
        self.assertEqual(updated.status, OrderStatus.FILLED)

    def test_async_response_binds_xt_id(self):
        order = _mk_order(xt_order_id=0)
        self.order_mgr.register_order(order)
        self.order_mgr.register_seq(77, order.order_uuid)

        self.order_mgr.on_async_response(77, 99001)

        by_xt = self.order_mgr.get_order_by_xt_id(99001)
        self.assertIsNotNone(by_xt)
        self.assertEqual(by_xt.order_uuid, order.order_uuid)

    def test_get_orders_by_strategy(self):
        o1 = _mk_order(strategy_id="s1")
        o2 = _mk_order(strategy_id="s2")
        self.order_mgr.register_order(o1)
        self.order_mgr.register_order(o2)

        s1_orders = self.order_mgr.get_orders_by_strategy("s1")
        self.assertEqual(len(s1_orders), 1)
        self.assertEqual(s1_orders[0].strategy_id, "s1")


if __name__ == "__main__":
    unittest.main(verbosity=2)
