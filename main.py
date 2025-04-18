"""
Solana SuperTeam Admin Bot
This bot manages content for the Solana SuperTeam User Bot.
It can add events, FAQs, and other information that will be displayed by the User Bot.
"""

import os
import logging
import json
import asyncio
import requests
from datetime import datetime
from dotenv import load_dotenv
from telegram import Update, Bot
from telegram.ext import Application, CommandHandler, ContextTypes
import urllib.parse
import threading
import time
import nest_asyncio

# Apply nest_asyncio to allow nested event loops
nest_asyncio.apply()

# Configure logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()

# Get configuration from environment variables
ADMIN_TELEGRAM_BOT_TOKEN = os.getenv("ADMIN_TELEGRAM_BOT_TOKEN")
API_DATABASE_URL = os.getenv("API_DATABASE_URL")
ADMIN_GROUP_CHAT_ID = os.getenv("ADMIN_GROUP_CHAT_ID")

# Global state
websocket_connection = False

# Helper function to fix URL paths
def fix_url(base_url, path):
    """Create a properly formatted URL without double slashes."""
    if not base_url:
        return path
        
    # Remove trailing slash from base URL
    if base_url.endswith('/'):
        base_url = base_url[:-1]
        
    # Remove leading slash from path
    if path.startswith('/'):
        path = path[1:]
        
    return f"{base_url}/{path}"

def get_vietnam_time():
    """Get current time in Vietnam timezone format."""
    now = datetime.now()
    return now.strftime("%Y-%m-%d %H:%M:%S")

async def send_status_message(chat_id=None):
    """Send a message about the backend connection status."""
    # If no chat ID is provided, use the admin group
    if not chat_id and ADMIN_GROUP_CHAT_ID:
        chat_id = ADMIN_GROUP_CHAT_ID
    
    if not chat_id:
        logger.error("No chat ID provided for status message")
        return
    
    # Default statuses
    api_status = "❌ Not Connected"
    db_status = "❌ Not Connected"
    rag_status = "❌ Not Connected"
    
    # Check API health
    if API_DATABASE_URL:
        try:
            # Try health endpoint
            url = fix_url(API_DATABASE_URL, "/health")
            logger.info(f"Checking API health at: {url}")
            
            try:
                response = requests.get(url, timeout=10)
                if response.status_code == 200:
                    api_status = "✅ Connected"
                    db_status = "✅ Connected"  # Default if no detailed status
                    rag_status = "✅ Connected"  # Default if no detailed status
                    
                    # Check more specific statuses if needed
                    try:
                        # Check MongoDB specific status
                        mongo_url = fix_url(API_DATABASE_URL, "/mongodb/health")
                        logger.info(f"Checking MongoDB health at: {mongo_url}")
                        
                        mongo_response = requests.get(mongo_url, timeout=5)
                        if mongo_response.status_code != 200:
                            db_status = "⚠️ Partial Connection"
                            
                        # Check RAG specific status
                        rag_url = fix_url(API_DATABASE_URL, "/rag/health")
                        logger.info(f"Checking RAG health at: {rag_url}")
                        
                        rag_response = requests.get(rag_url, timeout=5)
                        if rag_response.status_code == 200:
                            rag_data = rag_response.json()
                            rag_status = "✅ Connected" if rag_data.get('status') == "healthy" else "⚠️ Issues Detected"
                        else:
                            rag_status = "❌ Not Connected"
                    except Exception as e:
                        logger.error(f"Error checking specific health endpoints: {e}")
                        pass
                else:
                    logger.error(f"Health check failed: {response.status_code} - {response.text}")
            except Exception as e:
                logger.error(f"Error checking API health: {e}")
        except Exception as e:
            logger.error(f"Error checking backend connection: {e}")
    
    # Check websocket connection
    ws_status = "✅ Connected" if websocket_connection else "❌ Not Connected"
    
    status_message = (
        "🤖 *Admin Bot Status Report*\n\n"
        f"🕒 Time: {get_vietnam_time()}\n"
        f"🔌 API: {api_status}\n"
        f"📊 Databases: {db_status}\n"
        f"🧠 RAG System: {rag_status}\n"
        f"📡 WebSocket: {ws_status}\n\n"
        "The bot is monitoring for user activities."
    )
    
    try:
        bot = Bot(token=ADMIN_TELEGRAM_BOT_TOKEN)
        await bot.send_message(
            chat_id=chat_id,
            text=status_message,
            parse_mode="Markdown"
        )
        logger.info(f"Status message sent to chat {chat_id}")
    except Exception as e:
        logger.error(f"Failed to send status message: {e}")

# Command handlers
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Send a message when the command /start is issued."""
    logger.info(f"Received /start command from {update.effective_user.id}")
    
    welcome_text = (
        "Hello, admin! I am the Solana SuperTeam Admin Bot. "
        "I can help you manage content for the User Bot.\n\n"
        "Type /status to check backend connections\n"
        "Type /help for more information"
    )
    
    await update.message.reply_text(welcome_text)
    
    # Also check and send status
    await status_command(update, context)

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Send a message when the command /help is issued."""
    logger.info(f"Received /help command from {update.effective_user.id}")
    
    help_text = (
        "Here are the available commands:\n\n"
        "/start - Start the bot\n"
        "/status - Check backend connection status\n"
        "/help - Show this help message\n\n"
        "The Admin Bot helps manage content for the User Bot by monitoring "
        "the backend system and allowing direct management of events, FAQs, "
        "and other information."
    )
    
    await update.message.reply_text(help_text)

