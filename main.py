"""
Solana SuperTeam User Bot
This bot provides information about Solana SuperTeam and events.
"""

import os
import logging
import requests
import json
from datetime import datetime
from dotenv import load_dotenv
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes
from urllib.parse import urlparse, urljoin
import asyncio

# Configure logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()

# Get configuration from environment variables
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
API_RAG_URL = os.getenv("API_RAG_URL")
API_DATABASE_URL = os.getenv("API_DATABASE_URL")

# Helper function to fix URL paths
def fix_url(base_url, path):
    """Create a properly formatted URL without double slashes."""
    if not base_url:
        return path
        
    # Parse the URL to handle special cases
    parsed = urlparse(base_url)
    
    # If URL is a Hugging Face space, adjust the path
    if "huggingface.co" in parsed.netloc and "spaces" in parsed.path:
        # For HF spaces, API endpoints should be directly at the root, not under /spaces/...
        # Convert https://huggingface.co/spaces/Cuong2004/Pix-Agent/ to https://cuong2004-pix-agent.hf.space/
        parts = parsed.path.strip('/').split('/')
        if len(parts) >= 3 and parts[0] == 'spaces':
            username = parts[1]
            repo_name = parts[2]
            base_url = f"https://{username.lower()}-{repo_name.lower()}.hf.space"
            
    # Use urljoin for clean URL concatenation
    return urljoin(base_url.rstrip('/') + '/', path.lstrip('/'))

# Helper functions
def get_current_time():
    """Get current time in standard format."""
    now = datetime.now()
    return now.strftime("%Y-%m-%d %H:%M:%S")

def generate_session_id(user_id, timestamp=None):
    """Generate a consistent session ID format."""
    if timestamp is None:
        timestamp = get_current_time()
    return f"{user_id}_{timestamp.replace(' ', '_')}"

async def log_complete_session(update: Update, action: str, message: str, response_text: str):
    """Log a complete session with both user message and bot response in one call."""
    try:
        user = update.effective_user
        timestamp = get_current_time()
        session_id = generate_session_id(user.id, timestamp)
        
        # Create complete session data including both message and response
        session_data = {
            "session_id": session_id,
            "factor": "user",
            "action": action,
            "created_at": timestamp,
            "first_name": user.first_name or "",
            "last_name": user.last_name or "",
            "message": message,
            "user_id": str(user.id),
            "username": user.username or "",
            "response": response_text
        }
        
        if API_DATABASE_URL:
            # Send complete session data to API
            endpoint_url = fix_url(API_DATABASE_URL, "/mongodb/session")
            logger.info(f"Logging complete session to: {endpoint_url}")
            
            try:
                response = requests.post(endpoint_url, json=session_data)
                if response.status_code not in [200, 201]:  # Accept both 200 OK and 201 Created
                    logger.warning(f"Failed to log complete session: {response.status_code} - {response.text}")
                    return session_id
                
                logger.info(f"Successfully logged complete session: {session_id}")
                return session_id
            except Exception as e:
                logger.error(f"Error posting to {endpoint_url}: {e}")
                return session_id
        else:
            logger.warning("Database URL not configured, session not logged")
        return session_id
    except Exception as e:
        logger.error(f"Error logging complete session: {e}")
        return generate_session_id(user.id) if user else None

# Simplified function to create session ID without logging
async def log_session(update: Update, action: str, message: str = ""):
    """Create a temporary session ID without actually logging to the database."""
    try:
        user = update.effective_user
        timestamp = get_current_time()
        session_id = generate_session_id(user.id, timestamp)
        return session_id
    except Exception as e:
        logger.error(f"Error creating temporary session ID: {e}")
        return None

