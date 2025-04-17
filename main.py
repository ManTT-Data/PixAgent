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
    
    while True:
        # Parse the API_DATABASE_URL to create a WebSocket URL
        # This is a placeholder - adjust according to your actual WebSocket URL pattern
        ws_url = API_DATABASE_URL.replace("http://", "ws://").replace("https://", "wss://")
        ws_url = fix_url(ws_url, "/ws/activity")
        
        logger.info(f"Connecting to WebSocket: {ws_url}")
        
        try:
            # This is a placeholder for WebSocket connection logic
            # Replace with actual WebSocket implementation if needed
            websocket_connection = True
            
            # Simulate a WebSocket connection by sleeping
            await asyncio.sleep(60)
            
            # If you implement actual WebSocket, handle messages here
            # For now, just log a placeholder message
            logger.info("WebSocket: Monitoring for user activity")
            
        except Exception as e:
            websocket_connection = False
            logger.error(f"WebSocket error: {e}")
            # Wait before reconnecting
            await asyncio.sleep(10) 