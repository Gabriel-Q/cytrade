"""FastAPI 后端入口与应用工厂。

本模块负责完成 Web 服务的最外层装配工作，主要包括：

* 创建 FastAPI 应用实例。
* 注册 REST 路由与 WebSocket 路由。
* 将主程序构造好的核心对象注入到 Web 层上下文。
* 在存在前端构建产物时，托管静态资源并支持 SPA 路由回退。
* 提供后台线程方式启动 Web 服务的便捷入口。
"""
import asyncio
import os
import threading
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional

try:
    from fastapi import FastAPI, HTTPException
    from fastapi.middleware.cors import CORSMiddleware
    from fastapi.responses import FileResponse
    from fastapi.staticfiles import StaticFiles
    _FASTAPI = True
except ImportError:
    _FASTAPI = False

from monitor.logger import get_logger

logger = get_logger("system")

# ---- 全局依赖注入容器（在主程序装配阶段设置）----------------------------
_strategy_runner = None  # 策略运行器，供策略管理接口使用。
_position_manager = None  # 持仓管理器，供持仓查询接口使用。
_order_manager = None  # 订单管理器，供订单与成交接口使用。
_data_manager = None  # 数据管理器，供历史记录与快照接口使用。
_connection_manager = None  # 交易连接管理器，供系统状态接口使用。
_trade_executor = None  # 交易执行器，供人工下单或平仓接口使用。
_data_subscription = None  # 行情订阅管理器，供系统状态接口读取最新数据时间与延迟。
_ws_manager = None  # WebSocket 管理器实例，由应用创建时初始化。


def _get_frontend_dist_dir() -> Path:
    """返回前端打包产物目录。

    Returns:
        Path: 默认约定的前端 `dist` 构建目录路径。
    """
    return Path(__file__).resolve().parents[1] / "frontend" / "dist"


def init_app_context(strategy_runner=None, position_manager=None,
                     order_manager=None, data_manager=None,
                     connection_manager=None, trade_executor=None,
                     data_subscription=None):
    """把主程序创建的核心对象注入到 Web 层全局上下文中。

    Web 路由模块本身不负责对象构造，而是通过该函数接收主程序已经装配完成的
    运行时依赖。这样可以避免 Web 层直接反向依赖系统启动流程。
    """
    global _strategy_runner, _position_manager, _order_manager
    global _data_manager, _connection_manager, _trade_executor, _data_subscription
    _strategy_runner = strategy_runner
    _position_manager = position_manager
    _order_manager = order_manager
    _data_manager = data_manager
    _connection_manager = connection_manager
    _trade_executor = trade_executor
    _data_subscription = data_subscription


# ---- App 工厂 -------------------------------------------------------

def create_app():
    """创建并配置 FastAPI 应用实例。

    Returns:
        FastAPI: 已注册中间件、路由与静态资源托管配置的应用对象。

    Raises:
        ImportError: 当前环境未安装 FastAPI 依赖时抛出。
    """
    if not _FASTAPI:
        raise ImportError("fastapi 未安装，请执行: pip install fastapi uvicorn")

    from web.backend.routes import router
    from web.backend.websocket import WebSocketManager, ws_router

    global _ws_manager
    _ws_manager = WebSocketManager()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        """FastAPI 生命周期钩子。

        Args:
            app: 当前 FastAPI 应用实例。
        """
        logger.info("FastAPI: 应用启动")
        yield
        logger.info("FastAPI: 应用关闭")

    app = FastAPI(
        title="cytrade API",
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

    # 将主程序注入的运行时对象同步到路由模块，供接口处理函数直接使用。
    from web.backend import routes
    routes._strategy_runner = _strategy_runner
    routes._position_manager = _position_manager
    routes._order_manager = _order_manager
    routes._data_manager = _data_manager
    routes._connection_manager = _connection_manager
    routes._trade_executor = _trade_executor
    routes._data_subscription = _data_subscription
    routes._ws_manager = _ws_manager

    frontend_dist = _get_frontend_dist_dir()
    index_file = frontend_dist / "index.html"
    assets_dir = frontend_dist / "assets"

    if index_file.exists():
        # 若前端已完成构建，则由后端同时承担静态资源托管职责，方便一体化部署。
        if assets_dir.exists():
            app.mount("/assets", StaticFiles(directory=str(assets_dir)), name="frontend-assets")

        @app.get("/", include_in_schema=False)
        async def frontend_index():
            """返回前端入口页面。"""
            return FileResponse(str(index_file))

        @app.get("/{full_path:path}", include_in_schema=False)
        async def frontend_spa(full_path: str):
            """支持前端单页应用路由回退。

            Args:
                full_path: 浏览器请求的任意路径。
            """
            if full_path.startswith(("api", "ws")):
                raise HTTPException(status_code=404, detail="Not Found")

            # 若请求的是实际存在的静态文件，则原样返回；否则统一回退到入口页。
            requested_file = frontend_dist / full_path
            if requested_file.is_file():
                return FileResponse(str(requested_file))

            return FileResponse(str(index_file))

        logger.info("FastAPI: 已启用前端静态资源托管 %s", index_file)
    else:
        logger.info("FastAPI: 未检测到前端构建产物，跳过静态托管")

    return app


def run_server(host: str = "0.0.0.0", port: int = 8080):
    """在后台线程中运行 FastAPI 服务。

    Args:
        host: 监听地址。
        port: 监听端口。

    Returns:
        threading.Thread | None: 启动成功时返回后台线程对象，失败时返回 `None`。
    """
    try:
        import uvicorn
        app = create_app()

        def _run():
            """真正执行 uvicorn 启动的线程入口。"""
            uvicorn.run(app, host=host, port=port, log_level="warning")

        t = threading.Thread(target=_run, daemon=True, name="web-server")
        t.start()
        logger.info("Web 服务已启动 http://%s:%d", host, port)
        return t
    except Exception as e:
        logger.error("Web 服务启动失败: %s", e, exc_info=True)
        return None