# Command handlers
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Send a message when the command /start is issued."""
    # Create temporary session ID to store in context
    temp_session_id = await log_session(update, "start")
    context.user_data["last_session_id"] = temp_session_id
    
    # Create main menu keyboard
    keyboard = [
        [KeyboardButton("Da Nang's bucket list"), KeyboardButton("Solana Summit Event")],
        [KeyboardButton("Events"), KeyboardButton("About Pixity")],
        [KeyboardButton("Emergency"), KeyboardButton("FAQ")]
    ]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    
    # Display available commands
    commands_text = (
        "Available commands:\n"
        "/start - Start the bot and display the main menu\n"
        "/events - Show upcoming events\n"
        "/faq - Show frequently asked questions\n"
        "/emergency - List of emergency\n"
        "/help - Display this help"
    )
    
    welcome_text = (
        "Hello! This is PiXity, your local buddy. I can help you with every information about Da Nang, ask me!\n\n"
        "This is the beta version of PiXity, so a few hiccups are inevitable, if there is any feedback, contact us @PiXity_assistant.\n\n"
        "And don't worry—your data will never be stolen. Feel free to explore and enjoy using PiXity!\n\n"
        f"{commands_text}"
    )
    
    # Send message to user
    await update.message.reply_text(welcome_text, reply_markup=reply_markup)
    
    # Log complete session including both command and response
    await log_complete_session(update, "start", "/start", welcome_text)

async def events_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show upcoming events."""
    session_id = await log_session(update, "events")
    context.user_data["last_session_id"] = session_id
    await get_events(update, context, "events", "")

async def faq_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show frequently asked questions."""
    session_id = await log_session(update, "faq")
    context.user_data["last_session_id"] = session_id
    await get_faq(update, context, "faq", "")

async def emergency_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show emergency information."""
    session_id = await log_session(update, "emergency")
    context.user_data["last_session_id"] = session_id
    await get_emergency(update, context, "emergency", "")

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Send a message when the command /help is issued."""
    # Create temporary session ID
    temp_session_id = await log_session(update, "help")
    context.user_data["last_session_id"] = temp_session_id
    
    help_text = (
        "Available commands:\n"
        "/start - Start the bot and display the main menu\n"
        "/events - Show upcoming events\n"
        "/faq - Show frequently asked questions\n"
        "/emergency - List of emergency\n"
        "/help - Display this help\n\n"
        "Bot Features:\n"
        "• Ask questions about Da Nang\n"
        "• Get information about events\n"
        "• Browse through FAQs\n"
        "• Access emergency information"
    )
    
    # Create main menu keyboard
    keyboard = [
        [KeyboardButton("Da Nang's bucket list"), KeyboardButton("Solana Summit Event")],
        [KeyboardButton("Events"), KeyboardButton("About Pixity")],
        [KeyboardButton("Emergency"), KeyboardButton("FAQ")]
    ]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    
    await update.message.reply_text(help_text, reply_markup=reply_markup)
    
    # Log complete session including both command and response
    await log_complete_session(update, "help", "/help", help_text)

# Button handlers
async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle button callbacks."""
    query = update.callback_query
    data = query.data
        
    if data.startswith("emergency_") or data.startswith("faq_") or data.startswith("events_"):
        # Log that we received a callback but we're not processing it anymore since we show all info directly
        logger.info(f"Received callback {data}, but now showing all information directly")
        await query.answer("This feature has been updated. Please use the main menu buttons.")
        
        # Show the keyboard again
        keyboard = [
            [KeyboardButton("Da Nang's bucket list"), KeyboardButton("Solana Summit Event")],
            [KeyboardButton("Events"), KeyboardButton("About Pixity")],
            [KeyboardButton("Emergency"), KeyboardButton("FAQ")]
        ]
        reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
        await query.message.reply_text("Please use the main menu buttons:", reply_markup=reply_markup)
        
        # Log complete session
        await log_complete_session(update, "callback_handled", f"Callback data: {data}", "Callback received but not processed due to update")
    else:
        # Handle other callbacks or undefined callbacks
        await query.answer("Unknown callback query")
        logger.warning(f"Unhandled callback query received: {data}")
        await log_complete_session(update, "callback_handled", f"Unknown callback data: {data}", "Callback not recognized")