async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Check and send status about backend connections."""
    logger.info(f"Received /status command from {update.effective_user.id}")
    
    await update.message.reply_text("Checking backend connections...")
    await send_status_message(update.effective_chat.id)

# WebSocket monitoring
async def websocket_listener():
    """Listen for user activity via WebSocket."""
    global websocket_connection
    
    if not API_DATABASE_URL:
        logger.error("Database URL not configured, cannot start WebSocket")
        return
    
    # Make sure websocket-client module is available
    try:
        import websocket
    except ImportError:
        logger.error("websocket-client module not installed. Please install it with 'pip install websocket-client'")
        return
    
    # Create Bot instance for use in other threads
    try:
        bot = Bot(token=ADMIN_TELEGRAM_BOT_TOKEN)
        logger.info("Telegram Bot instance created for notifications")
    except Exception as e:
        logger.error(f"Failed to create Telegram Bot instance: {e}")
        return
    
    # Create queue for notifications between WebSocket thread and main thread
    import queue
    notification_queue = queue.Queue()
    
    # Determine WebSocket URL from API_DATABASE_URL
    parsed_url = urllib.parse.urlparse(API_DATABASE_URL)
    
    # Determine protocol
    use_wss = parsed_url.scheme == "https"
    
    # Get hostname and port
    websocket_server = parsed_url.netloc.split(':')[0]
    # Hugging Face Space sử dụng cổng 443 mặc định
    websocket_port = parsed_url.port if parsed_url.port else (443 if use_wss else 80)
    
    # WebSocket path
    websocket_path = "/notify"
    
    # Create full URL
    if use_wss:
        # Cho Hugging Face Space và các dịch vụ HTTPS khác,
        # không cần chỉ định cổng nếu là 443
        if websocket_port == 443:
            ws_url = f"wss://{websocket_server}{websocket_path}"
        else:
            ws_url = f"wss://{websocket_server}:{websocket_port}{websocket_path}"
    else:
        if websocket_port == 80:
            ws_url = f"ws://{websocket_server}{websocket_path}"
        else:
            ws_url = f"ws://{websocket_server}:{websocket_port}{websocket_path}"
    
    logger.info(f"Connecting to WebSocket: {ws_url}")
    
    # Create an event loop for the thread
    thread_loop = asyncio.new_event_loop()
    asyncio.set_event_loop(thread_loop)
    
    # Define event handlers
    def on_message(ws, message):
        try:
            # Kiểm tra xem đây có phải phản hồi keepalive không
            if isinstance(message, str) and message.lower() == "keepalive" or "echo" in message:
                logger.debug("Received keepalive response")
                global websocket_connection
                websocket_connection = True
                return
            
            # Parse JSON message
            data = json.loads(message)
            logger.info(f"Received notification: {data}")
            
            # Cập nhật trạng thái kết nối
            global websocket_connection
            websocket_connection = True
            
            # Process notification by type
            if data.get("type") == "new_session":
                session_data = data.get("data", {})
                user_question = session_data.get("message", "")
                user_response = session_data.get("response", "")
                user_name = session_data.get("first_name", "Unknown User")
                
                # Log question information
                logger.info(f"User {user_name} asked: {user_question}")
                logger.info(f"System response: {user_response}")
                
                # Add to queue for processing in main thread
                if ADMIN_GROUP_CHAT_ID:
                    notification = {
                        "type": "question",
                        "first_name": session_data.get('first_name', ''),
                        "last_name": session_data.get('last_name', ''),
                        "user_id": session_data.get('user_id', ''),
                        "created_at": session_data.get('created_at', ''),
                        "question": user_question,
                        "response": user_response,
                        "session_id": session_data.get('session_id', '')
                    }
                    notification_queue.put(notification)
        except json.JSONDecodeError:
            # Handle non-JSON messages (e.g., keepalive responses)
            logger.debug(f"Received non-JSON message: {message}")
            
            # Ngay cả khi không phải JSON, vẫn nhận được phản hồi từ server
            # nên cập nhật trạng thái kết nối
            global websocket_connection
            websocket_connection = True
        except Exception as e:
            logger.error(f"Error processing message: {e}")
    
    def on_error(ws, error):
        logger.error(f"WebSocket error: {error}")
        global websocket_connection
        websocket_connection = False
        
        # Add error notification to queue
        if ADMIN_GROUP_CHAT_ID:
            notification_queue.put({
                "type": "error",
                "message": f"WebSocket error: {error}"
            })
    
    def on_close(ws, close_status_code, close_msg):
        logger.warning(f"WebSocket connection closed: code={close_status_code}, message={close_msg}")
        global websocket_connection
        websocket_connection = False
    
    def on_open(ws):
        logger.info(f"WebSocket connection opened to {ws_url}")
        global websocket_connection
        websocket_connection = True
        
        # Add success notification to queue
        if ADMIN_GROUP_CHAT_ID:
            notification_queue.put({
                "type": "success",
                "message": "WebSocket connected successfully! Now monitoring user questions."
            })
        
        # Start keepalive thread
        def send_keepalive_thread():
            while True:
                try:
                    if ws.sock and ws.sock.connected:
                        ws.send("keepalive")
                        logger.info("Sent keepalive message")
                    time.sleep(300)  # 5 minutes as per API docs
                except Exception as e:
                    logger.error(f"Error sending keepalive: {e}")
                    time.sleep(60)  # Retry after 1 minute if error
                    
        keepalive_thread = threading.Thread(target=send_keepalive_thread, daemon=True)
        keepalive_thread.start()
    
    # Initialize and run WebSocket client in a loop for automatic reconnection
    def run_websocket_client():
        # Set the event loop for this thread
        asyncio.set_event_loop(thread_loop)
        
        # Thêm tính năng backoff để tránh thử kết nối lại quá nhanh
        retry_count = 0
        max_retry_count = 10
        
        while True:
            try:
                # Reset kết nối nếu đã thử quá nhiều lần
                if retry_count >= max_retry_count:
                    logger.warning(f"Reached max retry count ({max_retry_count}). Resetting retry counter.")
                    retry_count = 0
                    time.sleep(30)  # Chờ lâu hơn trước khi thử lại
                
                # Tạo đối tượng websocket với các tùy chọn SSL nếu cần
                websocket.enableTrace(True if retry_count > 5 else False)  # Bật trace nếu nhiều lần thử không thành công
                
                # Tạo WebSocket app với các đầu mục xử lý sự kiện
                ws = websocket.WebSocketApp(
                    ws_url,
                    on_open=on_open,
                    on_message=on_message,
                    on_error=on_error,
                    on_close=on_close
                )
                
                # Thêm các tùy chọn SSL nếu dùng wss://
                if ws_url.startswith("wss://"):
                    logger.info("Using secure WebSocket connection with SSL options")
                    
                    # Tùy chỉnh các tham số ping để giữ kết nối lâu dài
                    ws.run_forever(
                        ping_interval=60,   # Gửi ping mỗi 60 giây
                        ping_timeout=30,    # Thời gian chờ pong
                        sslopt={"cert_reqs": 0}  # Bỏ qua xác thực SSL certificate
                    )
                else:
                    # Chạy với ping/pong bình thường
                    ws.run_forever(ping_interval=60, ping_timeout=30)
                
                # Nếu code chạy đến đây, kết nối đã bị đóng
                logger.warning("WebSocket connection lost, reconnecting...")
                
                # Tính backoff time dựa trên số lần thử
                backoff_time = min(5 * (2 ** retry_count), 300)  # Tối đa 5 phút
                logger.info(f"Waiting {backoff_time} seconds before reconnecting...")
                time.sleep(backoff_time)
                
                # Tăng số lần thử kết nối
                retry_count += 1
                
            except Exception as e:
                logger.error(f"WebSocket client error: {e}")
                logger.info("Reconnecting in 5 seconds...")
                time.sleep(5)
                retry_count += 1
    
    # Run WebSocket client in a separate thread
    websocket_thread = threading.Thread(target=run_websocket_client, daemon=True)
    websocket_thread.start()
    
    # Main loop to process notifications from queue
    while True:
        try:
            # Check if WebSocket thread has died
            if not websocket_thread.is_alive():
                logger.warning("WebSocket thread died, restarting...")
                websocket_thread = threading.Thread(target=run_websocket_client, daemon=True)
                websocket_thread.start()
            
            # Process notifications in queue
            try:
                # Don't wait too long to check thread periodically
                notification = notification_queue.get(timeout=5)
                
                if ADMIN_GROUP_CHAT_ID:
                    message_text = ""
                    
                    if notification["type"] == "question":
                        message_text = (
                            f"❓ *Question from {notification['first_name']}*:\n{notification['question']}\n\n"
                            f"🤖 *System response*:\n{notification['response']}\n\n"
                            f"🆔 Session ID: `{notification['session_id']}`"
                        )
                    elif notification["type"] == "error":
                        message_text = f"❌ {notification['message']}\nTrying to reconnect in 5 seconds..."
                    elif notification["type"] == "success":
                        message_text = f"✅ {notification['message']}"
                    
                    if message_text:
                        await bot.send_message(
                            chat_id=ADMIN_GROUP_CHAT_ID,
                            text=message_text,
                            parse_mode="Markdown"
                        )
                        logger.info(f"Notification sent to admin group: {notification['type']}")
                
            except queue.Empty:
                # Timeout is just for thread checking, not an error
                pass
            except Exception as e:
                logger.error(f"Error processing notification: {e}")
                
            # Wait a bit before checking again
            await asyncio.sleep(1)
        
        except Exception as e:
            logger.error(f"Error in main websocket loop: {e}")
            await asyncio.sleep(5)  # Wait before trying again 