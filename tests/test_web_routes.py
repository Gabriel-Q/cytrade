"""
Web 路由测试
"""
import sys, os, asyncio
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import unittest
from unittest.mock import MagicMock

from config.enums import OrderDirection, OrderStatus, OrderType
from trading.models import Order
from web.backend import routes


@unittest.skipUnless(hasattr(routes, "cancel_order"), "fastapi not available")
class TestWebRoutes(unittest.TestCase):

    def setUp(self):
        self.order = Order(
            strategy_id="s1",
            strategy_name="TestGrid",
            stock_code="000001",
            direction=OrderDirection.BUY,
            order_type=OrderType.LIMIT,
            price=10.0,
            quantity=100,
            status=OrderStatus.SUBMITTED,
        )
        self.order_mgr = MagicMock()
        self.trade_exec = MagicMock()
        self.order_mgr.get_order.return_value = self.order
        self.trade_exec.cancel_order.return_value = True

        routes._order_manager = self.order_mgr
        routes._trade_executor = self.trade_exec

    def test_cancel_order_route_uses_trade_executor(self):
        result = asyncio.run(routes.cancel_order(self.order.order_uuid))

        self.trade_exec.cancel_order.assert_called_once_with(self.order.order_uuid, remark="Web撤单")
        self.assertTrue(result.success)


if __name__ == "__main__":
    unittest.main(verbosity=2)
