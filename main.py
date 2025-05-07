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
import html
import re
from telegram.constants import ParseMode

# Hàm tiện ích để loại bỏ thẻ HTML không hợp lệ và tự động escape nội dung
def clean_html(text):
    """
    Xử lý nội dung để hiển thị an toàn trong Telegram.
    Giữ lại các thẻ HTML hợp lệ: <b>, <i>, <a>, <code>, <pre>, <s>.
    Escape các ký tự đặc biệt khác.
    """
    if not text:
        return ""
        
    # Danh sách các thẻ HTML được Telegram hỗ trợ
    valid_tags = ['<b>', '</b>', '<i>', '</i>', '<code>', '</code>', 
                 '<pre>', '</pre>', '<s>', '</s>']
    
    # Mẫu regex cho thẻ <a>
    a_tag_pattern = r'<a\s+href=[\'"]([^\'"]+)[\'"]>(.*?)</a>'
    
    # Kiểm tra nếu văn bản đã có chứa thẻ HTML
    has_html_tags = any(tag in text.lower() for tag in valid_tags) or re.search(a_tag_pattern, text)
    
    if has_html_tags:
        # Danh sách các mẫu regex để phát hiện thẻ và nội dung của chúng
        tag_patterns = {
            'b': (r'<b>(.*?)</b>', r'<b>\1</b>'),
            'i': (r'<i>(.*?)</i>', r'<i>\1</i>'),
            'code': (r'<code>(.*?)</code>', r'<code>\1</code>'),
            'pre': (r'<pre>(.*?)</pre>', r'<pre>\1</pre>'),
            's': (r'<s>(.*?)</s>', r'<s>\1</s>'),
            'a': (a_tag_pattern, None)  # None vì chúng ta sẽ xử lý đặc biệt
        }
        
        # Đánh dấu thẻ hợp lệ để giữ lại
        placeholder_map = {}
        counter = 0
        
        # Thay thế tạm thời các thẻ hợp lệ bằng placeholder
        for tag, (pattern, replacement) in tag_patterns.items():
            matches = re.finditer(pattern, text, re.DOTALL)
            for match in matches:
                placeholder = f"PLACEHOLDER_{counter}"
                counter += 1
                
                if tag == 'a':
                    href = match.group(1)
                    content = match.group(2)
                    placeholder_map[placeholder] = f'<a href="{href}">{html.escape(content)}</a>'
                else:
                    content = match.group(1)
                    replacement_format = replacement.replace('\\1', html.escape(content))
                    placeholder_map[placeholder] = replacement_format
                
                text = text.replace(match.group(0), placeholder)
        
        # Escape toàn bộ văn bản còn lại
        text = html.escape(text)
        
        # Khôi phục các thẻ đã đánh dấu
        for placeholder, original in placeholder_map.items():
            text = text.replace(placeholder, original)
            
        return text
    else:
        # Nếu không có thẻ HTML, escape toàn bộ văn bản
        return html.escape(text)

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

# Define main menu keyboard for reuse throughout the application
MAIN_MENU = [
    [KeyboardButton("Da Nang's bucket list"), KeyboardButton("Solana Summit Event")],
    [KeyboardButton("Events"), KeyboardButton("About Pixity")],
    [KeyboardButton("Emergency"), KeyboardButton("FAQ")]
]

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
    await update.message.reply_text(
        welcome_text,
        parse_mode=ParseMode.HTML,
        disable_web_page_preview=True,
        reply_markup=reply_markup)
    
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
    
    await update.message.reply_text(
        help_text,
        parse_mode=ParseMode.HTML,
        disable_web_page_preview=True,
        reply_markup=reply_markup)
    
    # Log complete session including both command and response
    await log_complete_session(update, "help", "/help", help_text)

