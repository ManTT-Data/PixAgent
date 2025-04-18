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
    
    # Đảm bảo có websocket-client module
    try:
        import websocket
    except ImportError:
        logger.error("websocket-client module not installed. Please install it with 'pip install websocket-client'")
        return
    
    # Xác định URL WebSocket từ API_DATABASE_URL
    parsed_url = urllib.parse.urlparse(API_DATABASE_URL)
    
    # Xác định protocol
    use_wss = parsed_url.scheme == "https"
    
    # Lấy hostname và port
    websocket_server = parsed_url.netloc.split(':')[0]
    websocket_port = parsed_url.port if parsed_url.port else (443 if use_wss else 80)
    
    # Đường dẫn của WebSocket
    websocket_path = "/notify"
    
    # Tạo URL đầy đủ
    if use_wss:
        ws_url = f"wss://{websocket_server}{websocket_path}"
    else:
        ws_url = f"ws://{websocket_server}:{websocket_port}{websocket_path}"
    
    logger.info(f"WebSocket URL: {ws_url}")
    
    # Định nghĩa các event handlers
    def on_message(ws, message):
        try:
            # Parse JSON message
            data = json.loads(message)
            logger.info(f"Received notification: {data}")
            
            # Xử lý thông báo theo loại
            if data.get("type") == "new_session":
                session_data = data.get("data", {})
                user_question = session_data.get("message", "")
                user_response = session_data.get("response", "")
                user_name = session_data.get("first_name", "Unknown User")
                
                # Log thông tin câu hỏi
                logger.info(f"User {user_name} asked: {user_question}")
                logger.info(f"System response: {user_response}")
                
                # Gửi thông báo đến nhóm admin
                if ADMIN_GROUP_CHAT_ID:
                    asyncio.run_coroutine_threadsafe(
                        send_admin_notification(
                            session_data=session_data,
                            user_question=user_question, 
                            user_response=user_response
                        ), 
                        asyncio.get_event_loop()
                    )
        except json.JSONDecodeError:
            # Xử lý tin nhắn không phải JSON (ví dụ: keepalive responses)
            logger.debug(f"Received non-JSON message: {message}")
        except Exception as e:
            logger.error(f"Error processing message: {e}")
    
    def on_error(ws, error):
        logger.error(f"WebSocket error: {error}")
        websocket_connection = False
        
        # Thông báo lỗi đến admin group
        if ADMIN_GROUP_CHAT_ID:
            asyncio.run_coroutine_threadsafe(
                send_error_notification(f"WebSocket error: {error}"),
                asyncio.get_event_loop()
            )
    
    def on_close(ws, close_status_code, close_msg):
        logger.warning(f"WebSocket connection closed: code={close_status_code}, message={close_msg}")
        websocket_connection = False
    
    def on_open(ws):
        logger.info(f"WebSocket connection opened to {ws_url}")
        websocket_connection = True
        
        # Thông báo kết nối thành công đến admin group
        if ADMIN_GROUP_CHAT_ID:
            asyncio.run_coroutine_threadsafe(
                send_success_notification("WebSocket connected successfully! Now monitoring user questions."),
                asyncio.get_event_loop()
            )
        
        # Khởi động thread gửi keepalive
        def send_keepalive_thread():
            while True:
                try:
                    if ws.sock and ws.sock.connected:
                        ws.send("keepalive")
                        logger.info("Sent keepalive message")
                    time.sleep(300)  # 5 phút theo tài liệu API
                except Exception as e:
                    logger.error(f"Error sending keepalive: {e}")
                    time.sleep(60)  # Thử lại sau 1 phút nếu có lỗi
                    
        keepalive_thread = threading.Thread(target=send_keepalive_thread, daemon=True)
        keepalive_thread.start()
    
    # Định nghĩa hàm hỗ trợ gửi thông báo
    async def send_admin_notification(session_data, user_question, user_response):
        try:
            bot = Bot(token=ADMIN_TELEGRAM_BOT_TOKEN)
            notification = (
                f"❓ *Câu hỏi từ {session_data.get('first_name', '')}*:\n{user_question}\n\n"
                f"🤖 *Phản hồi của hệ thống*:\n{user_response}\n\n"
                f"🆔 Session ID: `{session_data.get('session_id', '')}`"
            )
            await bot.send_message(
                chat_id=ADMIN_GROUP_CHAT_ID,
                text=notification,
                parse_mode="Markdown"
            )
            logger.info(f"Notification sent to admin group for session {session_data.get('session_id', '')}")
        except Exception as e:
            logger.error(f"Failed to send notification: {e}")
    
    async def send_error_notification(error_message):
        try:
            bot = Bot(token=ADMIN_TELEGRAM_BOT_TOKEN)
            await bot.send_message(
                chat_id=ADMIN_GROUP_CHAT_ID,
                text=f"❌ {error_message}\nĐang thử kết nối lại sau 5 giây...",
                parse_mode="Markdown"
            )
        except Exception as e:
            logger.error(f"Failed to send error notification: {e}")
    
    async def send_success_notification(message):
        try:
            bot = Bot(token=ADMIN_TELEGRAM_BOT_TOKEN)
            await bot.send_message(
                chat_id=ADMIN_GROUP_CHAT_ID,
                text=f"✅ {message}",
                parse_mode="Markdown"
            )
        except Exception as e:
            logger.error(f"Failed to send success notification: {e}")
    
    # Khởi tạo và chạy WebSocket client trong một vòng lặp để tự động kết nối lại
    def run_websocket_client():
        while True:
            try:
                # Tạo WebSocket app với các handlers
                ws = websocket.WebSocketApp(
                    ws_url,
                    on_open=on_open,
                    on_message=on_message,
                    on_error=on_error,
                    on_close=on_close
                )
                
                # Chạy với ping/pong để theo dõi kết nối
                ws.run_forever(ping_interval=60, ping_timeout=30)
                
                # Nếu tới đây, kết nối đã đóng
                logger.warning("WebSocket connection lost, reconnecting in 5 seconds...")
                time.sleep(5)
            except Exception as e:
                logger.error(f"WebSocket client error: {e}")
                logger.info("Reconnecting in 5 seconds...")
                time.sleep(5)
    
    # Chạy WebSocket client trong một thread riêng
    websocket_thread = threading.Thread(target=run_websocket_client, daemon=True)
    websocket_thread.start()
    
    # Giữ coroutine chạy
    while True:
        await asyncio.sleep(60)  # Kiểm tra mỗi phút
        if not websocket_thread.is_alive():
            logger.warning("WebSocket thread died, restarting...")
            websocket_thread = threading.Thread(target=run_websocket_client, daemon=True)
            websocket_thread.start() 