# Message handler
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle user messages."""
    text = update.message.text
    
    # Create temporary session ID - not actually saved to database
    temp_session_id = await log_session(update, "message", text)
    context.user_data["last_session_id"] = temp_session_id
    
    # Handle menu button presses
    if text == "Da Nang's bucket list":
        await get_danang_bucket_list(update, context)
    elif text == "Solana Summit Event":
        await get_solana_summit(update, context)
    elif text == "Events":
        await get_events(update, context, "events", text)
    elif text == "Emergency":
        await get_emergency(update, context, "emergency", text)
    elif text == "FAQ":
        await get_faq(update, context, "faq", text)
    elif text == "About Pixity":
        await get_about_pixity(update, context, "about_pixity", text)
    else:
        # Send message to RAG API and get response
        await get_rag_response(update, context, "asking_freely", text)

# API interaction functions
async def get_events(update: Update, context: ContextTypes.DEFAULT_TYPE, action: str, message: str):
    """Get events from API and display them in one message."""
    try:
        if not API_DATABASE_URL:
            logger.error("Database API not configured. Cannot fetch events.")
            return

        endpoint_url = fix_url(API_DATABASE_URL, "/postgres/events")
        params = {
            "active_only": True,
            "featured_only": False,
            "limit": 3,
            "skip": 0,
            "use_cache": True
        }
        logger.info(f"Fetching events from: {endpoint_url}")

        response = requests.get(endpoint_url, params=params)
        if response.status_code != 200:
            logger.error(f"Failed to fetch events: {response.status_code} - {response.text}")
            return

        events = response.json() or []
        if not events:
            response_text = "No upcoming events at the moment."
        else:
            lines = ["*Upcoming Events*\n"]
            for ev in events:
                block = [f"🎉 *{ev.get('name', 'Event')}*"]
                if ev.get("description"):
                    block.append(f"{ev['description']}")
                if ev.get("address"):
                    block.append(f"📍 Location: {ev['address']}")
                if ev.get("date_start"):
                    start = ev["date_start"].replace("T", " ").split(".")[0]
                    block.append(f"Start: {start}")
                if ev.get("date_end"):
                    end = ev["date_end"].replace("T", " ").split(".")[0]
                    block.append(f"End: {end}")
                price_info = "💰 Price: Free"
                if ev.get("price"):
                    p = ev["price"][0]
                    if p.get("amount", 0) > 0:
                        price_info = f"💰 Price: {p['amount']} {p.get('currency', '')}"
                block.append(price_info)
                lines.append("\n".join(block))
            response_text = "\n\n".join(lines)

        keyboard = [
            [KeyboardButton("Da Nang's bucket list"), KeyboardButton("Solana Summit Event")],
            [KeyboardButton("Events"), KeyboardButton("About Pixity")],
            [KeyboardButton("Emergency"), KeyboardButton("FAQ")]
        ]
        reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

        await update.effective_message.reply_text(
            response_text,
            parse_mode="Markdown",
            reply_markup=reply_markup
        )
        await log_complete_session(update, action, message, response_text)

    except Exception as e:
        logger.error(f"Error fetching events: {e}")


async def get_emergency(update: Update, context: ContextTypes.DEFAULT_TYPE, action: str, message: str):
    """First show a list of emergency categories, then show details for the chosen category."""
    try:
        if not API_DATABASE_URL:
            logger.error("Database API not configured. Cannot fetch emergency information.")
            return

        # If we haven't fetched sections yet, do phase 1
        if "emergency_sections" not in context.user_data:
            # 1) fetch list of categories
            sections_url = fix_url(API_DATABASE_URL, "/postgres/emergency/sections")
            logger.info(f"Fetching emergency sections from: {sections_url}")
            resp = requests.get(sections_url)
            if resp.status_code != 200:
                logger.error(f"Failed to fetch emergency sections: {resp.status_code} - {resp.text}")
                return

            sections = resp.json() or []
            if not sections:
                response_text = "No emergency categories available."
                await update.effective_message.reply_text(response_text)
                await log_complete_session(update, action, message, response_text)
                return

            # build markdown list of names
            lines = ["*Please select an emergency category:*"]
            for sec in sections:
                lines.append(f"- {sec['name']}")
            response_text = "\n".join(lines)

            # save name→id mapping for phase 2
            context.user_data["emergency_sections"] = {sec["name"]: sec["id"] for sec in sections}

            # reply with a keyboard of category names
            keyboard = [[KeyboardButton(sec["name"])] for sec in sections]
            reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
            await update.effective_message.reply_text(
                response_text, parse_mode="Markdown", reply_markup=reply_markup
            )
            await log_complete_session(update, action, message, response_text)
            return

        # phase 2: user has tapped a category name
        mapping = context.user_data.pop("emergency_sections", {})
        section_name = message
        section_id = mapping.get(section_name)
        if not section_id:
            # unknown button: fall back to phase 1
            return await get_emergency(update, context, action, "")

        # fetch details for this section
        detail_url = fix_url(API_DATABASE_URL, f"/postgres/emergency/section/{section_id}")
        logger.info(f"Fetching emergency details from: {detail_url}")
        resp = requests.get(detail_url)
        if resp.status_code != 200:
            logger.error(f"Failed to fetch emergency details: {resp.status_code} - {resp.text}")
            return

        details = resp.json() or []
        if not details:
            response_text = f"No entries found for '{section_name}'."
        else:
            # build markdown list of contacts
            lines = [f"*{section_name}*"]
            for c in details:
                name = c.get("name", "Unknown")
                phone = c.get("phone_number", "No phone")
                lines.append(f"- *{name}*: {phone}")
                if desc := c.get("description"):
                    lines.append(f"  {desc}")
                if addr := c.get("address"):
                    lines.append(f"  {addr}")
                lines.append("")  # blank line between entries
            response_text = "\n".join(lines).rstrip()

        # send back to main menu
        keyboard = [
            [KeyboardButton("Da Nang's bucket list"), KeyboardButton("Solana Summit Event")],
            [KeyboardButton("Events"), KeyboardButton("About Pixity")],
            [KeyboardButton("Emergency"), KeyboardButton("FAQ")]
        ]
        reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
        await update.effective_message.reply_text(
            response_text, parse_mode="Markdown", reply_markup=reply_markup
        )
        # log with message = category name
        await log_complete_session(update, action, section_name, response_text)

    except Exception as e:
        logger.error(f"Error fetching emergency info: {e}")


async def get_faq(update: Update, context: ContextTypes.DEFAULT_TYPE, action: str, message: str):
    """Get FAQ information from API and display it."""
    try:
        if not API_DATABASE_URL:
            logger.error("Database API not configured. Cannot fetch FAQ information.")
            return

        endpoint_url = fix_url(API_DATABASE_URL, "/postgres/faq")
        params = {"active_only": True, "limit": 10, "use_cache": True}
        logger.info(f"Fetching FAQ from: {endpoint_url}")

        response = requests.get(endpoint_url, params=params)
        if response.status_code != 200:
            logger.error(f"Failed to fetch FAQ info: {response.status_code} - {response.text}")
            return

        faqs = response.json() or []
        if not faqs:
            response_text = "No FAQ information available."
        else:
            lines = ["📋 *Frequently Asked Questions*\n"]
            for i, faq in enumerate(faqs, 1):
                lines.append(f"❓ *{faq.get('question', f'Question {i}')}*")
                lines.append(f"✅ {faq.get('answer','No answer available')}\n")
            response_text = "\n".join(lines)

        keyboard = [
            [KeyboardButton("Da Nang's bucket list"), KeyboardButton("Solana Summit Event")],
            [KeyboardButton("Events"), KeyboardButton("About Pixity")],
            [KeyboardButton("Emergency"), KeyboardButton("FAQ")]
        ]
        reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

        await update.effective_message.reply_text(
            response_text,
            parse_mode="Markdown",
            reply_markup=reply_markup
        )
        await log_complete_session(update, action, message, response_text)

    except Exception as e:
        logger.error(f"Error fetching FAQ information: {e}")

async def get_rag_response(update: Update, context: ContextTypes.DEFAULT_TYPE, action: str, query_text: str):
    """Get response from RAG API, falling back to the database URL if needed."""
    try:
        if not API_RAG_URL and not API_DATABASE_URL:
            logger.error("API not configured. Cannot process your question.")
            return

        # Choose whichever base URL is available
        base_url = API_RAG_URL or API_DATABASE_URL
        rag_url = fix_url(base_url, "/rag/chat")
        logger.info(f"Sending question to RAG at: {rag_url}")

        user = update.effective_user
        payload = {
            "user_id": str(user.id),
            "question": query_text,
            "include_history": True,
            "use_rag": True,
            "similarity_top_k": 3,
            "vector_distance_threshold": 0.75,
            "session_id": context.user_data.get("last_session_id"),
            "first_name": user.first_name or "",
            "last_name": user.last_name or "",
            "username": user.username or ""
        }

        response = requests.post(rag_url, json=payload)
        if response.status_code != 200:
            logger.error(f"Failed to get RAG response: {response.status_code} - {response.text}")
            return

        result = response.json()
        answer = result.get("answer", "I couldn't find an answer to your question.")
        if sources := result.get("sources"):
            answer += "\n\nSources:"
            for i, src in enumerate(sources[:3], 1):
                answer += f"\n{i}. {src.get('source','Unknown')}"

        # Send answer and log
        await update.message.reply_text(answer)
        await log_complete_session(update, action, query_text, answer)

        # Re-show main keyboard
        keyboard = [
            [KeyboardButton("Da Nang's bucket list"), KeyboardButton("Solana Summit Event")],
            [KeyboardButton("Events"), KeyboardButton("About Pixity")],
            [KeyboardButton("Emergency"), KeyboardButton("FAQ")]
        ]

    except Exception as e:
        logger.error(f"Error getting RAG response: {e}")


async def get_about_pixity(update: Update, context: ContextTypes.DEFAULT_TYPE, action: str, message: str):
    """Get About Pixity information from API and display it."""
    try:
        if not API_DATABASE_URL:
            logger.error("Database API not configured. Cannot fetch About Pixity information.")
            return

        endpoint_url = fix_url(API_DATABASE_URL, "/postgres/about-pixity")
        params = {"use_cache": True}
        logger.info(f"Fetching About Pixity info from: {endpoint_url}")

        response = requests.get(endpoint_url, params=params)
        if response.status_code != 200:
            logger.error(f"Failed to fetch About Pixity info: {response.status_code} - {response.text}")
            return

        about_data = response.json() or {}
        raw = about_data.get("content", "") or ""
        try:
            content_obj = json.loads(raw)
            about_text = content_obj.get("content", raw).strip()
        except:
            about_text = raw.strip()

        keyboard = [
            [KeyboardButton("Da Nang's bucket list"), KeyboardButton("Solana Summit Event")],
            [KeyboardButton("Events"), KeyboardButton("About Pixity")],
            [KeyboardButton("Emergency"), KeyboardButton("FAQ")]
        ]
        reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
        await update.effective_message.reply_text(about_text or "Information unavailable.", reply_markup=reply_markup)
        await log_complete_session(update, action, message, about_text)

    except Exception as e:
        logger.error(f"Error fetching About Pixity information: {e}")

from telegram.constants import ParseMode  # add at top

async def get_solana_summit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Get Solana Summit information from API and display it with HTML links."""
    try:
        if not API_DATABASE_URL:
            logger.error("Database API not configured. Cannot fetch Solana Summit information.")
            return

        endpoint_url = fix_url(API_DATABASE_URL, "/postgres/solana-summit")
        params = {"use_cache": True}
        logger.info(f"Fetching Solana Summit info from: {endpoint_url}")

        response = requests.get(endpoint_url, params=params)
        if response.status_code != 200:
            logger.error(f"Failed to fetch Solana Summit info: {response.status_code} - {response.text}")
            return

        summit_data = response.json() or {}
        raw = summit_data.get("content", "") or ""

        # try to unwrap nested JSON
        try:
            parsed = json.loads(raw)
            solana_summit_info = parsed.get("content", raw).strip()
        except Exception:
            solana_summit_info = raw.strip() or "Solana Summit information is unavailable."

        # build your keyboard as before
        keyboard = [
            [KeyboardButton("Da Nang's bucket list"), KeyboardButton("Solana Summit Event")],
            [KeyboardButton("Events"), KeyboardButton("About Pixity")],
            [KeyboardButton("Emergency"), KeyboardButton("FAQ")]
        ]
        reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

        # ***The only change: switch to HTML parse mode***
        await update.effective_message.reply_text(
            solana_summit_info,
            parse_mode=ParseMode.HTML,
            disable_web_page_preview=False,
            reply_markup=reply_markup
        )

        session_id = await log_session(update, "solana_summit")
        context.user_data["last_session_id"] = session_id
        await log_complete_session(update, "solana_summit", "Solana Summit Event", solana_summit_info)

    except Exception as e:
        logger.error(f"Error fetching Solana Summit information: {e}")

