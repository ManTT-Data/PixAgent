import os
import logging
import asyncio

from fastapi import FastAPI, Request, BackgroundTasks
from fastapi.responses import JSONResponse, HTMLResponse
import telegram
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters

from main import (
    start_command,
    help_command,
    events_command,
    faq_command,
    emergency_command,
    handle_button,
    handle_message,
    TELEGRAM_BOT_TOKEN,
    API_DATABASE_URL,
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
bot_app.add_handler(CallbackQueryHandler(handle_button))
bot_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

@app.on_event("startup")
async def startup():
    logger.info("🚀 Starting bot app...")

    # Try initializing Telegram bot (getMe, etc.)
    for attempt in range(3):
        try:
            await bot_app.initialize()
            logger.info("✅ Bot initialized properly")
            break
        except Exception as e:
            logger.error(f"❌ Attempt {attempt+1} to initialize bot failed: {e}")
            if attempt < 2:
                logger.info("⏳ Retrying in 3 seconds...")
                await asyncio.sleep(3)
            else:
                logger.warning("⚠️ Giving up. Marking bot as initialized temporarily.")
                bot_app._initialized = True  # Force as initialized to avoid username crash

    # Log our Database API URL
    if API_DATABASE_URL:
        logger.info(f"🔗 Database API URL: {API_DATABASE_URL}")

    # --- TỰ ĐỘNG SET TELEGRAM WEBHOOK ---
    webhook_url = os.getenv("WEBHOOK_URL")
    if webhook_url:
        try:
            await bot_app.bot.set_webhook(webhook_url)
            logger.info(f"✅ Webhook set to {webhook_url}")
        except Exception as e:
            logger.error(f"❌ Failed to set webhook: {e}")

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

@app.get("/health")
async def health():
    return {
        "status": "healthy",
        "webhook_url_configured": bool(os.getenv("WEBHOOK_URL")),
        "database_configured": bool(API_DATABASE_URL),
        "initialized": bot_app._initialized,
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app:app", host="0.0.0.0", port=int(os.getenv("PORT", 7860)))
