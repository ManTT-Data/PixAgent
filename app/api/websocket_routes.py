from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Depends, status
from typing import List, Dict
import logging
from datetime import datetime
import asyncio
import json
import os
from dotenv import load_dotenv
from app.database.mongodb import session_collection
from app.utils.utils import get_local_time

# Load environment variables
load_dotenv()

# Get WebSocket configuration from environment variables
WEBSOCKET_SERVER = os.getenv("WEBSOCKET_SERVER", "localhost")
WEBSOCKET_PORT = os.getenv("WEBSOCKET_PORT", "7860")
WEBSOCKET_PATH = os.getenv("WEBSOCKET_PATH", "/notify")

# Configure logging
logger = logging.getLogger(__name__)

# Create router
router = APIRouter(
    tags=["WebSocket"],
)

# Store active WebSocket connections
class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)
        client_info = f"{websocket.client.host}:{websocket.client.port}" if hasattr(websocket, 'client') else "Unknown"
        logger.info(f"New WebSocket connection from {client_info}. Total connections: {len(self.active_connections)}")

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
                logger.info(f"Message sent to WebSocket connection")
            except Exception as e:
                logger.error(f"Error sending message to WebSocket: {e}")
                disconnected.append(connection)
                
        # Remove disconnected connections
        for conn in disconnected:
            if conn in self.active_connections:
                self.active_connections.remove(conn)
                logger.info(f"Removed disconnected WebSocket. Remaining: {len(self.active_connections)}")

# Initialize connection manager
manager = ConnectionManager()

# Create full URL of WebSocket server from environment variables
def get_full_websocket_url(server_side=False):
    if server_side:
        # Relative URL (for server side)
        return WEBSOCKET_PATH
    else:
        # Full URL (for client)
        # Check if should use wss:// for HTTPS
        is_https = True if int(WEBSOCKET_PORT) == 443 else False
        protocol = "wss" if is_https else "ws"
        
        # If using default port for protocol, don't include in URL
        if (is_https and int(WEBSOCKET_PORT) == 443) or (not is_https and int(WEBSOCKET_PORT) == 80):
            return f"{protocol}://{WEBSOCKET_SERVER}{WEBSOCKET_PATH}"
        else:
            return f"{protocol}://{WEBSOCKET_SERVER}:{WEBSOCKET_PORT}{WEBSOCKET_PATH}"

# Add GET endpoint to display WebSocket information in Swagger
@router.get("/notify", 
    summary="WebSocket notifications for Admin Bot",
    description=f"""
    This is documentation for the WebSocket endpoint.
    
    To connect to WebSocket:
    1. Use the path `{get_full_websocket_url()}`
    2. Connect using a WebSocket client library
    3. When there are new sessions requiring attention, you will receive notifications through this connection
    
    Notifications are sent when:
    - Session response starts with "I'm sorry"
    - The system cannot answer the user's question
    
    Make sure to send a "keepalive" message every 5 minutes to maintain the connection.
    """,
    status_code=status.HTTP_200_OK
)
async def websocket_documentation():
    """
    Provides information about how to use the WebSocket endpoint /notify.
    This endpoint is for documentation purposes only. To use WebSocket, please connect to the WebSocket URL.
    """
    ws_url = get_full_websocket_url()
    return {
        "websocket_endpoint": WEBSOCKET_PATH,
        "connection_type": "WebSocket",
        "protocol": "ws://",
        "server": WEBSOCKET_SERVER,
        "port": WEBSOCKET_PORT,
        "full_url": ws_url,
        "description": "Endpoint to receive notifications about new sessions requiring attention",
        "notification_format": {
            "type": "sorry_response",
            "timestamp": "YYYY-MM-DD HH:MM:SS",
            "data": {
                "session_id": "session id",
                "factor": "user",
                "action": "action type",
                "message": "User question",
                "response": "I'm sorry...",
                "user_id": "user id",
                "first_name": "user's first name",
                "last_name": "user's last name",
                "username": "username",
                "created_at": "creation time"
            }
        },
        "client_example": """
        import websocket
        import json
        import os
        import time
        import threading
        from dotenv import load_dotenv
        
        # Load environment variables
        load_dotenv()
        
        # Get WebSocket configuration from environment variables
        WEBSOCKET_SERVER = os.getenv("WEBSOCKET_SERVER", "localhost")
        WEBSOCKET_PORT = os.getenv("WEBSOCKET_PORT", "7860")
        WEBSOCKET_PATH = os.getenv("WEBSOCKET_PATH", "/notify")
        
        # Create full URL
        ws_url = f"ws://{WEBSOCKET_SERVER}:{WEBSOCKET_PORT}{WEBSOCKET_PATH}"
        
        # If using HTTPS, replace ws:// with wss://
        # ws_url = f"wss://{WEBSOCKET_SERVER}{WEBSOCKET_PATH}"
        
        # Send keepalive periodically
        def send_keepalive(ws):
            while True:
                try:
                    if ws.sock and ws.sock.connected:
                        ws.send("keepalive")
                        print("Sent keepalive message")
                    time.sleep(300)  # 5 minutes
                except Exception as e:
                    print(f"Error sending keepalive: {e}")
                    time.sleep(60)
        
        def on_message(ws, message):
            try:
                data = json.loads(message)
                print(f"Received notification: {data}")
                # Process notification, e.g.: send to Telegram Admin
                if data.get("type") == "sorry_response":
                    session_data = data.get("data", {})
                    user_question = session_data.get("message", "")
                    user_name = session_data.get("first_name", "Unknown User")
                    print(f"User {user_name} asked: {user_question}")
                    # Code to send message to Telegram Admin
            except json.JSONDecodeError:
                print(f"Received non-JSON message: {message}")
            except Exception as e:
                print(f"Error processing message: {e}")
        
        def on_error(ws, error):
            print(f"WebSocket error: {error}")
        
        def on_close(ws, close_status_code, close_msg):
            print(f"WebSocket connection closed: code={close_status_code}, message={close_msg}")
        
        def on_open(ws):
            print(f"WebSocket connection opened to {ws_url}")
            # Send keepalive messages periodically in a separate thread
            keepalive_thread = threading.Thread(target=send_keepalive, args=(ws,), daemon=True)
            keepalive_thread.start()
        
        def run_forever_with_reconnect():
            while True:
                try:
                    # Connect WebSocket with ping to maintain connection
                    ws = websocket.WebSocketApp(
                        ws_url,
                        on_open=on_open,
                        on_message=on_message,
                        on_error=on_error,
                        on_close=on_close
                    )
                    ws.run_forever(ping_interval=60, ping_timeout=30)
                    print("WebSocket connection lost, reconnecting in 5 seconds...")
                    time.sleep(5)
                except Exception as e:
                    print(f"WebSocket connection error: {e}")
                    time.sleep(5)
        
        # Start WebSocket client in a separate thread
        websocket_thread = threading.Thread(target=run_forever_with_reconnect, daemon=True)
        websocket_thread.start()
        
        # Keep the program running
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            print("Stopping WebSocket client...")
        """
    }