async def get_danang_bucket_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Get Da Nang's Bucket List information from API and display it."""
    try:
        if not API_DATABASE_URL:
            logger.error("Database API not configured. Cannot fetch Da Nang's Bucket List information.")
            return

        endpoint_url = fix_url(API_DATABASE_URL, "/postgres/danang-bucket-list")
        params = {"use_cache": True}
        logger.info(f"Fetching Da Nang's Bucket List info from: {endpoint_url}")

        response = requests.get(endpoint_url, params=params)
        if response.status_code != 200:
            logger.error(f"Failed to fetch Da Nang's Bucket List info: {response.status_code} - {response.text}")
            return

        bucket_data = response.json() or {}
        raw = bucket_data.get("content", "") or ""

        try:
            content_json = json.loads(raw)
            title = content_json.get("title", "Da Nang's bucket list").strip()
            description = content_json.get("description", "").strip()
            items = content_json.get("items", [])

            # Build a clean list of lines
            lines = [f"📋 {title}:"]
            if description:
                lines.append(description)

            for item in items:
                emoji = item.get("emoji", "•")
                name = item.get("name", "").strip()
                desc = item.get("description", "").strip()
                line = f"{emoji} {name}" + (f" – {desc}" if desc else "")
                lines.append(line)

            bucket_text = "\n".join(lines)

        except Exception:
            # Fallback nếu JSON malformed
            bucket_text = raw.strip() or "Da Nang's Bucket List information is unavailable."

        # Gửi cùng keyboard
        keyboard = [
            [KeyboardButton("Da Nang's bucket list"), KeyboardButton("Solana Summit Event")],
            [KeyboardButton("Events"), KeyboardButton("About Pixity")],
            [KeyboardButton("Emergency"), KeyboardButton("FAQ")]
        ]
        reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
        await update.effective_message.reply_text(bucket_text, parse_mode="Markdown", reply_markup=reply_markup)

        # Log session
        session_id = await log_session(update, "danang_bucket_list")
        context.user_data["last_session_id"] = session_id
        await log_complete_session(update, "danang_bucket_list", "Da Nang's bucket list", bucket_text)

    except Exception as e:
        logger.error(f"Error fetching Da Nang's Bucket List information: {e}")

