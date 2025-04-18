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
    # Characters that need to be escaped in Markdown v2
    escape_chars = ['_', '*', '[', ']', '(', ')', '~', '`', '>', '#', '+', '-', '=', '|', '{', '}', '.', '!']
    for char in escape_chars:
        text = text.replace(char, f"\\{char}")
    return text

def get_current_time():
    """Get current time in standard format."""
    now = datetime.now()
    return now.strftime("%Y-%m-%d %H:%M:%S")

async def send_status_message(chat_id=None, custom_message=None, alert=False):
    """Send a message about the backend connection status."""
    # If no chat ID is provided, use the admin group
    if not chat_id and ADMIN_GROUP_CHAT_ID:
        chat_id = ADMIN_GROUP_CHAT_ID
    
    if not chat_id:
        logger.error("No chat ID provided for status message")
        return
    
    # Use custom message if provided, otherwise generate status report
    if custom_message:
        status_message = custom_message
    else:
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
            f"🕒 Time: {get_current_time()}\n"
            f"🔌 API: {api_status}\n"
            f"📊 Databases: {db_status}\n"
            f"🧠 RAG System: {rag_status}\n"
            f"📡 WebSocket: {ws_status}\n\n"
            "The bot is monitoring for user activities."
        )
    
    # For normal status messages, escape markdown if needed
    if not custom_message:
        status_message = escape_markdown(status_message)
    
    # Add alert prefix if this is an alert message
    if alert:
        # When adding alert prefix, make sure not to break Markdown formatting
        # Use non-escaped asterisks for the ALERT text since we want it bold
        status_message = f"⚠️ *ALERT* ⚠️\n\n{status_message}"
    
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
        
        # If sending with Markdown failed, try again without formatting
        try:
            logger.info("Trying to send message without Markdown formatting")
            # Replace backticks, asterisks and other special characters
            plain_text = status_message.replace('*', '').replace('`', '').replace('_', '')
            await bot.send_message(
                chat_id=chat_id,
                text=plain_text,
                parse_mode=None
            )
            logger.info("Message sent without formatting")
        except Exception as fallback_error:
            logger.error(f"Failed to send even without formatting: {fallback_error}")

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
    
    # WebSocket path
    websocket_path = "/notify"
    
    # Create full URL
    if use_wss:
        # For Hugging Face Space and other HTTPS services,
        # no need to specify port if it's 443
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
        global websocket_connection
        try:
            # Check if this is a keepalive response
            if isinstance(message, str) and message.lower() == "keepalive" or "echo" in message:
                logger.debug("Received keepalive response")
                websocket_connection = True
                return
            
            # Parse JSON message
            data = json.loads(message)
            logger.info(f"Received notification: {data}")
            
            # Update connection status
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
                        "username": session_data.get('username', ''),
                        "created_at": session_data.get('created_at', ''),
                        "question": user_question,
                        "response": user_response,
                        "session_id": session_data.get('session_id', '')
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
                    
                    if notification["type"] == "question":
                        # Format full name
                        user_full_name = f"{notification['first_name']} {notification['last_name']}".strip()
                        # Format username with @ if available
                        username_display = f" (@{notification['username']})" if notification['username'] else ""
                        
                        # Escape special characters for Markdown
                        escaped_question = escape_markdown(notification['question'])
                        escaped_response = escape_markdown(notification['response'])
                        escaped_session_id = escape_markdown(notification['session_id'])
                        
                        message_text = (
                            f"🚨 *New announcement!*\n"
                            f"👤 User: {escape_markdown(user_full_name)}{escape_markdown(username_display)}\n"
                            f"💬 Question: {escaped_question}\n"
                            f"🤖 System response: {escaped_response}\n"
                            f"🕒 Time: {notification['created_at']}\n"
                            f"🆔 Session ID: `{escaped_session_id}`"
                        )
                    elif notification["type"] == "error":
                        message_text = f"❌ {escape_markdown(notification['message'])}\nTrying to reconnect in 5 seconds..."
                    elif notification["type"] == "success":
                        message_text = f"✅ {escape_markdown(notification['message'])}"
                    
                    if message_text:
                        try:
                            await bot.send_message(
                                chat_id=ADMIN_GROUP_CHAT_ID,
                                text=message_text,
                                parse_mode="Markdown"
                            )
                            logger.info(f"Notification sent to admin group: {notification['type']}")
                        except Exception as e:
                            logger.error(f"Error sending notification: {e}")
                            
                            # If sending with Markdown failed, try again without formatting
                            try:
                                logger.info("Trying to send notification without Markdown formatting")
                                # Replace backticks, asterisks and other special characters
                                plain_text = message_text.replace('*', '').replace('`', '').replace('_', '')
                                await bot.send_message(
                                    chat_id=ADMIN_GROUP_CHAT_ID,
                                    text=plain_text,
                                    parse_mode=None
                                )
                                logger.info("Notification sent without formatting")
                            except Exception as fallback_error:
                                logger.error(f"Failed to send notification even without formatting: {fallback_error}")
                
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
        http_endpoint = API_DATABASE_URL.replace('ws://', 'http://').replace('wss://', 'https://')
        
        if not http_endpoint.endswith('/'):
            health_endpoint = f"{http_endpoint}/health"
        else:
            health_endpoint = f"{http_endpoint}health"
        
        logger.debug(f"Checking health at: {health_endpoint}")
        
        # First check the API health
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(health_endpoint, timeout=10) as response:
                    if response.status == 200:
                        health_data = await response.json()
                        logger.debug(f"Health data: {health_data}")
                        
                        # Check MongoDB and RAG status
                        mongo_status = health_data.get('mongodb', False)
                        rag_status = health_data.get('rag_system', False)
                        
                        # Create plain text status message (no Markdown formatting)
                        status_message = "📊 Backend Status:\n"
                        status_message += "🔄 API: Online ✅\n"
                        status_message += f"🗄️ MongoDB: {'Online ✅' if mongo_status else 'Offline ❌'}\n"
                        status_message += f"🧠 RAG System: {'Online ✅' if rag_status else 'Offline ❌'}\n"
                        status_message += f"🔌 WebSocket: {'Connected ✅' if websocket_connection else 'Disconnected ❌'}"
                        
                        if not (mongo_status and rag_status and websocket_connection):
                            logger.warning(f"Some services are down: MongoDB={mongo_status}, RAG={rag_status}, WebSocket={websocket_connection}")
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
                            status_message = "📊 Backend Status:\n🔄 API: Offline ❌ (Status code: " + str(response.status) + ")"
                            await send_status_message(custom_message=status_message, alert=True)
                            last_alert_time = current_time
        except aiohttp.ClientError as e:
            logger.error(f"Health check request failed: {e}")
            # Alert about connection error - avoid using the error message directly as it might contain special chars
            current_time = time.time()
            if current_time - last_alert_time > ALERT_INTERVAL_SECONDS:
                status_message = "📊 Backend Status:\n🔄 API: Offline ❌ (Connection error)"
                await send_status_message(custom_message=status_message, alert=True)
                last_alert_time = current_time
    except Exception as e:
        logger.error(f"Error in check_websocket_connection: {e}")
        websocket_connection = False 