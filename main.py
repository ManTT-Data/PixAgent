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
import aiohttp
from telegram.constants import ParseMode


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

# Display warning if ADMIN_GROUP_CHAT_ID is not set
if not ADMIN_GROUP_CHAT_ID:
    logging.warning("⚠️ ADMIN_GROUP_CHAT_ID is not set. Notifications cannot be sent to admin group!")
    logging.warning("Please set ADMIN_GROUP_CHAT_ID environment variable to receive notifications")
else:
    logging.info(f"Admin notifications will be sent to chat ID: {ADMIN_GROUP_CHAT_ID}")

# Global state
websocket_connection = False
last_alert_time = 0
ALERT_INTERVAL_SECONDS = 300  # 5 minutes between alerts

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

def escape_markdown(text):
    """Escape special characters for Markdown formatting."""
    if text is None:
        return ""
    
    # Return empty string for None or empty text
    if not text:
        return ""
        
    # Characters that need to be escaped in Markdown v2
    escape_chars = ['_', '*', '[', ']', '(', ')', '~', '`', '>', '#', '+', '-', '=', '|', '{', '}', '.', '!']
    
    # Create a new string with escaped characters
    result = ""
    for char in text:
        if char in escape_chars:
            result += f"\\{char}"
        else:
            result += char
            
    return result

def get_current_time():
    """Get current time in standard format."""
    now = datetime.now()
    return now.strftime("%Y-%m-%d %H:%M:%S")

