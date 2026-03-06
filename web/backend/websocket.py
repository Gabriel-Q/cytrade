"""
WebSocket 实时推送
- 行情数据
- 持仓更新
- 订单状态变化
"""
import asyncio
import json
import threading
from datetime import datetime
from typing import Set

try:
    from fastapi import APIRouter, WebSocket, WebSocketDisconnect
    from fastapi.websockets import WebSocketState
    _FASTAPI = True
except ImportError:
    _FASTAPI = False
    APIRouter = object
    WebSocket = None
    WebSocketDisconnect = Exception
    WebSocketState = None

from monitor.logger import get_logger

logger = get_logger("system")

if _FASTAPI:
    ws_router = APIRouter()
else:
    ws_router = None


class WebSocketManager:
    """WebSocket 连接管理器"""

    def __init__(self):
        self._connections: Set = set()
        self._lock = threading.Lock()

    async def connect(self, ws) -> None:
        await ws.accept()
        with self._lock:
            self._connections.add(ws)
        logger.info("WebSocket: 新连接，当前 %d 个", len(self._connections))

    def disconnect(self, ws) -> None:
        with self._lock:
            self._connections.discard(ws)
        logger.info("WebSocket: 断开连接，当前 %d 个", len(self._connections))

    async def broadcast(self, message: dict) -> None:
        """广播消息给所有连接的客户端"""
        if _FASTAPI is False:
            return
        msg_str = json.dumps(message, ensure_ascii=False, default=str)
        dead = set()
        with self._lock:
            conns = set(self._connections)
        for ws in conns:
            try:
                if ws.client_state == WebSocketState.CONNECTED:
                    await ws.send_text(msg_str)
            except Exception:
                dead.add(ws)
        if dead:
            with self._lock:
                self._connections -= dead

    def broadcast_sync(self, message: dict) -> None:
        """从同步线程发送广播（自动创建 event loop）"""
        try:
            loop = asyncio.new_event_loop()
            loop.run_until_complete(self.broadcast(message))
            loop.close()
        except Exception as e:
            logger.debug("WebSocket broadcast_sync: %s", e)

    def notify_tick(self, code: str, price: float, latency_ms: float) -> None:
        """发送行情更新"""
        self.broadcast_sync({
            "type": "tick",
            "code": code,
            "price": price,
            "latency_ms": latency_ms,
            "time": datetime.now().isoformat(),
        })

    def notify_order_update(self, order) -> None:
        """发送订单状态变化"""
        self.broadcast_sync({
            "type": "order_update",
            "order_uuid": order.order_uuid,
            "status": order.status.value,
            "filled_quantity": order.filled_quantity,
            "filled_avg_price": order.filled_avg_price,
            "time": datetime.now().isoformat(),
        })

    def notify_position_update(self, pos) -> None:
        """发送持仓更新"""
        self.broadcast_sync({
            "type": "position_update",
            "strategy_id": pos.strategy_id,
            "stock_code": pos.stock_code,
            "total_quantity": pos.total_quantity,
            "avg_cost": pos.avg_cost,
            "unrealized_pnl": pos.unrealized_pnl,
            "time": datetime.now().isoformat(),
        })


# ---- WebSocket 端点 --------------------------------------------------

if _FASTAPI and ws_router is not None:

    # 单例管理器（路由模块共享）
    _ws_manager = WebSocketManager()

    @ws_router.websocket("/ws/realtime")
    async def websocket_endpoint(websocket: WebSocket):
        await _ws_manager.connect(websocket)
        try:
            while True:
                # 保持连接，等待客户端消息（心跳或控制指令）
                data = await websocket.receive_text()
                if data == "ping":
                    await websocket.send_text(json.dumps({"type": "pong"}))
        except WebSocketDisconnect:
            _ws_manager.disconnect(websocket)
        except Exception as e:
            logger.error("WebSocket: 异常: %s", e)
            _ws_manager.disconnect(websocket)


__all__ = ["WebSocketManager", "ws_router"]
