from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Depends, status
from typing import List, Dict
import logging
from datetime import datetime
import asyncio
import json
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Lấy cấu hình WebSocket từ biến môi trường
WEBSOCKET_SERVER = os.getenv("WEBSOCKET_SERVER", "localhost")
WEBSOCKET_PORT = os.getenv("WEBSOCKET_PORT", "7860")
WEBSOCKET_PATH = os.getenv("WEBSOCKET_PATH", "/notify")

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

# Tạo URL đầy đủ của WebSocket server từ biến môi trường
def get_full_websocket_url(server_side=False):
    if server_side:
        # URL tương đối (cho phía server)
        return WEBSOCKET_PATH
    else:
        # URL đầy đủ (cho client)
        return f"ws://{WEBSOCKET_SERVER}:{WEBSOCKET_PORT}{WEBSOCKET_PATH}"

# Thêm endpoint GET để hiển thị thông tin WebSocket trong Swagger
@router.get("/notify", 
    summary="WebSocket thông báo cho Admin Bot",
    description=f"""
    Đây là tài liệu cho WebSocket endpoint.
    
    Để kết nối WebSocket:
    1. Sử dụng đường dẫn `{get_full_websocket_url()}`
    2. Kết nối bằng thư viện WebSocket client
    3. Khi có session mới cần thông báo, bạn sẽ nhận được thông báo qua kết nối này
    
    Thông báo được gửi khi:
    - Có session mới với factor "rag"
    - Tin nhắn bắt đầu bằng "I don't know"
    """,
    status_code=status.HTTP_200_OK
)
async def websocket_documentation():
    """
    Cung cấp thông tin về cách sử dụng WebSocket endpoint /notify.
    Endpoint này chỉ dùng cho mục đích tài liệu. Để sử dụng WebSocket, vui lòng kết nối đến WebSocket URL.
    """
    ws_url = get_full_websocket_url()
    return {
        "websocket_endpoint": WEBSOCKET_PATH,
        "connection_type": "WebSocket",
        "protocol": "ws://",
        "server": WEBSOCKET_SERVER,
        "port": WEBSOCKET_PORT,
        "full_url": ws_url,
        "description": "Endpoint nhận thông báo về các session mới cần chú ý",
        "notification_format": {
            "type": "new_session",
            "timestamp": "YYYY-MM-DD HH:MM:SS",
            "data": {
                "session_id": "id của session",
                "factor": "rag",
                "action": "loại hành động",
                "message": "I don't know...",
                "user_id": "id người dùng",
                "first_name": "tên người dùng",
                "last_name": "họ người dùng",
                "username": "tên đăng nhập",
                "created_at": "thời gian tạo"
            }
        },
        "client_example": f"""
        import websocket
        import json
        import os
        from dotenv import load_dotenv
        
        # Load environment variables
        load_dotenv()
        
        # Lấy cấu hình WebSocket từ biến môi trường
        WEBSOCKET_SERVER = os.getenv("WEBSOCKET_SERVER", "localhost")
        WEBSOCKET_PORT = os.getenv("WEBSOCKET_PORT", "7860")
        WEBSOCKET_PATH = os.getenv("WEBSOCKET_PATH", "/notify")
        
        # Tạo URL đầy đủ
        ws_url = f"ws://{{WEBSOCKET_SERVER}}:{{WEBSOCKET_PORT}}{{WEBSOCKET_PATH}}"
        
        def on_message(ws, message):
            data = json.loads(message)
            print(f"Received notification: {{data}}")
            # Forward to Telegram Admin
        
        def on_error(ws, error):
            print(f"Error: {{error}}")
        
        def on_close(ws, close_status_code, close_msg):
            print("Connection closed")
        
        def on_open(ws):
            print("Connection opened")
            # Gửi message keepalive định kỳ
            ws.send("keepalive")
        
        # Kết nối WebSocket
        ws = websocket.WebSocketApp(
            ws_url,
            on_open=on_open,
            on_message=on_message,
            on_error=on_error,
            on_close=on_close
        )
        ws.run_forever()
        """
    }

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