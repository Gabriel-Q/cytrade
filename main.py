"""cytrade 主程序入口。

这个文件的职责不是承载业务逻辑，而是完成系统装配与启动。
它把配置、连接、订单、持仓、策略、Web、监控等模块按正确顺序组装起来。
"""
import sys
import os
import signal
import threading

# 确保项目根目录在 sys.path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config.settings import Settings
from config.fee_schedule import FeeSchedule
from monitor.logger import LogManager, get_logger
from data.manager import DataManager
from core.connection import ConnectionManager
from core.callback import MyXtQuantTraderCallback
from core.data_subscription import DataSubscriptionManager
from trading.order_manager import OrderManager
from trading.executor import TradeExecutor
from position.manager import PositionManager
from strategy.runner import StrategyRunner
from monitor.watchdog import Watchdog


def build_app(strategy_classes=None, settings: Settings = None):
    """构建并连接所有核心模块。

    这是整个程序的“装配函数”，只负责依赖注入和对象连接，
    不负责真正进入运行循环。

    Args:
        strategy_classes: 需要托管的策略类列表。
        settings: 可选配置对象；不传时使用默认配置。

    Returns:
        一个包含所有核心模块实例的字典，便于测试和主程序复用。
    """
    settings = settings or Settings()
    # 先准备运行目录，避免后续日志、数据库、状态文件写入失败。
    settings.ensure_dirs()

    # ---- 日志 ----
    log_mgr = LogManager(
        log_dir=settings.LOG_DIR,
        max_days=settings.LOG_MAX_DAYS,
        level=settings.LOG_LEVEL,
        summary_mode=settings.LOG_SUMMARY_MODE,
    )
    logger = get_logger("system")
    logger.info("=" * 50)
    logger.info("cytrade 启动")

    # ---- 数据管理 ----
    data_mgr = DataManager(
        db_path=settings.SQLITE_DB_PATH,
        state_dir=settings.STATE_SAVE_DIR,
        remote_cfg=settings.REMOTE_DB_CONFIG,
    )
    if settings.ENABLE_REMOTE_DB:
        data_mgr.set_remote_enabled(True)

    # ``fee_schedule`` 统一封装买卖佣金、印花税和 T+0 属性判断。
    fee_schedule = FeeSchedule(
        file_path=settings.FEE_TABLE_PATH,
        default_buy_fee_rate=settings.DEFAULT_BUY_FEE_RATE,
        default_sell_fee_rate=settings.DEFAULT_SELL_FEE_RATE,
        default_stamp_tax_rate=settings.DEFAULT_STAMP_TAX_RATE,
    )

    # ---- 交易连接 ----
    conn_mgr = ConnectionManager(
        qmt_path=settings.QMT_PATH,
        account_id=settings.ACCOUNT_ID,
        account_type=settings.ACCOUNT_TYPE,
        base_interval=settings.RECONNECT_BASE_SEC,
        max_interval=settings.RECONNECT_MAX_INTERVAL_SEC,
        max_retries=(settings.RECONNECT_MAX_RETRIES
                     if settings.RECONNECT_MAX_RETRIES > 0 else None),
    )

    # ---- 订单管理 ----
    order_mgr = OrderManager(data_manager=data_mgr, fee_schedule=fee_schedule)

    # ---- 持仓管理 ----
    pos_mgr = PositionManager(
        cost_method=settings.COST_METHOD,
        data_manager=data_mgr,
        fee_schedule=fee_schedule,
    )

    # ---- 注册回调链：成交 → 持仓 ----
    order_mgr.set_position_callback(pos_mgr.on_trade_callback)

    # ---- 交易执行器 ----
    trade_exec = TradeExecutor(conn_mgr, order_mgr, pos_mgr)

    # ---- XtQuant 回调 ----
    callback = MyXtQuantTraderCallback(
        order_manager=order_mgr,
        connection_manager=conn_mgr,
    )
    conn_mgr.register_callback(callback)

    # ---- 数据订阅 ----
    # 行情订阅模块与交易连接模块解耦，便于重连后独立恢复订阅。
    data_sub = DataSubscriptionManager(
        latency_threshold_sec=settings.DATA_LATENCY_THRESHOLD_SEC,
        default_period=settings.SUBSCRIPTION_PERIOD,
    )

    # ---- 策略运行 ----
    runner = StrategyRunner(
        data_subscription=data_sub,
        trade_executor=trade_exec,
        position_manager=pos_mgr,
        data_manager=data_mgr,
        connection_manager=conn_mgr,
        strategy_classes=strategy_classes or [],
        latency_threshold_sec=settings.DATA_LATENCY_THRESHOLD_SEC,
        process_threshold_ms=settings.STRATEGY_PROCESS_THRESHOLD_MS,
    )

    # 注册“订单状态变化 -> 策略对象”的回调。
    # 这样策略才能在成交、撤单、废单后及时更新自己的内部状态。
    order_mgr.set_strategy_callback(runner.dispatch_order_update)

    # 网络断开后，连接模块会负责重连；
    # 这里再把“重连成功后的补偿动作”挂进去，自动恢复行情订阅。
    conn_mgr.register_reconnect_callback(data_sub.resubscribe_all)

    # ---- 看门狗 ----
    watchdog = Watchdog(
        interval_sec=settings.WATCHDOG_INTERVAL_SEC,
        dingtalk_webhook=settings.DINGTALK_WEBHOOK_URL,
        dingtalk_secret=settings.DINGTALK_SECRET,
        cpu_threshold=settings.CPU_ALERT_THRESHOLD,
        mem_threshold=settings.MEM_ALERT_THRESHOLD,
        position_report_times=settings.POSITION_REPORT_TIMES,
        position_manager=pos_mgr,
        connection_manager=conn_mgr,
        data_subscription=data_sub,
    )

    # 行情到达时刷新看门狗心跳
    runner.set_heartbeat_callback(watchdog.register_heartbeat)
    runner.set_alert_callback(watchdog.send_dingtalk_alert)

    # 返回装配好的上下文，方便：
    # 1. `run()` 直接复用。
    # 2. 测试代码精确断言模块装配关系。
    return {
        "settings": settings,
        "log_mgr": log_mgr,
        "data_mgr": data_mgr,
        "fee_schedule": fee_schedule,
        "conn_mgr": conn_mgr,
        "order_mgr": order_mgr,
        "pos_mgr": pos_mgr,
        "trade_exec": trade_exec,
        "callback": callback,
        "data_sub": data_sub,
        "runner": runner,
        "watchdog": watchdog,
    }