async def verify_api_endpoints():
    """Verify which API endpoints are available and update global configuration."""
    global API_DATABASE_URL, API_RAG_URL
    if not API_DATABASE_URL:
        logger.warning("No API_DATABASE_URL configured, skipping endpoint verification")
        return
        
    logger.info(f"Verifying API endpoints for {API_DATABASE_URL}...")
    
    # Check both API structures
    session_endpoints = [
        {"path": "/session", "version": "new"},
        {"path": "/mongodb/session", "version": "legacy"}
    ]
    rag_endpoints = [
        {"path": "/chat", "version": "new"},
        {"path": "/rag/chat", "version": "legacy"}
    ]
    
    # Test session endpoints
    session_api_version = None
    for endpoint in session_endpoints:
        url = fix_url(API_DATABASE_URL, endpoint["path"])
        try:
            # Just check if the endpoint exists
            response = requests.options(url, timeout=5)
            if response.status_code != 404:
                session_api_version = endpoint["version"]
                logger.info(f"Found valid session API endpoint: {url} (version: {session_api_version})")
                break
        except Exception as e:
            logger.warning(f"Error checking endpoint {url}: {e}")
    
    # Test RAG endpoints
    rag_api_version = None
    api_base = API_RAG_URL if API_RAG_URL else API_DATABASE_URL
    for endpoint in rag_endpoints:
        url = fix_url(api_base, endpoint["path"])
        try:
            # Just check if the endpoint exists
            response = requests.options(url, timeout=5)
            if response.status_code != 404:
                rag_api_version = endpoint["version"]
                logger.info(f"Found valid RAG API endpoint: {url} (version: {rag_api_version})")
                break
        except Exception as e:
            logger.warning(f"Error checking endpoint {url}: {e}")
    
    # Log the results
    if session_api_version:
        logger.info(f"Using {session_api_version} version for session API")
    else:
        logger.warning("No valid session API endpoint found!")
    
    if rag_api_version:
        logger.info(f"Using {rag_api_version} version for RAG API")
    else:
        logger.warning("No valid RAG API endpoint found!")
        
    # Store the versions in global variables for use by the API functions
    return {
        "session_api_version": session_api_version,
        "rag_api_version": rag_api_version
    }

