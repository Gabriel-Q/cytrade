"""
FastAPI 后端 API
- 策略管理（暂停/恢复/强制平仓）
- 持仓查询
- 订单查询
- 成交查询
- 系统状态
- WebSocket 实时推送
"""
import asyncio
import threading
from contextlib import asynccontextmanager
from typing import Optional

try:
    from fastapi import FastAPI
    from fastapi.middleware.cors import CORSMiddleware
    _FASTAPI = True
except ImportError:
    _FASTAPI = False

from monitor.logger import get_logger

logger = get_logger("system")

# ---- 全局依赖注入容器（在 main.py 中设置）------------------------------
_strategy_runner = None
_position_manager = None
_order_manager = None
_data_manager = None
_connection_manager = None
_trade_executor = None
_ws_manager = None  # WebSocketManager


def init_app_context(strategy_runner=None, position_manager=None,
                     order_manager=None, data_manager=None,
                     connection_manager=None, trade_executor=None):
    global _strategy_runner, _position_manager, _order_manager
    global _data_manager, _connection_manager, _trade_executor
    _strategy_runner = strategy_runner
    _position_manager = position_manager
    _order_manager = order_manager
    _data_manager = data_manager
    _connection_manager = connection_manager
    _trade_executor = trade_executor


# ---- App 工厂 -------------------------------------------------------

def create_app():
    if not _FASTAPI:
        raise ImportError("fastapi 未安装，请执行: pip install fastapi uvicorn")

    from web.backend.routes import router
    from web.backend.websocket import WebSocketManager, ws_router

    global _ws_manager
    _ws_manager = WebSocketManager()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        logger.info("FastAPI: 应用启动")
        yield
        logger.info("FastAPI: 应用关闭")

    app = FastAPI(
        title="CyTrade2 API",
        description="量化交易框架控制面板",
        version="1.0.0",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(router, prefix="/api")
    app.include_router(ws_router)

    # 将上下文注入路由
    from web.backend import routes
    routes._strategy_runner = _strategy_runner
    routes._position_manager = _position_manager
    routes._order_manager = _order_manager
    routes._data_manager = _data_manager
    routes._connection_manager = _connection_manager
    routes._trade_executor = _trade_executor
    routes._ws_manager = _ws_manager

    return app


def run_server(host: str = "0.0.0.0", port: int = 8080):
    """在后台线程中运行 FastAPI 服务"""
    try:
        import uvicorn
        app = create_app()

        def _run():
            uvicorn.run(app, host=host, port=port, log_level="warning")

        t = threading.Thread(target=_run, daemon=True, name="web-server")
        t.start()
        logger.info("Web 服务已启动 http://%s:%d", host, port)
        return t
    except Exception as e:
        logger.error("Web 服务启动失败: %s", e, exc_info=True)
        return None
