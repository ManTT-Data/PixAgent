import os
import logging
import asyncio
from fastapi import FastAPI, Request, BackgroundTasks, Response
from fastapi.responses import HTMLResponse, JSONResponse
import telegram
from telegram.ext import Application, CommandHandler
import nest_asyncio
import requests

# Apply nest_asyncio to allow nested event loops
nest_asyncio.apply()

# Import functions from main.py
from main import (
    start_command,
    help_command,
    status_command,
    websocket_listener,
    ADMIN_TELEGRAM_BOT_TOKEN,
    ADMIN_GROUP_CHAT_ID,
    API_DATABASE_URL
)

# Logging setup
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger("app")

# Create FastAPI app and Telegram Application
app = FastAPI(title="Solana SuperTeam Admin Bot")
bot_app = Application.builder().token(ADMIN_TELEGRAM_BOT_TOKEN).build()

# Register handlers for commands
bot_app.add_handler(CommandHandler("start", start_command))
bot_app.add_handler(CommandHandler("help", help_command))
bot_app.add_handler(CommandHandler("status", status_command))

# WebSocket task variables
websocket_task = None
websocket_connection_error = None

@app.on_event("startup")
async def startup():
    global websocket_task, websocket_connection_error

    logger.info(f"🔑 Admin Bot starting (token prefix {ADMIN_TELEGRAM_BOT_TOKEN[:5]}…)")  
    if API_DATABASE_URL:
        logger.info(f"🔗 Database API URL: {API_DATABASE_URL}")
        
        # Kiểm tra ngay kết nối tới backend
        try:
            backend_url = API_DATABASE_URL
            if backend_url.startswith("ws://"):
                backend_url = backend_url.replace("ws://", "http://")
            elif backend_url.startswith("wss://"):
                backend_url = backend_url.replace("wss://", "https://")

            # Loại bỏ dấu / ở cuối URL nếu có
            if backend_url.endswith('/'):
                backend_url = backend_url[:-1]
                
            # Kiểm tra health endpoint
            if not backend_url.endswith('/health'):
                health_url = f"{backend_url}/health"
            else:
                health_url = backend_url
                
            logger.info(f"Checking backend connection: {health_url}")
            response = requests.get(health_url, timeout=10)
            
            if response.status_code == 200:
                logger.info("✅ Backend connection successful!")
                
                # Không kiểm tra admin ws status vì endpoint không tồn tại
                logger.info("WebSocket sẽ được kết nối tự động đến /notify endpoint")
            else:
                logger.warning(f"⚠️ Backend health check failed with status {response.status_code}")
        except Exception as e:
            logger.warning(f"⚠️ Backend connection check failed: {e}")
    
    logger.info(f"👥 Admin Group Chat ID: {ADMIN_GROUP_CHAT_ID}")

    # Initialize Telegram bot
    try:
        await bot_app.initialize()
        await bot_app.start()
        logger.info("✅ Bot application initialized and started")
    except Exception as e:
        logger.error(f"❌ Failed to initialize bot application: {e}")

    # Automatically set webhook if WEBHOOK_URL environment variable exists
    webhook_url = os.getenv("WEBHOOK_URL")
    if webhook_url:
        try:
            await bot_app.bot.set_webhook(webhook_url)
            logger.info(f"✅ Webhook set to {webhook_url}")
        except Exception as e:
            logger.error(f"❌ Failed to set webhook: {e}")

    # Start WebSocket listener
    try:
        websocket_task = asyncio.create_task(websocket_listener())
        logger.info("📡 WebSocket listener started")
    except Exception as e:
        websocket_connection_error = str(e)
        logger.error(f"❌ Failed to start WebSocket listener: {e}")

@app.on_event("shutdown")
async def shutdown():
    global websocket_task

    # Stop WebSocket task if running
    if websocket_task:
        websocket_task.cancel()
        try:
            await websocket_task
        except asyncio.CancelledError:
            logger.info("🛑 WebSocket listener cancelled")

    # Shutdown bot cleanly
    try:
        await bot_app.stop()
        await bot_app.shutdown()
        logger.info("🛑 Bot application stopped")
    except Exception as e:
        logger.error(f"❌ Error stopping bot application: {e}")

@app.post("/telegram-webhook")
async def telegram_webhook(request: Request, background_tasks: BackgroundTasks):
    """Process updates from Telegram via webhook."""
    try:
        update_data = await request.json()
        logger.info(f"📥 Received update: {update_data}")
        background_tasks.add_task(process_update, update_data)
        return JSONResponse(content={"status": "ok"})
    except Exception as e:
        logger.error(f"❌ Error processing webhook: {e}")
        return JSONResponse(content={"status": "error", "message": str(e)}, status_code=500)

async def process_update(update_data):
    """Run bot_app.process_update in background."""
    try:
        update = telegram.Update.de_json(update_data, bot_app.bot)
        await bot_app.process_update(update)
    except Exception as e:
        logger.error(f"❌ Error in process_update: {e}")

@app.get("/", response_class=HTMLResponse)
async def root():
    """Basic status page."""
    webhook_configured = bool(os.getenv("WEBHOOK_URL"))
    websocket_running = websocket_task is not None and not websocket_task.done()

    return f"""
    <html><body>
      <h1>Solana SuperTeam Admin Bot</h1>
      <p>🔹 Status: Running</p>
      <p>🔹 Webhook URL Configured: {'✅' if webhook_configured else '❌'}</p>
      <p>🔹 WebSocket Status: {'✅ Running' if websocket_running else '❌ Stopped'}</p>
      <p>🔹 Admin Group Chat ID: {'✅' if ADMIN_GROUP_CHAT_ID else '❌'}</p>
      {f"<p style='color:red;'>WebSocket error: {websocket_connection_error}</p>" if websocket_connection_error else ""}
    </body></html>
    """

@app.head("/", include_in_schema=False)
async def root_head():
    """HEAD / returns 200 OK for ping tools."""
    return Response(status_code=200)

@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "bot": "admin_bot",
        "webhook_configured": bool(os.getenv("WEBHOOK_URL")),
        "websocket_running": websocket_task is not None and not websocket_task.done(),
        "websocket_error": websocket_connection_error,
        "admin_group_configured": bool(ADMIN_GROUP_CHAT_ID),
        "database_configured": bool(API_DATABASE_URL)
    }

@app.get("/status")
async def status():
    """Detailed bot status."""
    return {
        "bot": "admin_bot",
        "status": "running",
        "webhook_configured": bool(os.getenv("WEBHOOK_URL")),
        "websocket_status": "running" if websocket_task and not websocket_task.done() else "stopped",
        "websocket_error": websocket_connection_error,
        "admin_group_configured": bool(ADMIN_GROUP_CHAT_ID)
    }

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 10000))  # Changed default to 10000 to match logs
    uvicorn.run("app:app", host="0.0.0.0", port=port)