# Button handlers
async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle button callbacks."""
    query = update.callback_query
    data = query.data
    
    try:
        await query.answer()  # Acknowledge the button press to stop the loading indicator
        
        if data.startswith("emergency_"):
            parts = data.split("_")
            # emergency_item_{section_id}_{item_id}
            if parts[1] == "item":
                # data format: emergency_item_{section}_{item}
                _, _, section_id, item_id = parts
                await show_emergency_item(update, context, section_id, item_id)
        elif data.startswith("faq_"):
            # Extract FAQ ID from callback data
            faq_id = data.split("_")[1]
            await show_faq_answer(update, context, faq_id)
        else:
            # Handle other callbacks or undefined callbacks
            logger.warning(f"Unhandled callback query received: {data}")
            await query.message.reply_text(
                "Sorry, I couldn't process that request.",
                reply_markup=ReplyKeyboardMarkup(MAIN_MENU, resize_keyboard=True)
            )
    except Exception as e:
        logger.error(f"Error handling callback: {e}")
        await query.message.reply_text(
            f"Error processing your selection: {str(e)}",
            reply_markup=ReplyKeyboardMarkup(MAIN_MENU, resize_keyboard=True)
        )

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
            lines = ["<b>Upcoming Events</b>\n"]
            for ev in events:
                block = [f"🎉 <b>{clean_html(ev.get('name', 'Event'))}</b>"]
                if ev.get("description"):
                    block.append(f"{clean_html(ev['description'])}")
                if ev.get("address"):
                    block.append(f"📍 Location: {clean_html(ev['address'])}")
                if ev.get("date_start"):
                    start = ev["date_start"].replace("T", " ").split(".")[0]
                    block.append(f"Start: {clean_html(start)}")
                if ev.get("date_end"):
                    end = ev["date_end"].replace("T", " ").split(".")[0]
                    block.append(f"End: {clean_html(end)}")
                price_info = "💰 Price: Free"
                if ev.get("price"):
                    p = ev["price"][0]
                    if p.get("amount", 0) > 0:
                        price_info = f"💰 Price: {p['amount']} {clean_html(p.get('currency', ''))}"
                block.append(price_info)
                lines.append("\n".join(block))
            response_text = "\n\n".join(lines)

        reply_markup = ReplyKeyboardMarkup(MAIN_MENU, resize_keyboard=True)

        await update.effective_message.reply_text(
            response_text,
            parse_mode=ParseMode.HTML,
            disable_web_page_preview=True,
            reply_markup=reply_markup
        )
        await log_complete_session(update, action, message, response_text)

    except Exception as e:
        logger.error(f"Error fetching events: {e}")


async def get_emergency(update: Update, context: ContextTypes.DEFAULT_TYPE, action: str, message: str):
    """
    Phase 1: show emergency categories as inline buttons.
    Invoked from /emergency command or text handler.
    """
    from telegram import InlineKeyboardMarkup
    import requests
    
    # Fetch sections
    url = fix_url(API_DATABASE_URL, "/postgres/emergency/sections")
    resp = requests.get(url)
    if resp.status_code != 200:
        await update.message.reply_text("Failed to load categories.", reply_markup=ReplyKeyboardMarkup(MAIN_MENU, resize_keyboard=True))
        return

    sections = resp.json() or []
    if not sections:
        await update.message.reply_text("No emergency categories available.", reply_markup=ReplyKeyboardMarkup(MAIN_MENU, resize_keyboard=True))
        return

    # Build inline keyboard
    keyboard = []
    for sec in sections:
        sid = sec.get("id")
        name = sec.get("name")
        if sid and name:
            keyboard.append([InlineKeyboardButton(name, callback_data=f"emergency_{sid}")])
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(
        "Please select an emergency category:",
        reply_markup=reply_markup
    )
    await log_complete_session(update, action, message, "Emergency categories shown")



async def get_faq(update: Update, context: ContextTypes.DEFAULT_TYPE, action: str, message: str):
    """
    Show FAQ questions as inline buttons and then display answer for selected question.
    """
    try:
        if not API_DATABASE_URL:
            logger.error("Database API not configured. Cannot fetch FAQs.")
            return

        # Phase 1: list questions as inline buttons
        url = fix_url(API_DATABASE_URL, "/postgres/faq")
        logger.info(f"Fetching FAQs from: {url}")
        
        resp = requests.get(url, params={"active_only": True, "limit": 10, "use_cache": True})
        if resp.status_code != 200:
            logger.error(f"Failed to fetch FAQs: {resp.status_code}")
            return

        faqs = resp.json() or []
        if not faqs:
            text = "No FAQs available."
            await update.effective_message.reply_text(
                text,
                reply_markup=ReplyKeyboardMarkup(MAIN_MENU, resize_keyboard=True)
            )
            await log_complete_session(update, action, message, text)
            return

        # Create inline keyboard with full FAQ questions
        keyboard = []
        for faq in faqs:
            faq_id = faq.get("id")
            question = faq.get("question", "Unknown")
            if faq_id and question:
                keyboard.append(
                    [InlineKeyboardButton(question, callback_data=f"faq_{faq_id}")]
                )
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        # Show the menu with inline buttons
        await update.effective_message.reply_text(
            "Frequently Asked Questions:",
            reply_markup=reply_markup
        )

        await log_complete_session(update, action, message, "FAQ questions shown as inline buttons")

    except Exception as e:
        logger.error(f"Error in get_faq: {e}")
        # Fallback to main menu if error
        reply_markup = ReplyKeyboardMarkup(MAIN_MENU, resize_keyboard=True)
        await update.effective_message.reply_text(
            f"Error loading FAQ questions: {e}",
            reply_markup=reply_markup
        )



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
        
        # Đảm bảo an toàn HTML cho câu trả lời
        escaped_answer = clean_html(answer)
        
        if sources := result.get("sources"):
            escaped_answer += "\n\nSources:"
            for i, src in enumerate(sources[:3], 1):
                source = clean_html(src.get('source','Unknown'))
                escaped_answer += f"\n{i}. {source}"

        # Send answer with HTML parsing mode
        await update.message.reply_text(
            escaped_answer,
            parse_mode=ParseMode.HTML
        )
        await log_complete_session(update, action, query_text, answer)

        # Re-show main keyboard
        reply_markup = ReplyKeyboardMarkup(MAIN_MENU, resize_keyboard=True)
        
        # Send another message with the keyboard if not already sent
        if not escaped_answer:
            await update.message.reply_text(
                "Is there anything else I can help you with?",
                reply_markup=reply_markup
            )

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
            
        # Đảm bảo an toàn HTML cho nội dung
        escaped_about_text = clean_html(about_text)

        reply_markup = ReplyKeyboardMarkup(MAIN_MENU, resize_keyboard=True)
        await update.effective_message.reply_text(
            escaped_about_text or "Information unavailable.", 
            reply_markup=reply_markup,
            parse_mode=ParseMode.HTML
        )
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

            # Build a clean list of lines with HTML escaping
            lines = [f"📋 <b>{clean_html(title)}</b>:"]
            if description:
                lines.append(clean_html(description))

            for item in items:
                emoji = item.get("emoji", "•")
                name = clean_html(item.get("name", "").strip())
                desc = clean_html(item.get("description", "").strip())
                line = f"{emoji} {name}" + (f" – {desc}" if desc else "")
                lines.append(line)

            bucket_text = "\n".join(lines)

        except Exception:
            # Fallback nếu JSON malformed
            bucket_text = clean_html(raw.strip()) or "Da Nang's Bucket List information is unavailable."

        # Gửi cùng keyboard
        reply_markup = ReplyKeyboardMarkup(MAIN_MENU, resize_keyboard=True)
        await update.effective_message.reply_text(
            bucket_text, 
            parse_mode=ParseMode.HTML, 
            reply_markup=reply_markup
        )

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

# Hàm để đăng ký các lệnh gợi ý khi người dùng nhấn / trên Telegram
async def set_commands(application):
    """Register bot commands to be shown in Telegram interface."""
    commands = [
        ("start", "Start the bot and display the main menu"),
        ("events", "Show upcoming events"),
        ("faq", "Show frequently asked questions"),
        ("emergency", "List of emergency contacts"),
        ("help", "Display help information")
    ]
    
    await application.bot.set_my_commands(commands)
    logger.info("Bot commands have been set successfully")

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
    
    # Set bot commands for menu suggestions
    asyncio.run(set_commands(application))
    
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

async def show_emergency_details(update: Update, context: ContextTypes.DEFAULT_TYPE, section_id: str):
    """
    Phase 2: show either item-submenu or full details for section.
    """
    from telegram import InlineKeyboardMarkup
    import requests

    query = update.callback_query
    # Fetch entries
    url = fix_url(API_DATABASE_URL, f"/postgres/emergency/section/{section_id}")
    resp = requests.get(url, params={"active_only": True, "use_cache": True})
    if resp.status_code != 200:
        await query.message.reply_text("Failed to load details.", reply_markup=ReplyKeyboardMarkup(MAIN_MENU, resize_keyboard=True))
        return

    items = resp.json() or []
    if not items:
        await query.message.reply_text("No entries found.", reply_markup=ReplyKeyboardMarkup(MAIN_MENU, resize_keyboard=True))
        return

    # For sections that need sub-menu
    if section_id in ["3", "5"]:
        # build item-buttons
        keyboard = []
        for it in items:
            iid = it.get("id")
            name = it.get("name")
            if iid and name:
                keyboard.append([InlineKeyboardButton(name, callback_data=f"emergency_item_{section_id}_{iid}")])
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.message.reply_text(
            "Please select an entry:",
            reply_markup=reply_markup
        )
        await log_complete_session(update, "emergency_section", section_id, "Submenu shown")
    else:
        # show full list
        lines = []
        for it in items:
            name = it.get("name", "Unknown")
            phone = it.get("phone_number") or "N/A"
            desc = it.get("description") or ""
            addr = it.get("address") or ""
            lines.append(f"• {name}: {phone}")
            if desc:
                lines.extend(desc.split("\n"))
            if addr:
                lines.append(f"Address: {addr}")
            lines.append("")
        text = "\n".join(lines).strip()
        await query.message.reply_text(text, reply_markup=ReplyKeyboardMarkup(MAIN_MENU, resize_keyboard=True))
        await log_complete_session(update, "emergency_section", section_id, text)


async def show_emergency_item(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    section_id: str,
    item_id: str
):
    """
    Phase 3: show detail for a single item.
    """
    query = update.callback_query
    import requests

    # Fetch section items
    url = fix_url(API_DATABASE_URL, f"/postgres/emergency/section/{section_id}")
    resp = requests.get(url, params={"active_only": True, "use_cache": True})
    if resp.status_code != 200:
        await query.message.reply_text("Failed to load item.", reply_markup=ReplyKeyboardMarkup(MAIN_MENU, resize_keyboard=True))
        return

    items = resp.json() or []
    item = next((i for i in items if str(i.get("id")) == item_id), None)
    if not item:
        await query.message.reply_text("Entry not found.", reply_markup=ReplyKeyboardMarkup(MAIN_MENU, resize_keyboard=True))
        return

    # Build detail message
    lines = [item.get("name", "Unknown")]
    if item.get("phone_number"):
        lines.append(f"Phone: {item['phone_number']}")
    if item.get("description"):
        for dl in item["description"].split("\n"):
            if dl.strip():
                lines.append(dl.strip())
    if item.get("address"):
        lines.append(f"Address: {item['address']}")
    text = "\n".join(lines)

    await query.message.reply_text(text, reply_markup=ReplyKeyboardMarkup(MAIN_MENU, resize_keyboard=True))
    await log_complete_session(update, "emergency_item", f"{section_id}/{item_id}", text)




async def show_faq_answer(update: Update, context: ContextTypes.DEFAULT_TYPE, faq_id):
    """Show answer for selected FAQ question."""
    query = update.callback_query
    
    try:
        if not API_DATABASE_URL:
            await query.message.reply_text("Database API not configured.")
            return

        url = fix_url(API_DATABASE_URL, f"/postgres/faq/{faq_id}")
        logger.info(f"Fetching FAQ answer from: {url}")
        
        resp = requests.get(url)
        if resp.status_code != 200:
            logger.error(f"Failed to fetch FAQ answer: {resp.status_code}")
            await query.message.reply_text(
                f"Failed to get FAQ answer. Status code: {resp.status_code}",
                reply_markup=ReplyKeyboardMarkup(MAIN_MENU, resize_keyboard=True)
            )
            return
        
        data = resp.json() or {}
        question = data.get("question", "Unknown question")
        answer = data.get("answer", "No answer available.")
        
        # Format response
        detail_text = f"<b>{clean_html(question)}</b>\n\n{clean_html(answer)}"
        
        # Send answer
        await query.message.reply_text(
            detail_text,
            parse_mode=ParseMode.HTML,
            reply_markup=ReplyKeyboardMarkup(MAIN_MENU, resize_keyboard=True)
        )
        
        # Log session
        await log_complete_session(
            update,
            "faq_answer",
            f"FAQ answer for question ID {faq_id}",
            detail_text
        )
        
    except Exception as e:
        logger.error(f"Error showing FAQ answer: {e}")
        await query.message.reply_text(
            f"Error showing FAQ answer: {str(e)}",
            reply_markup=ReplyKeyboardMarkup(MAIN_MENU, resize_keyboard=True)
        ) 