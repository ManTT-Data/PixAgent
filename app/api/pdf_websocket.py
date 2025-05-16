import logging
from typing import Dict, List, Optional, Any
from fastapi import WebSocket, WebSocketDisconnect, APIRouter
from pydantic import BaseModel
import json
import time

# Cấu hình logging
logger = logging.getLogger(__name__)

# Models cho Swagger documentation
class ConnectionStatus(BaseModel):
    user_id: str
    active: bool
    connection_count: int
    last_activity: Optional[float] = None

class UserConnection(BaseModel):
    user_id: str
    connection_count: int

class AllConnectionsStatus(BaseModel):
    total_users: int
    total_connections: int
    users: List[UserConnection]

# Khởi tạo router
router = APIRouter(
    prefix="",
    tags=["WebSockets"],
)

class ConnectionManager:
    """Quản lý các kết nối WebSocket"""
    
    def __init__(self):
        # Lưu trữ các kết nối theo user_id
        self.active_connections: Dict[str, List[WebSocket]] = {}
        
    async def connect(self, websocket: WebSocket, user_id: str):
        """Kết nối một WebSocket mới"""
        await websocket.accept()
        if user_id not in self.active_connections:
            self.active_connections[user_id] = []
        self.active_connections[user_id].append(websocket)
        logger.info(f"New WebSocket connection for user {user_id}. Total connections: {len(self.active_connections[user_id])}")
        
    def disconnect(self, websocket: WebSocket, user_id: str):
        """Ngắt kết nối WebSocket"""
        if user_id in self.active_connections:
            if websocket in self.active_connections[user_id]:
                self.active_connections[user_id].remove(websocket)
            # Xóa user_id khỏi dict nếu không còn kết nối nào
            if not self.active_connections[user_id]:
                del self.active_connections[user_id]
        logger.info(f"WebSocket disconnected for user {user_id}")
        
    async def send_message(self, message: Dict[str, Any], user_id: str):
        """Gửi tin nhắn tới tất cả kết nối của một user"""
        if user_id in self.active_connections:
            disconnected_websockets = []
            for websocket in self.active_connections[user_id]:
                try:
                    await websocket.send_text(json.dumps(message))
                except Exception as e:
                    logger.error(f"Error sending message to WebSocket: {str(e)}")
                    disconnected_websockets.append(websocket)
            
            # Xóa các kết nối bị ngắt
            for websocket in disconnected_websockets:
                self.disconnect(websocket, user_id)
    
    def get_connection_status(self, user_id: str = None) -> Dict[str, Any]:
        """Lấy thông tin về trạng thái kết nối WebSocket"""
        if user_id:
            # Trả về thông tin kết nối cho user cụ thể
            if user_id in self.active_connections:
                return {
                    "user_id": user_id,
                    "active": True,
                    "connection_count": len(self.active_connections[user_id]),
                    "last_activity": time.time()
                }
            else:
                return {
                    "user_id": user_id,
                    "active": False,
                    "connection_count": 0,
                    "last_activity": None
                }
        else:
            # Trả về thông tin tất cả kết nối
            result = {
                "total_users": len(self.active_connections),
                "total_connections": sum(len(connections) for connections in self.active_connections.values()),
                "users": []
            }
            
            for uid, connections in self.active_connections.items():
                result["users"].append({
                    "user_id": uid,
                    "connection_count": len(connections)
                })
            
            return result


# Tạo instance của ConnectionManager
manager = ConnectionManager()

# Test route for manual WebSocket sending
@router.get("/ws/test/{user_id}")
async def test_websocket_send(user_id: str):
    """
    Test route to manually send a WebSocket message to a user
    This is useful for debugging WebSocket connections
    """
    logger.info(f"Attempting to send test message to user: {user_id}")
    
    # Check if user has a connection
    status = manager.get_connection_status(user_id)
    if not status["active"]:
        logger.warning(f"No active WebSocket connection for user: {user_id}")
        return {"success": False, "message": f"No active WebSocket connection for user: {user_id}"}
    
    # Send test message
    await manager.send_message({
        "type": "test_message",
        "message": "This is a test WebSocket message",
        "timestamp": int(time.time())
    }, user_id)
    
    logger.info(f"Test message sent to user: {user_id}")
    return {"success": True, "message": f"Test message sent to user: {user_id}"}

