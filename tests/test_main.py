"""
主入口装配测试
"""
import sys, os, tempfile
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import unittest

import main as app_main
from config.settings import Settings


class TestMainBuildApp(unittest.TestCase):

    def test_build_app_registers_reconnect_callback(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            settings = Settings(
                LOG_DIR=os.path.join(tmpdir, "logs"),
                SQLITE_DB_PATH=os.path.join(tmpdir, "data", "cytrade2.db"),
                STATE_SAVE_DIR=os.path.join(tmpdir, "saved_states"),
            )
            ctx = app_main.build_app(strategy_classes=[], settings=settings)

            self.assertIsNotNone(ctx["conn_mgr"])
            self.assertIn(ctx["data_sub"].resubscribe_all, ctx["conn_mgr"]._reconnect_callbacks)
            self.assertIs(ctx["runner"]._heartbeat_callback.__self__, ctx["watchdog"])
            self.assertIs(
                ctx["runner"]._heartbeat_callback.__func__,
                ctx["watchdog"].register_heartbeat.__func__,
            )


if __name__ == "__main__":
    unittest.main(verbosity=2)