async def send_status_message(chat_id=None, custom_message=None, alert=False):
    """Send a message about the backend connection status."""
    # Nếu không có chat_id thì dùng ADMIN_GROUP_CHAT_ID
    if not chat_id and ADMIN_GROUP_CHAT_ID:
        chat_id = ADMIN_GROUP_CHAT_ID
    if not chat_id:
        logger.error("No chat ID provided for status message")
        return

    # Build nội dung message
    if custom_message:
        status_message = custom_message
    else:
        api_status = "❌ Không kết nối"
        db_status = "❌ Không kết nối"
        rag_status = "❌ Không kết nối"
        if API_DATABASE_URL:
            try:
                url = fix_url(API_DATABASE_URL, "/health")
                logger.info(f"Checking API health at: {url}")
                response = requests.get(url, timeout=10)
                if response.status_code == 200:
                    api_status = "✅ Đã kết nối"
                    db_status = "✅ Đã kết nối"
                    rag_status = "✅ Đã kết nối"
                    try:
                        mongo_url = fix_url(API_DATABASE_URL, "/mongodb/health")
                        mongo_resp = requests.get(mongo_url, timeout=5)
                        if mongo_resp.status_code != 200:
                            db_status = "⚠️ Kết nối một phần"
                        rag_url = fix_url(API_DATABASE_URL, "/rag/health")
                        rag_resp = requests.get(rag_url, timeout=5)
                        if rag_resp.status_code == 200:
                            rag_data = rag_resp.json()
                            rag_status = "✅ Đã kết nối" if rag_data.get("status")=="healthy" else "⚠️ Phát hiện vấn đề"
                        else:
                            rag_status = "❌ Không kết nối"
                    except Exception as e:
                        logger.error(f"Error checking specific health endpoints: {e}")
                else:
                    logger.error(f"Health check failed: {response.status_code} - {response.text}")
            except Exception as e:
                logger.error(f"Error checking backend connection: {e}")

        # Check admin websocket status
        admin_id = os.getenv("ADMIN_ID", "admin-bot-123")
        admin_status = "✅ Đã kết nối" if websocket_connection else "❌ Không kết nối"
        
        # Try to get detailed admin websocket status
        try:
            admin_ws_url = fix_url(API_DATABASE_URL, f"/admin/ws/status/{admin_id}")
            admin_ws_resp = requests.get(admin_ws_url, timeout=5)
            if admin_ws_resp.status_code == 200:
                admin_ws_data = admin_ws_resp.json()
                admin_status = "✅ Đã kết nối" if admin_ws_data.get("active") else "❌ Không kết nối"
        except Exception as e:
            logger.error(f"Error checking admin websocket status: {e}")
        
        status_message = (
            "🤖 *Báo cáo trạng thái Admin Bot*\n\n"
            f"🕒 Thời gian: {get_current_time()}\n"
            f"🔌 API: {api_status}\n"
            f"📊 Cơ sở dữ liệu: {db_status}\n"
            f"🧠 Hệ thống RAG: {rag_status}\n"
            f"📡 Admin WebSocket: {admin_status}\n\n"
            "Bot đang giám sát hoạt động người dùng."
        )
        status_message = escape_markdown(status_message)

    if alert:
        status_message = f"⚠️ *CẢNH BÁO* ⚠️\n\n{status_message}"

    try:
        bot = Bot(token=ADMIN_TELEGRAM_BOT_TOKEN)
        await bot.send_message(
            chat_id=chat_id,
            text=status_message,
            parse_mode=ParseMode.MARKDOWN_V2
        )
        logger.info(f"Status message sent to chat {chat_id}")
    except Exception as e:
        logger.error(f"Failed to send status message: {e}")
        # Fallback không format
        try:
            plain = status_message.replace('*','').replace('`','').replace('_','')
            await bot.send_message(
                chat_id=chat_id,
                text=plain,
                parse_mode=None
            )
            logger.info("Message sent without formatting")
        except Exception as fe:
            logger.error(f"Fallback send failed: {fe}")

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
    await send_status_message(chat_id=update.effective_chat.id)

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
    # Hugging Face Space uses port 443 by default
    websocket_port = parsed_url.port if parsed_url.port else (443 if use_wss else 80)
    
    # Create admin_id (can be any unique string for this admin)
    admin_id = os.getenv("ADMIN_ID", "admin-bot-123")
    
    # WebSocket path for admin monitoring
    # Sử dụng đúng endpoint của backend theo tài liệu API
    websocket_path = f"/admin/ws/monitor/{admin_id}"
    
    # Create full URL
    if use_wss:
        # Sử dụng HTTPS/WSS
        if websocket_port == 443:
            ws_url = f"wss://{websocket_server}{websocket_path}"
        else:
            ws_url = f"wss://{websocket_server}:{websocket_port}{websocket_path}"
    else:
        # Sử dụng HTTP/WS
        if websocket_port == 80:
            ws_url = f"ws://{websocket_server}{websocket_path}"
        else:
            ws_url = f"ws://{websocket_server}:{websocket_port}{websocket_path}"

    # Ghi log URL cuối cùng để debug
    logger.info(f"Connecting to Admin WebSocket: {ws_url}")
    
    # Create an event loop for the thread
    thread_loop = asyncio.new_event_loop()
    asyncio.set_event_loop(thread_loop)
    
    # Define event handlers
    def on_message(ws, message):
        global websocket_connection
        try:
            # Check if this is a keepalive response
            if isinstance(message, str) and (message.lower() == "keepalive" or "echo" in message or "ping" in message):
                logger.debug("Received keepalive response")
                websocket_connection = True
                return
            
            # Parse JSON message
            data = json.loads(message)
            logger.info(f"Received notification: {data}")
            
            # Update connection status
            websocket_connection = True
            
            # Xử lý tin nhắn theo định dạng của backend (/admin/ws/monitor/{admin_id})
            if data.get("type") == "sorry_response":
                # Extract data according to the admin websocket guide format
                user_id = data.get("user_id", "")
                user_message = data.get("message", "")
                bot_response = data.get("response", "")
                session_id = data.get("session_id", "")
                timestamp = data.get("timestamp", "")
                user_info = data.get("user_info", {})
                
                # Extract user info
                first_name = user_info.get("first_name", "")
                last_name = user_info.get("last_name", "")
                username = user_info.get("username", "")
                
                # Log question information
                logger.info(f"User {first_name} {last_name} asked: {user_message}")
                logger.info(f"System response (I'm sorry): {bot_response}")
                
                # Add to queue for processing in main thread
                if ADMIN_GROUP_CHAT_ID:
                    notification = {
                        "type": "sorry_response",
                        "first_name": first_name,
                        "last_name": last_name,
                        "user_id": user_id,
                        "username": username,
                        "created_at": timestamp,
                        "question": user_message,
                        "response": bot_response,
                        "session_id": session_id
                    }
                    notification_queue.put(notification)
            
            # For backward compatibility with new_session type
            elif data.get("type") == "new_session":
                # Extract data from the notification
                session_data = data.get("data", {})
                user_message = session_data.get("message", "")
                bot_response = session_data.get("response", "")
                
                # Skip if the response doesn't start with "I'm sorry"
                if not (bot_response and bot_response.lower().startswith("i'm sorry")):
                    logger.debug("Response doesn't start with 'I'm sorry', ignoring")
                    return
                
                # Extract user info
                user_id = session_data.get("user_id", "")
                first_name = session_data.get("first_name", "")
                last_name = session_data.get("last_name", "")
                username = session_data.get("username", "")
                timestamp = session_data.get("created_at", "")
                session_id = session_data.get("session_id", "")
                
                # Log question information
                logger.info(f"User {first_name} {last_name} received an 'I'm sorry' response")
                logger.info(f"Question: {user_message}")
                logger.info(f"Response: {bot_response}")
                
                # Add to queue for processing in main thread
                if ADMIN_GROUP_CHAT_ID:
                    notification = {
                        "type": "sorry_response",
                        "first_name": first_name,
                        "last_name": last_name,
                        "user_id": user_id,
                        "username": username,
                        "created_at": timestamp,
                        "question": user_message,
                        "response": bot_response,
                        "session_id": session_id
                    }
                    notification_queue.put(notification)
        except json.JSONDecodeError:
            # Handle non-JSON messages (e.g., keepalive responses)
            logger.debug(f"Received non-JSON message: {message}")
            
            # Even when not JSON, we still got a response from the server
            # so update connection status
            websocket_connection = True
        except Exception as e:
            logger.error(f"Error processing message: {e}")
            logger.error(f"Message content: {message}")
    
    def on_error(ws, error):
        global websocket_connection
        logger.error(f"WebSocket error: {error}")
        websocket_connection = False
        
        # Add error notification to queue
        if ADMIN_GROUP_CHAT_ID:
            notification_queue.put({
                "type": "error",
                "message": f"WebSocket error: {error}"
            })
    
    def on_close(ws, close_status_code, close_msg):
        global websocket_connection
        logger.warning(f"WebSocket connection closed: code={close_status_code}, message={close_msg}")
        websocket_connection = False
    
    def on_open(ws):
        global websocket_connection
        logger.info(f"WebSocket connection opened to {ws_url}")
        websocket_connection = True
        
        # Add success notification to queue
        if ADMIN_GROUP_CHAT_ID:
            notification_queue.put({
                "type": "success",
                "message": "Admin WebSocket connected successfully! Now monitoring for 'I'm sorry' responses."
            })
        
        # Start keepalive thread
        def send_keepalive_thread():
            while True:
                try:
                    if ws.sock and ws.sock.connected:
                        try:
                            # Format 1: JSON with action ping (per admin guide)
                            ws.send(json.dumps({"action": "ping"}))
                            logger.info("Sent keepalive message (JSON format)")
                        except Exception as e1:
                            logger.error(f"Error sending JSON keepalive: {e1}")
                            
                            try:
                                # Format 2: Simple string "keepalive"
                                ws.send("keepalive")
                                logger.info("Sent keepalive message (string format)")
                            except Exception as e2:
                                logger.error(f"Error sending string keepalive: {e2}")
                    
                    time.sleep(300)  # 5 minutes as per API docs
                except Exception as e:
                    logger.error(f"Error in keepalive thread: {e}")
                    time.sleep(60)  # Retry after 1 minute if error
                    
        keepalive_thread = threading.Thread(target=send_keepalive_thread, daemon=True)
        keepalive_thread.start()
    
    # Initialize and run WebSocket client in a loop for automatic reconnection
    def run_websocket_client():
        # Set the event loop for this thread
        asyncio.set_event_loop(thread_loop)
        
        # Add backoff feature to prevent reconnecting too quickly
        retry_count = 0
        max_retry_count = 10
        
        while True:
            try:
                # Reset connection if tried too many times
                if retry_count >= max_retry_count:
                    logger.warning(f"Reached max retry count ({max_retry_count}). Resetting retry counter.")
                    retry_count = 0
                    time.sleep(30)  # Wait longer before retrying
                
                # Create websocket object with SSL options if needed
                websocket.enableTrace(True if retry_count > 5 else False)  # Enable trace if many connection attempts failed
                
                # Create WebSocket app with event handlers
                ws = websocket.WebSocketApp(
                    ws_url,
                    on_open=on_open,
                    on_message=on_message,
                    on_error=on_error,
                    on_close=on_close
                )
                
                # Add SSL options if using wss://
                if ws_url.startswith("wss://"):
                    logger.info("Using secure WebSocket connection with SSL options")
                    
                    # Customize ping parameters for long-term connection
                    ws.run_forever(
                        ping_interval=60,   # Send ping every 60 seconds
                        ping_timeout=30,    # Timeout for pong
                        sslopt={"cert_reqs": 0}  # Skip SSL certificate validation
                    )
                else:
                    # Run with normal ping/pong
                    ws.run_forever(ping_interval=60, ping_timeout=30)
                
                # If code reaches here, connection has been closed
                logger.warning("WebSocket connection lost, reconnecting...")
                
                # Calculate backoff time based on retry count
                backoff_time = min(5 * (2 ** retry_count), 300)  # Maximum 5 minutes
                logger.info(f"Waiting {backoff_time} seconds before reconnecting...")
                time.sleep(backoff_time)
                
                # Increase connection retry count
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
                    
                    if notification["type"] == "sorry_response":
                        # Format full name
                        user_full_name = f"{notification['first_name']} {notification['last_name']}".strip()
                        # Format username with @ if available
                        username_display = f" (@{notification['username']})" if notification['username'] else ""
                        
                        # Escape special characters for Markdown
                        escaped_question = escape_markdown(notification['question'])
                        escaped_response = escape_markdown(notification['response'])
                        escaped_session_id = escape_markdown(notification['session_id'])
                        
                        message_text = (
                            f"🚨 *Phát hiện phản hồi \"I'm sorry\"*\n"
                            f"👤 Người dùng: {escape_markdown(user_full_name)}{escape_markdown(username_display)}\n"
                            f"💬 Câu hỏi: {escaped_question}\n"
                            f"🤖 Phản hồi: {escaped_response}\n"
                            f"🕒 Thời gian: {notification['created_at']}\n"
                            f"🆔 Session ID: `{escaped_session_id}`"
                        )
                    elif notification["type"] == "error":
                        message_text = f"❌ {escape_markdown(notification['message'])}\nĐang thử kết nối lại sau 5 giây..."
                    elif notification["type"] == "success":
                        message_text = f"✅ {escape_markdown(notification['message'])}"
                    
                    if message_text:
                        try:
                            logger.debug(f"Sending notification to chat ID: {ADMIN_GROUP_CHAT_ID}")
                            await bot.send_message(
                                chat_id=ADMIN_GROUP_CHAT_ID,
                                text=message_text,
                                parse_mode=ParseMode.MARKDOWN_V2
                            )
                            logger.info(f"Notification sent to admin group: {notification['type']}")
                        except Exception as e:
                            logger.error(f"Error sending notification: {e}")
                            
                            # Try without Markdown formatting
                            try:
                                logger.info("Trying to send notification without Markdown formatting")
                                # Create plain text by removing all special characters
                                plain_text = message_text.replace('*', '').replace('`', '').replace('_', '')
                                
                                # Log the message for debugging
                                logger.debug(f"Sending plain text notification: {plain_text[:100]}...")
                                
                                await bot.send_message(
                                    chat_id=ADMIN_GROUP_CHAT_ID,
                                    text=plain_text,
                                    parse_mode=None
                                )
                                logger.info("Notification sent without formatting")
                            except Exception as fallback_error:
                                logger.error(f"Failed to send notification even without formatting: {fallback_error}")
                                logger.error(f"Make sure ADMIN_GROUP_CHAT_ID is correctly set: {ADMIN_GROUP_CHAT_ID}")
                
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

