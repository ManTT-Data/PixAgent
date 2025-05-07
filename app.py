import os
import logging
import asyncio

from fastapi import FastAPI, Request, BackgroundTasks, Response
from fastapi.responses import JSONResponse, HTMLResponse
import telegram
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters

from main import (
    start_command,
    help_command,
    events_command,
    faq_command,
    emergency_command,
    handle_callback,
    handle_message,
    TELEGRAM_BOT_TOKEN,
    API_DATABASE_URL,
    verify_api_endpoints,
    get_session_endpoint,
    get_rag_endpoint,
    set_commands,
)

# Logging setup
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger("app")

# FastAPI app & Telegram bot application
app = FastAPI(title="Solana SuperTeam User Bot")
bot_app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

# Register handlers
bot_app.add_handler(CommandHandler("start", start_command, block=False))
bot_app.add_handler(CommandHandler("events", events_command, block=False))
bot_app.add_handler(CommandHandler("faq", faq_command, block=False))
bot_app.add_handler(CommandHandler("emergency", emergency_command, block=False))
bot_app.add_handler(CommandHandler("help", help_command, block=False))
bot_app.add_handler(CallbackQueryHandler(handle_callback))
bot_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

# Initialize bot app and set commands
async def init_bot():
    await bot_app.initialize()
    await set_commands(bot_app)
    
@app.on_event("startup")
async def on_startup():
    await init_bot()
    await bot_app.start()
    logger.info("Bot started through FastAPI")

    WEBHOOK_URL = os.getenv("WEBHOOK_URL")
    if WEBHOOK_URL:
        await bot_app.bot.set_webhook(WEBHOOK_URL)
        logger.info(f"Webhook set to: {WEBHOOK_URL}")
    
    # Verify API endpoints
    try:
        endpoints = await verify_api_endpoints()
        get_session_endpoint.verified_endpoints = endpoints
        get_rag_endpoint.verified_endpoints = endpoints
        logger.info(f"API endpoints verified: {endpoints}")
    except Exception as e:
        logger.error(f"Error verifying API endpoints: {e}")


@app.on_event("shutdown")
async def shutdown():
    await bot_app.shutdown()
    logger.info("🛑 Bot shut down cleanly.")


@app.post("/telegram-webhook")
async def telegram_webhook(request: Request, background_tasks: BackgroundTasks):
    data = await request.json()
    logger.info(f"📥 Received update: {data}")

    try:
        update = telegram.Update.de_json(data, bot_app.bot)
        background_tasks.add_task(bot_app.process_update, update)
    except Exception as e:
        logger.error(f"❌ Error processing update: {e}")
        return JSONResponse({"status": "error", "detail": str(e)}, status_code=500)

    return JSONResponse({"status": "ok"})


@app.get("/", response_class=HTMLResponse)
async def root():
    return """
    <html><body>
        <h1>Solana SuperTeam User Bot</h1>
        <p>🟢 Bot is running</p>
    </body></html>
    """


@app.head("/", include_in_schema=False)
async def root_head():
    """
    Returns 200 OK for HEAD /, helps ping tools like UptimeRobot to avoid 405 errors.
    """
    return Response(status_code=200)


@app.get("/health")
async def health():
    return {
        "status": "healthy",
        "webhook_url_configured": bool(os.getenv("WEBHOOK_URL")),
        "database_configured": bool(API_DATABASE_URL),
        "initialized": bot_app._initialized,
        "api_endpoints": {
            "session": "/mongodb/session",
            "rag": "/rag/chat"
        }
    }


if __name__ == "__main__":
    import uvicorn
    # Use uvicorn to run the FastAPI app instead of running the bot directly
    uvicorn.run("app:app", host="0.0.0.0", port=int(os.getenv("PORT", 7860)))