@router.websocket("/ws/pdf/{user_id}")
async def websocket_endpoint(websocket: WebSocket, user_id: str):
    """Endpoint WebSocket để cập nhật tiến trình xử lý PDF"""
    logger.info(f"WebSocket connection request received for user: {user_id}")
    
    try:
        await manager.connect(websocket, user_id)
        logger.info(f"WebSocket connection accepted for user: {user_id}")
        
        # Send a test message to confirm connection
        await manager.send_message({
            "type": "connection_established",
            "message": "WebSocket connection established successfully",
            "user_id": user_id,
            "timestamp": int(time.time())
        }, user_id)
        
        try:
            while True:
                # Đợi tin nhắn từ client (chỉ để giữ kết nối)
                data = await websocket.receive_text()
                logger.debug(f"Received from client: {data}")
                
                # Echo back to confirm receipt
                if data != "heartbeat":  # Don't echo heartbeats
                    await manager.send_message({
                        "type": "echo",
                        "message": f"Received: {data}",
                        "timestamp": int(time.time())
                    }, user_id)
        except WebSocketDisconnect:
            logger.info(f"WebSocket disconnected for user: {user_id}")
            manager.disconnect(websocket, user_id)
        except Exception as e:
            logger.error(f"WebSocket error: {str(e)}")
            manager.disconnect(websocket, user_id)
    except Exception as e:
        logger.error(f"Failed to establish WebSocket connection: {str(e)}")
        # Ensure the connection is closed properly
        if websocket.client_state != 4:  # 4 = CLOSED
            await websocket.close(code=1011, reason=f"Server error: {str(e)}")

import logging
from typing import Dict, List, Optional, Any
from fastapi import WebSocket, WebSocketDisconnect, APIRouter
from pydantic import BaseModel
import json
import time

# Cấu hình logging
logger = logging.getLogger(__name__)

# Models cho Swagger documentation
class ConnectionStatus(BaseModel):
    user_id: str
    active: bool
    connection_count: int
    last_activity: Optional[float] = None

class UserConnection(BaseModel):
    user_id: str
    connection_count: int

class AllConnectionsStatus(BaseModel):
    total_users: int
    total_connections: int
    users: List[UserConnection]

# Khởi tạo router
router = APIRouter(
    prefix="",
    tags=["WebSockets"],
)

class ConnectionManager:
    """Quản lý các kết nối WebSocket"""
    
    def __init__(self):
        # Lưu trữ các kết nối theo user_id
        self.active_connections: Dict[str, List[WebSocket]] = {}
        
    async def connect(self, websocket: WebSocket, user_id: str):
        """Kết nối một WebSocket mới"""
        await websocket.accept()
        if user_id not in self.active_connections:
            self.active_connections[user_id] = []
        self.active_connections[user_id].append(websocket)
        logger.info(f"New WebSocket connection for user {user_id}. Total connections: {len(self.active_connections[user_id])}")
        
    def disconnect(self, websocket: WebSocket, user_id: str):
        """Ngắt kết nối WebSocket"""
        if user_id in self.active_connections:
            if websocket in self.active_connections[user_id]:
                self.active_connections[user_id].remove(websocket)
            # Xóa user_id khỏi dict nếu không còn kết nối nào
            if not self.active_connections[user_id]:
                del self.active_connections[user_id]
        logger.info(f"WebSocket disconnected for user {user_id}")
        
    async def send_message(self, message: Dict[str, Any], user_id: str):
        """Gửi tin nhắn tới tất cả kết nối của một user"""
        if user_id in self.active_connections:
            disconnected_websockets = []
            for websocket in self.active_connections[user_id]:
                try:
                    await websocket.send_text(json.dumps(message))
                except Exception as e:
                    logger.error(f"Error sending message to WebSocket: {str(e)}")
                    disconnected_websockets.append(websocket)
            
            # Xóa các kết nối bị ngắt
            for websocket in disconnected_websockets:
                self.disconnect(websocket, user_id)
    
    def get_connection_status(self, user_id: str = None) -> Dict[str, Any]:
        """Lấy thông tin về trạng thái kết nối WebSocket"""
        if user_id:
            # Trả về thông tin kết nối cho user cụ thể
            if user_id in self.active_connections:
                return {
                    "user_id": user_id,
                    "active": True,
                    "connection_count": len(self.active_connections[user_id]),
                    "last_activity": time.time()
                }
            else:
                return {
                    "user_id": user_id,
                    "active": False,
                    "connection_count": 0,
                    "last_activity": None
                }
        else:
            # Trả về thông tin tất cả kết nối
            result = {
                "total_users": len(self.active_connections),
                "total_connections": sum(len(connections) for connections in self.active_connections.values()),
                "users": []
            }
            
            for uid, connections in self.active_connections.items():
                result["users"].append({
                    "user_id": uid,
                    "connection_count": len(connections)
                })
            
            return result


# Tạo instance của ConnectionManager
manager = ConnectionManager()