async def check_websocket_connection():
    """Check the health of the API and its services, log and alert if problems are found."""
    try:
        global websocket_connection, last_alert_time
        # Chuyển đổi URL WebSocket sang HTTP để check API
        http_endpoint = API_DATABASE_URL
        
        # Đảm bảo endpoint là HTTP/HTTPS, không phải WS/WSS
        if http_endpoint.startswith('ws://'):
            http_endpoint = http_endpoint.replace('ws://', 'http://')
        elif http_endpoint.startswith('wss://'):
            http_endpoint = http_endpoint.replace('wss://', 'https://')
        
        # Format the endpoint for the admin WebSocket status check
        admin_id = os.getenv("ADMIN_ID", "admin-bot-123")
        admin_ws_status_endpoint = f"{http_endpoint}/admin/ws/status/{admin_id}"
        
        logger.debug(f"Checking admin WebSocket status at: {admin_ws_status_endpoint}")
        
        # Check the API health and admin WebSocket status
        try:
            async with aiohttp.ClientSession() as session:
                # First check general API health
                health_endpoint = f"{http_endpoint}/health"
                async with session.get(health_endpoint, timeout=10) as response:
                    if response.status == 200:
                        health_data = await response.json()
                        logger.debug(f"Health data: {health_data}")
                        
                        # Check MongoDB and RAG status from health data
                        mongo_status = health_data.get('mongodb', False)
                        rag_status = health_data.get('rag_system', False)
                        
                        # Now check admin WebSocket status
                        admin_ws_active = False
                        try:
                            async with session.get(admin_ws_status_endpoint, timeout=5) as ws_response:
                                if ws_response.status == 200:
                                    ws_status_data = await ws_response.json()
                                    admin_ws_active = ws_status_data.get('active', False)
                                    logger.debug(f"Admin WebSocket status: {ws_status_data}")
                                else:
                                    logger.warning(f"Admin WebSocket status check failed: {ws_response.status}")
                        except Exception as ws_err:
                            logger.error(f"Error checking admin WebSocket status: {ws_err}")
                        
                        # Create status message in Vietnamese
                        status_message = "📊 Trạng thái hệ thống:\n"
                        status_message += "🔄 API: Trực tuyến ✅\n"
                        status_message += f"🗄️ MongoDB: {'Trực tuyến ✅' if mongo_status else 'Ngoại tuyến ❌'}\n"
                        status_message += f"🧠 RAG System: {'Trực tuyến ✅' if rag_status else 'Ngoại tuyến ❌'}\n"
                        status_message += f"🔌 Admin WebSocket: {'Đã kết nối ✅' if websocket_connection and admin_ws_active else 'Mất kết nối ❌'}"
                        
                        # Check overall system status and alert if needed
                        if not (mongo_status and rag_status and websocket_connection and admin_ws_active):
                            logger.warning(f"Some services are down: MongoDB={mongo_status}, RAG={rag_status}, WebSocket={websocket_connection}, AdminWS={admin_ws_active}")
                            # Alert admin if we haven't sent an alert recently
                            current_time = time.time()
                            if current_time - last_alert_time > ALERT_INTERVAL_SECONDS:
                                await send_status_message(custom_message=status_message, alert=True)
                                last_alert_time = current_time
                        else:
                            websocket_connection = True
                            logger.debug("All services are operational")
                    else:
                        logger.error(f"Health check failed with status code: {response.status}")
                        # Alert about API being down
                        current_time = time.time()
                        if current_time - last_alert_time > ALERT_INTERVAL_SECONDS:
                            status_message = "📊 Trạng thái hệ thống:\n🔄 API: Ngoại tuyến ❌ (Mã trạng thái: " + str(response.status) + ")"
                            await send_status_message(custom_message=status_message, alert=True)
                            last_alert_time = current_time
        except aiohttp.ClientError as e:
            logger.error(f"Health check request failed: {e}")
            # Alert about connection error
            current_time = time.time()
            if current_time - last_alert_time > ALERT_INTERVAL_SECONDS:
                status_message = "📊 Trạng thái hệ thống:\n🔄 API: Ngoại tuyến ❌ (Lỗi kết nối)"
                await send_status_message(custom_message=status_message, alert=True)
                last_alert_time = current_time
    except Exception as e:
        logger.error(f"Error in check_websocket_connection: {e}")
        websocket_connection = False 