def run(strategy_classes=None, settings: Settings = None):
    """启动主程序。

    这个函数负责真正运行系统，包括：
    - 建立 QMT 连接
    - 启动 Web 服务
    - 启动看门狗
    - 启动策略运行器
    - 启动行情订阅线程
    - 监听退出信号
    """
    ctx = build_app(strategy_classes, settings)
    logger = get_logger("system")
    # 这里把常用模块从上下文字典中取出，
    # 让后续启动逻辑更直观，也避免频繁写 `ctx[...]`。
    settings = ctx["settings"]
    conn_mgr = ctx["conn_mgr"]
    runner = ctx["runner"]
    watchdog = ctx["watchdog"]
    data_sub = ctx["data_sub"]

    # ---- 优雅退出 ----
    _stop_event = threading.Event()

    def _signal_handler(sig, frame):
        """统一处理 Ctrl+C / 终止信号，尽量优雅退出。"""
        logger.info("收到退出信号 (%s)，正在关闭...", sig)
        runner.stop()
        watchdog.stop()
        data_sub.stop()
        conn_mgr.disconnect()
        _stop_event.set()

    signal.signal(signal.SIGINT, _signal_handler)
    signal.signal(signal.SIGTERM, _signal_handler)

    # ---- 连接 QMT ----
    if not conn_mgr.connect():
        logger.error("无法连接 QMT，退出")
        return

    # ---- Web 服务 ----
    # Web 层是可选能力，因此这里采用 `try` 包裹，
    # 避免缺少 FastAPI/uvicorn 时影响核心交易链路启动。
    try:
        from web.backend.main import init_app_context, run_server
        from web.backend import routes as web_routes
        # 把核心对象注入 Web 层，供 API 路由直接访问。
        init_app_context(
            strategy_runner=runner,
            position_manager=ctx["pos_mgr"],
            order_manager=ctx["order_mgr"],
            data_manager=ctx["data_mgr"],
            connection_manager=conn_mgr,
            trade_executor=ctx["trade_exec"],
        )
        run_server(host=settings.WEB_HOST, port=settings.WEB_PORT)
        if getattr(web_routes, "_ws_manager", None):
            # 成交发生后，主动推送给前端，减少轮询压力。
            ctx["order_mgr"].set_trade_callback(web_routes._ws_manager.notify_trade_update)
    except Exception as e:
        logger.warning("Web 服务未启动（可能缺少 fastapi/uvicorn）: %s", e)

    # ---- 看门狗 ----
    watchdog.start()

    # ---- 策略启动 ----
    runner.start()
    watchdog.register_heartbeat("strategy_runner")

    # ``xtdata.run()`` 是阻塞式调用，所以放到子线程里运行。
    # 主线程只负责等待退出信号，避免主程序被卡死在行情循环里。
    data_thread = threading.Thread(
        target=data_sub.start, daemon=True, name="data-sub"
    )
    data_thread.start()

    logger.info("cytrade 运行中。按 Ctrl+C 退出。")
    _stop_event.wait()
    logger.info("cytrade 已退出")


if __name__ == "__main__":
    from strategy.test_grid_strategy import TestGridStrategy
    run(strategy_classes=[TestGridStrategy])