@router.websocket("/ws/pdf/{user_id}")
async def websocket_endpoint(websocket: WebSocket, user_id: str):
    """Endpoint WebSocket để cập nhật tiến trình xử lý PDF"""
    await manager.connect(websocket, user_id)
    try:
        while True:
            # Đợi tin nhắn từ client (chỉ để giữ kết nối)
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket, user_id)
    except Exception as e:
        logger.error(f"WebSocket error: {str(e)}")
        manager.disconnect(websocket, user_id)

# API endpoints để kiểm tra trạng thái WebSocket
@router.get("/ws/status", response_model=AllConnectionsStatus, responses={
    200: {
        "description": "Successful response",
        "content": {
            "application/json": {
                "example": {
                    "total_users": 2,
                    "total_connections": 3,
                    "users": [
                        {"user_id": "user1", "connection_count": 2},
                        {"user_id": "user2", "connection_count": 1}
                    ]
                }
            }
        }
    }
})
async def get_all_websocket_connections():
    """
    Lấy thông tin về tất cả kết nối WebSocket hiện tại.
    
    Endpoint này trả về:
    - Tổng số người dùng đang kết nối
    - Tổng số kết nối WebSocket
    - Danh sách người dùng kèm theo số lượng kết nối của mỗi người
    """
    return manager.get_connection_status()

@router.get("/ws/status/{user_id}", response_model=ConnectionStatus, responses={
    200: {
        "description": "Successful response for active connection",
        "content": {
            "application/json": {
                "examples": {
                    "active_connection": {
                        "summary": "Active connection",
                        "value": {
                            "user_id": "user123",
                            "active": True,
                            "connection_count": 2,
                            "last_activity": 1634567890.123
                        }
                    },
                    "no_connection": {
                        "summary": "No active connection",
                        "value": {
                            "user_id": "user456",
                            "active": False,
                            "connection_count": 0,
                            "last_activity": None
                        }
                    }
                }
            }
        }
    }
})
async def get_user_websocket_status(user_id: str):
    """
    Lấy thông tin về kết nối WebSocket của một người dùng cụ thể.
    
    Parameters:
    - **user_id**: ID của người dùng cần kiểm tra
    
    Returns:
    - Thông tin về trạng thái kết nối, bao gồm:
      - active: Có đang kết nối hay không
      - connection_count: Số lượng kết nối hiện tại
      - last_activity: Thời gian hoạt động gần nhất
    """
    return manager.get_connection_status(user_id)

# Các hàm gửi thông báo cập nhật trạng thái

async def send_pdf_upload_started(user_id: str, filename: str, document_id: str):
    """Gửi thông báo bắt đầu upload PDF"""
    await manager.send_message({
        "type": "pdf_upload_started",
        "document_id": document_id,
        "filename": filename,
        "timestamp": int(time.time())
    }, user_id)

async def send_pdf_upload_progress(user_id: str, document_id: str, step: str, progress: float, message: str):
    """Gửi thông báo tiến độ upload PDF"""
    await manager.send_message({
        "type": "pdf_upload_progress",
        "document_id": document_id,
        "step": step,
        "progress": progress,
        "message": message,
        "timestamp": int(time.time())
    }, user_id)

async def send_pdf_upload_completed(user_id: str, document_id: str, filename: str, chunks: int):
    """Gửi thông báo hoàn thành upload PDF"""
    await manager.send_message({
        "type": "pdf_upload_completed",
        "document_id": document_id,
        "filename": filename,
        "chunks": chunks,
        "timestamp": int(time.time())
    }, user_id)

async def send_pdf_upload_failed(user_id: str, document_id: str, filename: str, error: str):
    """Gửi thông báo lỗi upload PDF"""
    await manager.send_message({
        "type": "pdf_upload_failed",
        "document_id": document_id,
        "filename": filename,
        "error": error,
        "timestamp": int(time.time())
    }, user_id)

async def send_pdf_delete_started(user_id: str, namespace: str):
    """Gửi thông báo bắt đầu xóa PDF"""
    await manager.send_message({
        "type": "pdf_delete_started",
        "namespace": namespace,
        "timestamp": int(time.time())
    }, user_id)

async def send_pdf_delete_completed(user_id: str, namespace: str, deleted_count: int = 0):
    """Gửi thông báo hoàn thành xóa PDF"""
    await manager.send_message({
        "type": "pdf_delete_completed",
        "namespace": namespace,
        "deleted_count": deleted_count,
        "timestamp": int(time.time())
    }, user_id)

async def send_pdf_delete_failed(user_id: str, namespace: str, error: str):
    """Gửi thông báo lỗi xóa PDF"""
    await manager.send_message({
        "type": "pdf_delete_failed",
        "namespace": namespace,
        "error": error,
        "timestamp": int(time.time())
    }, user_id)