@router.websocket("/notify")
async def websocket_endpoint(websocket: WebSocket):
    """
    WebSocket endpoint to receive notifications about new sessions.
    Admin Bot will connect to this endpoint to receive notifications when there are new sessions requiring attention.
    """
    await manager.connect(websocket)
    try:
        # Keep track of last activity time to prevent connection timeouts
        last_activity = datetime.now()
        
        # Set up a background ping task
        async def send_periodic_ping():
            try:
                while True:
                    # Send ping every 20 seconds if no other activity
                    await asyncio.sleep(20)
                    current_time = datetime.now()
                    time_since_activity = (current_time - last_activity).total_seconds()
                    
                    # Only send ping if there's been no activity for 15+ seconds
                    if time_since_activity > 15:
                        logger.debug("Sending ping to client to keep connection alive")
                        await websocket.send_json({"type": "ping", "timestamp": current_time.isoformat()})
            except asyncio.CancelledError:
                # Task was cancelled, just exit quietly
                pass
            except Exception as e:
                logger.error(f"Error in ping task: {e}")
        
        # Start ping task
        ping_task = asyncio.create_task(send_periodic_ping())
        
        # Main message loop
        while True:
            # Update last activity time
            last_activity = datetime.now()
            
            # Maintain WebSocket connection
            data = await websocket.receive_text()
            
            # Echo back to keep connection active
            await websocket.send_json({
                "status": "connected", 
                "echo": data, 
                "timestamp": last_activity.isoformat()
            })
            logger.info(f"Received message from WebSocket: {data}")
    except WebSocketDisconnect:
        logger.info("WebSocket client disconnected")
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
    finally:
        # Always clean up properly
        manager.disconnect(websocket)
        # Cancel ping task if it's still running
        try:
            ping_task.cancel()
            await ping_task
        except (UnboundLocalError, asyncio.CancelledError):
            # ping_task wasn't created or already cancelled
            pass

# Function to send notifications over WebSocket
async def send_notification(data: dict):
    """
    Send notification to all active WebSocket connections.
    
    This function is used to notify admin bots about new issues or questions that need attention.
    It's triggered when the system cannot answer a user's question (response starts with "I'm sorry").
    
    Args:
        data: The data to send as notification
    """
    try:
        # Log number of active connections and notification attempt
        logger.info(f"Attempting to send notification. Active connections: {len(manager.active_connections)}")
        logger.info(f"Notification data: session_id={data.get('session_id')}, user_id={data.get('user_id')}")
        logger.info(f"Response: {data.get('response', '')[:50]}...")
        
        # Check if the response starts with "I'm sorry"
        response = data.get('response', '')
        if not response or not isinstance(response, str):
            logger.warning(f"Invalid response format in notification data: {response}")
            return
            
        if not response.strip().lower().startswith("i'm sorry"):
            logger.info(f"Response doesn't start with 'I'm sorry', notification not needed: {response[:50]}...")
            return
            
        logger.info(f"Response starts with 'I'm sorry', sending notification")
        
        # Format the notification data for admin - format theo chuẩn Admin_bot
        notification_data = {
            "type": "sorry_response",  # Đổi type thành sorry_response để phù hợp với Admin_bot
            "timestamp": get_local_time(),
            "user_id": data.get('user_id', 'unknown'),
            "message": data.get('message', ''),
            "response": response,
            "session_id": data.get('session_id', 'unknown'),
            "user_info": {
                "first_name": data.get('first_name', 'User'),
                "last_name": data.get('last_name', ''),
                "username": data.get('username', '')
            }
        }
        
        # Check if there are active connections
        if not manager.active_connections:
            logger.warning("No active WebSocket connections for notification broadcast")
            return
        
        # Broadcast notification to all active connections
        logger.info(f"Broadcasting notification to {len(manager.active_connections)} connections")
        await manager.broadcast(notification_data)
        logger.info("Notification broadcast completed successfully")
        
    except Exception as e:
        logger.error(f"Error sending notification: {e}")
        import traceback
        logger.error(traceback.format_exc())