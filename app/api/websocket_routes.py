from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Depends
from typing import List, Dict
import logging
from datetime import datetime
import asyncio
import json

# Cấu hình logging
logger = logging.getLogger(__name__)

# Tạo router
router = APIRouter(
    tags=["WebSocket"],
)

# Lưu trữ các kết nối WebSocket đang hoạt động
class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)
        logger.info(f"New WebSocket connection added. Total connections: {len(self.active_connections)}")

    def disconnect(self, websocket: WebSocket):
        self.active_connections.remove(websocket)
        logger.info(f"WebSocket connection removed. Total connections: {len(self.active_connections)}")

    async def broadcast(self, message: Dict):
        if not self.active_connections:
            logger.warning("No active WebSocket connections to broadcast to")
            return
            
        disconnected = []
        for connection in self.active_connections:
            try:
                await connection.send_json(message)
            except Exception as e:
                logger.error(f"Error sending message to WebSocket: {e}")
                disconnected.append(connection)
                
        # Xóa kết nối bị ngắt
        for conn in disconnected:
            if conn in self.active_connections:
                self.active_connections.remove(conn)

# Khởi tạo connection manager
manager = ConnectionManager()

@router.websocket("/notify")
async def websocket_endpoint(websocket: WebSocket):
    """
    WebSocket endpoint để nhận thông báo về các session mới.
    Admin Bot sẽ kết nối đến endpoint này để nhận thông báo khi có session mới cần chú ý.
    """
    await manager.connect(websocket)
    try:
        while True:
            # Duy trì kết nối WebSocket
            data = await websocket.receive_text()
            # Echo lại để giữ kết nối
            await websocket.send_json({"status": "connected", "echo": data})
    except WebSocketDisconnect:
        logger.info("WebSocket client disconnected")
        manager.disconnect(websocket)
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
        manager.disconnect(websocket)

# Hàm gửi thông báo qua WebSocket
async def send_notification(session_data: Dict):
    """
    Gửi thông báo qua WebSocket cho tất cả các kết nối đang hoạt động.
    
    Args:
        session_data (Dict): Dữ liệu session cần gửi
    """
    notification = {
        "type": "new_session",
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "data": session_data
    }
    
    await manager.broadcast(notification)
    logger.info(f"Notification sent for session {session_data.get('session_id')}") 