# Thêm vào hàm main() hoặc startup function
async def get_session_endpoint():
    """Get the correct session endpoint based on API verification."""
    # Default to legacy endpoint if verification wasn't done
    endpoint_base = "/mongodb/session"
    # Check if verification was done
    if hasattr(get_session_endpoint, "verified_endpoints"):
        if get_session_endpoint.verified_endpoints.get("session_api_version") == "new":
            endpoint_base = "/session"
    return endpoint_base

async def get_rag_endpoint():
    """Get the correct RAG endpoint based on API verification."""
    # Default to legacy endpoint if verification wasn't done
    endpoint_base = "/rag/chat"
    # Check if verification was done
    if hasattr(get_rag_endpoint, "verified_endpoints"):
        if get_rag_endpoint.verified_endpoints.get("rag_api_version") == "new":
            endpoint_base = "/chat"
    return endpoint_base

# Thêm vào startup hoặc init
if __name__ == "__main__":
    # Verify API endpoints and store results
    verified_endpoints = asyncio.run(verify_api_endpoints())
    get_session_endpoint.verified_endpoints = verified_endpoints
    get_rag_endpoint.verified_endpoints = verified_endpoints 
    
    # Create the Application and add handlers
    application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    # Add command handlers
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("events", events_command))
    application.add_handler(CommandHandler("faq", faq_command))
    application.add_handler(CommandHandler("emergency", emergency_command))
    application.add_handler(CommandHandler("help", help_command))
    
    # Add callback query handler
    application.add_handler(CallbackQueryHandler(handle_callback))
    
    # Add message handler
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    # Start the Bot with a dedicated event loop
    logger.info("Starting bot...")
    try:
        # Create a new event loop
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        # Run the application in this loop
        loop.run_until_complete(application.initialize())
        loop.run_until_complete(application.start())
        loop.run_forever()
    except (KeyboardInterrupt, SystemExit):
        logger.info("Bot stopped!")
    finally:
        # Properly close the application
        loop.run_until_complete(application.stop())
        loop.close() 