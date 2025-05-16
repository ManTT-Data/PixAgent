from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Depends, status, Query
from typing import List, Dict, Optional
import logging
from datetime import datetime
import asyncio
import json
import os
from dotenv import load_dotenv
from app.database.mongodb import session_collection
from app.utils.utils import get_local_time
from starlette.websockets import WebSocketState

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

# Store active WebSocket connections by user_id
active_connections: Dict[str, List[WebSocket]] = {}

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
    - Session response starts with "I don't know"
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
            "type": "new_session",
            "timestamp": "YYYY-MM-DD HH:MM:SS",
            "data": {
                "session_id": "session id",
                "factor": "user",
                "action": "action type",
                "message": "User question",
                "response": "I don't know...",
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
                if data.get("type") == "new_session":
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
    await websocket.accept()
    try:
        while True:
            # Maintain WebSocket connection
            data = await websocket.receive_text()
            # Echo back to keep connection active
            await websocket.send_json({"status": "connected", "echo": data, "timestamp": datetime.now().isoformat()})
            logger.info(f"Received message from WebSocket: {data}")
    except WebSocketDisconnect:
        logger.info("WebSocket client disconnected")

# Function to send notifications over WebSocket
async def send_notification(data: dict):
    """
    Send notification to all active WebSocket connections.
    
    This function is used to notify admin bots about new issues or questions that need attention.
    It's triggered when the system cannot answer a user's question (response starts with "I don't know").
    
    Args:
        data: The data to send as notification
    """
    try:
        # Log number of active connections and notification attempt
        logger.info(f"Attempting to send notification. Active connections: {len(active_connections)}")
        logger.info(f"Notification data: session_id={data.get('session_id')}, user_id={data.get('user_id')}")
        logger.info(f"Response: {data.get('response', '')[:50]}...")
        
        # Check if the response starts with "I don't know"
        response = data.get('response', '')
        if not response or not isinstance(response, str):
            logger.warning(f"Invalid response format in notification data: {response}")
            return
            
        if not response.strip().lower().startswith("i don't know"):
            logger.info(f"Response doesn't start with 'I don't know', notification not needed: {response[:50]}...")
            return
            
        logger.info(f"Response starts with 'I don't know', sending notification")
        
        # Format the notification data for admin
        notification_data = {
            "type": "new_session",
            "timestamp": get_local_time(),
            "data": {
                "session_id": data.get('session_id', 'unknown'),
                "user_id": data.get('user_id', 'unknown'),
                "message": data.get('message', ''),
                "response": response,
                "first_name": data.get('first_name', 'User'),
                "last_name": data.get('last_name', ''),
                "username": data.get('username', ''),
                "created_at": data.get('created_at', get_local_time()),
                "action": data.get('action', 'unknown'),
                "factor": "user"  # Always show as user for better readability
            }
        }
        
        # Check if there are active connections
        if not active_connections:
            logger.warning("No active WebSocket connections for notification broadcast")
            return
        
        # Broadcast notification to all active connections
        logger.info(f"Broadcasting notification to {len(active_connections)} connections")
        for user_id, connections in active_connections.items():
            for connection in connections:
                try:
                    await connection.send_json(notification_data)
                    logger.info(f"Message sent to WebSocket connection for user {user_id}")
                except Exception as e:
                    logger.error(f"Error sending notification to user {user_id}: {e}")
        logger.info("Notification broadcast completed successfully")
        
    except Exception as e:
        logger.error(f"Error sending notification: {e}")
        import traceback
        logger.error(traceback.format_exc())

@router.websocket("/status")
async def websocket_endpoint(websocket: WebSocket):
    """General WebSocket endpoint for notifications"""
    await websocket.accept()
    try:
        while True:
            # Wait for messages
            data = await websocket.receive_text()
            await websocket.send_text(f"Message received: {data}")
    except WebSocketDisconnect:
        logger.info("WebSocket client disconnected")

@router.websocket("/status/{user_id}")
async def websocket_user_status(websocket: WebSocket, user_id: str):
    """User-specific WebSocket for status updates and notifications"""
    await websocket.accept()
    
    # Add connection to active connections for this user
    if user_id not in active_connections:
        active_connections[user_id] = []
    active_connections[user_id].append(websocket)
    
    logger.info(f"WebSocket connection established for user {user_id}")
    
    try:
        # Send initial connection message
        await websocket.send_json({
            "event": "connected",
            "message": "WebSocket connection established"
        })
        
        # Main loop to handle incoming messages
        while True:
            # Wait for messages
            data = await websocket.receive_text()
            # Process message and send response
            await websocket.send_json({
                "event": "message_received",
                "data": data
            })
    except WebSocketDisconnect:
        logger.info(f"WebSocket disconnected for user {user_id}")
    except Exception as e:
        logger.error(f"WebSocket error for user {user_id}: {str(e)}")
    finally:
        # Remove connection from active connections
        if user_id in active_connections:
            active_connections[user_id].remove(websocket)
            if not active_connections[user_id]:
                del active_connections[user_id]
        logger.info(f"WebSocket connection removed for user {user_id}")

async def send_notification_to_user(user_id: str, event: str, data: dict):
    """
    Send notification to a specific user via WebSocket
    
    Args:
        user_id: User ID
        event: Event type
        data: Notification data
    """
    if user_id not in active_connections:
        logger.warning(f"No active WebSocket connection for user {user_id}")
        return
    
    message = {
        "event": event,
        "data": data
    }
    
    # Send to all connections for this user
    disconnected = []
    for i, connection in enumerate(active_connections[user_id]):
        try:
            if connection.client_state == WebSocketState.CONNECTED:
                await connection.send_json(message)
            else:
                disconnected.append(i)
        except Exception as e:
            logger.error(f"Error sending notification to user {user_id}: {str(e)}")
            disconnected.append(i)
    
    # Remove disconnected connections
    for i in sorted(disconnected, reverse=True):
        try:
            del active_connections[user_id][i]
        except:
            pass
    
    # Clean up empty user entries
    if user_id in active_connections and not active_connections[user_id]:
        del active_connections[user_id]

async def send_pdf_upload_progress(user_id: str, file_id: str, step: str, progress: float, message: str):
    """
    Send PDF upload progress via WebSocket
    
    Args:
        user_id: User ID
        file_id: File ID
        step: Current processing step
        progress: Progress value (0.0 to 1.0)
        message: Status message
    """
    await send_notification_to_user(user_id, "pdf_upload_progress", {
        "file_id": file_id,
        "step": step,
        "progress": progress,
        "message": message
    })

async def send_pdf_upload_started(user_id: str, filename: str, file_id: str):
    """
    Notify user that PDF upload has started
    
    Args:
        user_id: User ID
        filename: Original filename
        file_id: File ID for tracking
    """
    await send_notification_to_user(user_id, "pdf_upload_started", {
        "file_id": file_id,
        "filename": filename,
        "message": f"Started uploading {filename}"
    })

async def send_pdf_upload_completed(user_id: str, file_id: str, filename: str, chunks_processed: int):
    """
    Notify user that PDF upload has completed
    
    Args:
        user_id: User ID
        file_id: File ID
        filename: Original filename
        chunks_processed: Number of chunks processed
    """
    await send_notification_to_user(user_id, "pdf_upload_completed", {
        "file_id": file_id,
        "filename": filename,
        "chunks_processed": chunks_processed,
        "message": f"Completed processing {filename} with {chunks_processed} chunks"
    })

async def send_pdf_upload_failed(user_id: str, file_id: str, filename: str, error: str):
    """
    Notify user that PDF upload has failed
    
    Args:
        user_id: User ID
        file_id: File ID
        filename: Original filename
        error: Error message
    """
    await send_notification_to_user(user_id, "pdf_upload_failed", {
        "file_id": file_id,
        "filename": filename,
        "error": error,
        "message": f"Failed to process {filename}: {error}"
    })