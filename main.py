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
        
        # Tạo dữ liệu phiên chat hoàn chỉnh bao gồm cả câu hỏi và phản hồi
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
            # Gửi dữ liệu phiên chat hoàn chỉnh đến API
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

# Giữ hàm log_session để tương thích ngược, nhưng không sử dụng trong mã chính
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

# Không còn cần update_session_with_response nữa, nhưng giữ lại để tương thích ngược
async def update_session_with_response(session_id: str, response_text: str):
    """Deprecated function, only kept for backward compatibility."""
    # Không thực sự làm gì cả, vì chúng ta sẽ sử dụng log_complete_session
    logger.debug(f"Deprecated call to update_session_with_response for session: {session_id}")
    return True

# Command handlers
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Send a message when the command /start is issued."""
    # Tạo ID phiên tạm thời để lưu trong context
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
        f"{commands_text}"
    )
    
    # Gửi tin nhắn đến người dùng
    await update.message.reply_text(welcome_text, reply_markup=reply_markup)
    
    # Lưu phiên hoàn chỉnh bao gồm cả lệnh và phản hồi
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
    session_id = await log_session(update, "help")
    context.user_data["last_session_id"] = session_id
    
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
    
    # Update session with bot's response
    await update_session_with_response(session_id, help_text)

# Button handlers
async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle button callbacks."""
    query = update.callback_query
    data = query.data

    # Xử lý callback từ các nút khác nhau
    if data.startswith("emergency_"):
        # Trích xuất emergency_id từ callback data
        emergency_id = data.replace("emergency_", "")
        await show_emergency_details(update, context, emergency_id)
        await log_complete_session(update, "callback_handled", f"Callback data: {data}", "Emergency callback processed")
    elif data.startswith("faq_"):
        faq_id = data.replace("faq_", "")
        await show_faq_details(update, context, faq_id)
        await log_complete_session(update, "callback_handled", f"Callback data: {data}", "FAQ callback processed")
    elif data.startswith("events_"):
        event_id = data.replace("events_", "")
        await show_event_details(update, context, event_id)
        await log_complete_session(update, "callback_handled", f"Callback data: {data}", "Event callback processed")
    else:
        # Xử lý các callback khác hoặc callback không xác định
        await query.answer("Unknown callback query")
        logger.warning(f"Unhandled callback query received: {data}")
        await log_complete_session(update, "callback_handled", f"Unknown callback data: {data}", "Callback not recognized")

# Message handler
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle user messages."""
    text = update.message.text
    
    # Tạo ID phiên tạm thời - không thực sự lưu vào cơ sở dữ liệu
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
    """Get events from API and display them."""
    try:
        if not API_DATABASE_URL:
            response_text = "Database API not configured. Cannot fetch events."
            await update.effective_message.reply_text(response_text)
            
            # Lưu phiên hoàn chỉnh
            await log_complete_session(update, action, message, response_text)
            return
            
        # Using the documented events endpoint from PostgreSQL with parameters
        endpoint_url = fix_url(API_DATABASE_URL, "/postgres/events")
        params = {
            "active_only": True,
            "featured_only": False,
            "limit": 10,
            "skip": 0,
            "use_cache": True
        }
        logger.info(f"Fetching events from: {endpoint_url}")
        
        response = requests.get(endpoint_url, params=params)
        if response.status_code == 200:
            events = response.json()
            if not events:
                response_text = "No upcoming events at the moment."
                await update.effective_message.reply_text(response_text)
                
                # Lưu phiên hoàn chỉnh
                await log_complete_session(update, action, message, response_text)
                return
            
            # Combine all events into a single response for logging
            all_events_text = ""    
            for event in events:
                # Format price information
                price_info = "Free"
                if event.get('price') and len(event.get('price')) > 0:
                    price = event.get('price')[0]
                    if price.get('amount') > 0:
                        price_info = f"{price.get('amount')} {price.get('currency', '')}"
                
                # Format date and time
                start_date = event.get('date_start', '').replace('T', ' ').split('.')[0] if event.get('date_start') else 'TBA'
                end_date = event.get('date_end', '').replace('T', ' ').split('.')[0] if event.get('date_end') else 'TBA'
                
                # Create event text
                event_text = (
                    f"🎉 *{event.get('name', 'Event')}*\n"
                    f"📝 {event.get('description', 'No description available')}\n"
                    f"📍 Location: {event.get('address', 'TBA')}\n"
                    f"⏰ Start: {start_date}\n"
                    f"⏰ End: {end_date}\n"
                    f"💰 Price: {price_info}"
                )
                await update.effective_message.reply_text(event_text, parse_mode="Markdown")
                
                # Add to combined text for logging
                all_events_text += event_text + "\n\n"
            
            # Lưu phiên hoàn chỉnh với tất cả các sự kiện
            await log_complete_session(update, action, message, all_events_text)
            
            # Show the keyboard again to ensure buttons are available
            keyboard = [
                [KeyboardButton("Da Nang's bucket list"), KeyboardButton("Solana Summit Event")],
                [KeyboardButton("Events"), KeyboardButton("About Pixity")],
                [KeyboardButton("Emergency"), KeyboardButton("FAQ")]
            ]
            reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
            await update.effective_message.reply_text("", reply_markup=reply_markup)
        else:
            error_text = f"Failed to fetch events. Status: {response.status_code}"
            logger.error(f"Failed to fetch events: {response.status_code} - {response.text}")
            await update.effective_message.reply_text(error_text)
            
            # Lưu phiên với thông báo lỗi
            await log_complete_session(update, action, message, error_text)
    except Exception as e:
        error_text = "An error occurred while fetching events. Please try again later."
        logger.error(f"Error fetching events: {e}")
        await update.effective_message.reply_text(error_text)
        
        # Lưu phiên với thông báo lỗi
        await log_complete_session(update, action, message, error_text)

async def get_emergency(update: Update, context: ContextTypes.DEFAULT_TYPE, action: str, message: str):
    """Get emergency information from API and display it."""
    try:
        if not API_DATABASE_URL:
            response_text = "Database API not configured. Cannot fetch emergency information."
            await update.effective_message.reply_text(response_text)
            
            # Lưu phiên hoàn chỉnh
            await log_complete_session(update, action, message, response_text)
            return
            
        # Using the emergency endpoint from PostgreSQL
        endpoint_url = fix_url(API_DATABASE_URL, "/postgres/emergency")
        logger.info(f"Fetching emergency information from: {endpoint_url}")
        
        response = requests.get(endpoint_url)
        if response.status_code == 200:
            emergency_info = response.json()
            if not emergency_info:
                response_text = "No emergency information available."
                await update.effective_message.reply_text(response_text)
                
                # Lưu phiên hoàn chỉnh
                await log_complete_session(update, action, message, response_text)
                return
                
            emergency_text = "🚨 *Emergency Information* 🚨\n\n"
            
            # Sort contacts by type
            contacts_by_type = {}
            for contact in emergency_info:
                contact_type = contact.get("type", "Other")
                if contact_type not in contacts_by_type:
                    contacts_by_type[contact_type] = []
                contacts_by_type[contact_type].append(contact)
            
            # Format by type
            for contact_type, contacts in contacts_by_type.items():
                emergency_text += f"*{contact_type.upper()}*\n"
                for contact in contacts:
                    name = contact.get("name", "Unknown")
                    phone = contact.get("phone", "No phone")
                    description = contact.get("description", "")
                    
                    emergency_text += f"• *{name}*: {phone}\n"
                    if description:
                        emergency_text += f"  {description}\n"
                emergency_text += "\n"
            
            # Send the formatted emergency information
            await update.effective_message.reply_text(emergency_text, parse_mode="Markdown")
            
            # Lưu phiên hoàn chỉnh
            await log_complete_session(update, action, message, emergency_text)
            
            # Show the keyboard again
            keyboard = [
                [KeyboardButton("Da Nang's bucket list"), KeyboardButton("Solana Summit Event")],
                [KeyboardButton("Events"), KeyboardButton("About Pixity")],
                [KeyboardButton("Emergency"), KeyboardButton("FAQ")]
            ]
            reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
            await update.effective_message.reply_text("", reply_markup=reply_markup)
        else:
            error_text = f"Failed to fetch emergency information. Status: {response.status_code}"
            logger.error(f"Failed to fetch emergency info: {response.status_code} - {response.text}")
            await update.effective_message.reply_text(error_text)
            
            # Lưu phiên với thông báo lỗi
            await log_complete_session(update, action, message, error_text)
    except Exception as e:
        error_text = "An error occurred while fetching emergency information. Please try again later."
        logger.error(f"Error fetching emergency info: {e}")
        await update.effective_message.reply_text(error_text)
        
        # Lưu phiên với thông báo lỗi
        await log_complete_session(update, action, message, error_text)

async def show_emergency_details(update: Update, context: ContextTypes.DEFAULT_TYPE, emergency_id: str):
    """Display details for a selected emergency contact."""
    # Chức năng này không còn cần thiết vì chúng ta đã hiển thị tất cả thông tin khẩn cấp trong một tin nhắn
    # Thay vào đó, chúng ta sẽ ghi log query callback và gửi tin nhắn hướng dẫn
    callback_query = update.callback_query
    
    if callback_query:
        await callback_query.answer()
        
        # Ghi log query callback
        logger.info(f"Emergency callback received for ID: {emergency_id}")
        
        # Phản hồi người dùng
        await callback_query.message.reply_text(
            "Tất cả thông tin khẩn cấp đã được hiển thị ở trên. Vui lòng liên hệ số điện thoại phù hợp nếu bạn cần hỗ trợ.",
            parse_mode="Markdown"
        )
        
        # Ghi log phiên
        await log_complete_session(
            update, 
            "emergency_details", 
            f"Emergency detail request: {emergency_id}", 
            "Emergency details provided"
        )

async def get_faq(update: Update, context: ContextTypes.DEFAULT_TYPE, action: str, message: str):
    """Get FAQ information from API and display it."""
    try:
        if not API_DATABASE_URL:
            response_text = "Database API not configured. Cannot fetch FAQ information."
            await update.effective_message.reply_text(response_text)
            
            # Lưu phiên hoàn chỉnh
            await log_complete_session(update, action, message, response_text)
            return
            
        # Using the documented FAQ endpoint from PostgreSQL with parameters
        endpoint_url = fix_url(API_DATABASE_URL, "/postgres/faq")
        params = {
            "active_only": True,
            "limit": 10,
            "use_cache": True
        }
        logger.info(f"Fetching FAQ from: {endpoint_url}")
        
        response = requests.get(endpoint_url, params=params)
        if response.status_code == 200:
            faqs = response.json()
            if not faqs:
                response_text = "No FAQ information available."
                await update.effective_message.reply_text(response_text)
                
                # Lưu phiên hoàn chỉnh
                await log_complete_session(update, action, message, response_text)
                return
                
            keyboard = []
            for i, faq in enumerate(faqs):
                keyboard.append([InlineKeyboardButton(
                    faq.get('question', f'Question {i+1}'), 
                    callback_data=f"faq_{i}"
                )])
            
            prompt_text = "Please select a question:"
            reply_markup = InlineKeyboardMarkup(keyboard)
            await update.effective_message.reply_text(
                prompt_text, 
                reply_markup=reply_markup
            )
            
            # Create a text representation of the FAQ options for logging
            faq_options = "FAQ Options:\n"
            for i, faq in enumerate(faqs):
                faq_options += f"- {faq.get('question', f'Question {i+1}')}\n"
            
            # Lưu phiên hoàn chỉnh
            complete_response = prompt_text + "\n\n" + faq_options
            await log_complete_session(update, action, message, complete_response)
            
            # Store FAQs in context for later use
            context.user_data["faqs"] = faqs
        else:
            error_text = f"Failed to fetch FAQ information. Status: {response.status_code}"
            logger.error(f"Failed to fetch FAQ info: {response.status_code} - {response.text}")
            await update.effective_message.reply_text(error_text)
            
            # Lưu phiên với thông báo lỗi
            await log_complete_session(update, action, message, error_text)
    except Exception as e:
        error_text = "An error occurred while fetching FAQ information. Please try again later."
        logger.error(f"Error fetching FAQ information: {e}")
        await update.effective_message.reply_text(error_text)
        
        # Lưu phiên với thông báo lỗi
        await log_complete_session(update, action, message, error_text)

async def show_faq_details(update: Update, context: ContextTypes.DEFAULT_TYPE, faq_id: str):
    """Show details for a specific FAQ."""
    query = update.callback_query
    faqs = context.user_data.get("faqs", [])
    
    try:
        faq_index = int(faq_id)
        if faq_index < len(faqs):
            faq = faqs[faq_index]
            
            faq_text = (
                f"❓ *Question:*\n{faq.get('question', 'Unknown question')}\n\n"
                f"✅ *Answer:*\n{faq.get('answer', 'No answer available.')}"
            )
            # Gửi tin nhắn mới thay vì chỉnh sửa tin nhắn hiện có
            await query.message.reply_text(faq_text, parse_mode="Markdown")
            
            # Hiển thị bàn phím lại để đảm bảo các nút có sẵn
            keyboard = [
                [KeyboardButton("Da Nang's bucket list"), KeyboardButton("Solana Summit Event")],
                [KeyboardButton("Events"), KeyboardButton("About Pixity")],
                [KeyboardButton("Emergency"), KeyboardButton("FAQ")]
            ]
            reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
            follow_up_text = "Bạn còn muốn biết điều gì khác không?"
            await query.message.reply_text(follow_up_text, reply_markup=reply_markup)
        else:
            error_text = "Không tìm thấy câu hỏi."
            await query.answer(error_text)
            logger.error(f"FAQ không tìm thấy cho ID: {faq_id}")
    except Exception as e:
        error_text = "Đã xảy ra lỗi khi hiển thị câu trả lời."
        logger.error(f"Lỗi hiển thị câu trả lời FAQ: {e}")
        await query.answer(error_text)

async def show_event_details(update: Update, context: ContextTypes.DEFAULT_TYPE, event_id: str):
    """Show details for a specific event."""
    query = update.callback_query
    events = context.user_data.get("events", [])
    
    try:
        event_index = int(event_id)
        if event_index < len(events):
            event = events[event_index]
            
            event_text = (
                f"🎫 *{event.get('name', 'Unknown event')}*\n\n"
                f"📅 *Thời gian:* {event.get('date', 'N/A')}\n"
                f"📍 *Địa điểm:* {event.get('location', 'N/A')}\n\n"
                f"ℹ️ *Mô tả:*\n{event.get('description', 'Không có mô tả.')}"
            )
            # Gửi tin nhắn mới
            await query.message.reply_text(event_text, parse_mode="Markdown")
            
            # Hiển thị bàn phím lại
            keyboard = [
                [KeyboardButton("Da Nang's bucket list"), KeyboardButton("Solana Summit Event")],
                [KeyboardButton("Events"), KeyboardButton("About Pixity")],
                [KeyboardButton("Emergency"), KeyboardButton("FAQ")]
            ]
            reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
            follow_up_text = "Bạn còn muốn biết thông tin gì khác không?"
            await query.message.reply_text(follow_up_text, reply_markup=reply_markup)
        else:
            error_text = "Không tìm thấy sự kiện."
            await query.answer(error_text)
            logger.error(f"Sự kiện không tìm thấy cho ID: {event_id}")
    except Exception as e:
        error_text = "Đã xảy ra lỗi khi hiển thị thông tin sự kiện."
        logger.error(f"Lỗi hiển thị thông tin sự kiện: {e}")
        await query.answer(error_text)

async def get_rag_response(update: Update, context: ContextTypes.DEFAULT_TYPE, action: str, query_text: str):
    """Get response from RAG API."""
    try:
        if not API_RAG_URL and not API_DATABASE_URL:
            response_text = "API not configured. Cannot process your question."
            await update.message.reply_text(response_text)
            
            # Lưu phiên hoàn chỉnh
            await log_complete_session(update, action, query_text, response_text)
            return
            
        user = update.effective_user
        
        # Luôn sử dụng endpoint RAG cũ vì API mới chưa hoạt động
        if API_RAG_URL:
            rag_url = fix_url(API_RAG_URL, "/rag/chat")
        else:
            rag_url = fix_url(API_DATABASE_URL, "/rag/chat")
            
        logger.info(f"Sending question to RAG at: {rag_url}")
        
        # Sử dụng định dạng dữ liệu API cũ
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
        if response.status_code == 200:
            result = response.json()
            answer = result.get("answer", "I couldn't find an answer to your question.")
            
            # Process HTML formatting in the answer
            # If the API returns data with HTML tags, we'll use parse_mode=HTML
            use_html_mode = "<" in answer and ">" in answer
            
            # Handle cases where API returns HTML that doesn't comply with Telegram syntax
            # Telegram doesn't allow improperly nested tags
            if use_html_mode:
                # Ensure usernames are displayed correctly in b, i, u tags
                parse_mode = "HTML"
                logger.info("Using HTML parse mode for RAG response")
            else:
                parse_mode = None
                logger.info("Using default parse mode for RAG response")
            
            # Format sources if available
            sources = result.get("sources", [])
            response_with_sources = answer
            
            if sources:
                # Format sources theo định dạng API cũ
                if use_html_mode:
                    response_with_sources += "\n\n<b>Sources:</b>"
                    for i, source in enumerate(sources[:3]):  # Limit to 3 sources
                        source_text = source.get('source', 'Unknown')
                        response_with_sources += f"\n{i+1}. {source_text}"
                else:
                    response_with_sources += "\n\nSources:"
                    for i, source in enumerate(sources[:3]):  # Limit to 3 sources
                        source_text = source.get('source', 'Unknown')
                        response_with_sources += f"\n{i+1}. {source_text}"
            
            # Send response to user
            await update.message.reply_text(response_with_sources, parse_mode=parse_mode)
            
            # Lưu phiên hoàn chỉnh bao gồm cả câu hỏi và phản hồi
            await log_complete_session(update, action, query_text, response_with_sources)
            
            # Show the keyboard again to ensure buttons are available
            keyboard = [
                [KeyboardButton("Da Nang's bucket list"), KeyboardButton("Solana Summit Event")],
                [KeyboardButton("Events"), KeyboardButton("About Pixity")],
                [KeyboardButton("Emergency"), KeyboardButton("FAQ")]
            ]
            reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
            follow_up_text = "Is there anything else you would like to know?"
            await update.message.reply_text(follow_up_text, reply_markup=reply_markup)
            
            logger.info("RAG response sent to user")
        else:
            error_text = f"Failed to get a response. Status: {response.status_code}"
            logger.error(f"Failed to get RAG response: {response.status_code} - {response.text}")
            await update.message.reply_text(error_text)
            
            # Lưu phiên với thông báo lỗi
            await log_complete_session(update, action, query_text, error_text)
    except Exception as e:
        error_text = "An error occurred while processing your question. Please try again later."
        logger.error(f"Error getting RAG response: {e}")
        await update.message.reply_text(error_text)
        
        # Lưu phiên với thông báo lỗi
        await log_complete_session(update, action, query_text, error_text)

async def get_about_pixity(update: Update, context: ContextTypes.DEFAULT_TYPE, action: str, message: str):
    """Get About Pixity information from API and display it."""
    try:
        if not API_DATABASE_URL:
            response_text = "Database API not configured. Cannot fetch About Pixity information."
            await update.effective_message.reply_text(response_text)
            
            # Lưu phiên hoàn chỉnh
            await log_complete_session(update, action, message, response_text)
            return
            
        # Using the documented about-pixity endpoint from PostgreSQL API with cache
        endpoint_url = fix_url(API_DATABASE_URL, "/postgres/about-pixity")
        params = {
            "use_cache": True
        }
        logger.info(f"Fetching About Pixity info from: {endpoint_url}")
        
        response = requests.get(endpoint_url, params=params)
        if response.status_code == 200:
            about_data = response.json()
            if not about_data or not about_data.get('content'):
                # Fallback text if API doesn't return data
                about_text = (
                    "PiXity is your smart, AI-powered local companion designed to help foreigners navigate life in any city of "
                    "Vietnam with ease, starting with Da Nang. From finding late-night eats to handling visas, housing, and healthcare, "
                    "PiXity bridges the gap in language, culture, and local know-how — so you can explore the city like a true insider.\n\n"
                    "PiXity is proudly built by PiX.teq, the tech team behind PiX — a multidisciplinary collective based in Da Nang.\n\n"
                    "X: x.com/pixity_bot\n"
                    "Instagram: instagram.com/pixity.aibot/\n"
                    "Tiktok: tiktok.com/@pixity.aibot"
                )
            else:
                # Xử lý response có định dạng JSON
                try:
                    content_obj = json.loads(about_data.get('content'))
                    about_text = content_obj.get('content', about_data.get('content'))
                except:
                    about_text = about_data.get('content')
                
            # Send response to user
            await update.effective_message.reply_text(about_text)
            
            # Lưu phiên hoàn chỉnh
            await log_complete_session(update, action, message, about_text)
            
            # Show the keyboard again to ensure buttons are available
            keyboard = [
                [KeyboardButton("Da Nang's bucket list"), KeyboardButton("Solana Summit Event")],
                [KeyboardButton("Events"), KeyboardButton("About Pixity")],
                [KeyboardButton("Emergency"), KeyboardButton("FAQ")]
            ]
            reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
            await update.effective_message.reply_text("", reply_markup=reply_markup)
        else:
            error_text = f"Failed to fetch About Pixity information. Status: {response.status_code}"
            logger.error(f"Failed to fetch About Pixity info: {response.status_code} - {response.text}")
            await update.effective_message.reply_text(error_text)
            
            # Lưu phiên với thông báo lỗi
            await log_complete_session(update, action, message, error_text)
    except Exception as e:
        error_text = "An error occurred while fetching About Pixity information. Please try again later."
        logger.error(f"Error fetching About Pixity information: {e}")
        await update.effective_message.reply_text(error_text)
        
        # Lưu phiên với thông báo lỗi
        await log_complete_session(update, action, message, error_text)

async def get_solana_summit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Get Solana Summit information from API and display it."""
    try:
        if not API_DATABASE_URL:
            response_text = "Database API not configured. Cannot fetch Solana Summit information."
            await update.effective_message.reply_text(response_text)
            # Update session with response
            session_id = context.user_data.get("last_session_id")
            await update_session_with_response(session_id, response_text)
            return
            
        # Using the documented solana-summit endpoint from PostgreSQL API with cache
        endpoint_url = fix_url(API_DATABASE_URL, "/postgres/solana-summit")
        params = {
            "use_cache": True
        }
        logger.info(f"Fetching Solana Summit info from: {endpoint_url}")
        
        response = requests.get(endpoint_url, params=params)
        if response.status_code == 200:
            summit_data = response.json()
            
            if not summit_data or not summit_data.get('content'):
                # Fallback text if API doesn't return data
                solana_summit_info = (
                    "🌟 *Solana Summit APAC 2025* 🌟\n\n"
                    "Solana's biggest founder and developer conference returns to APAC!\n\n"
                    "📅 *Date & Time:*\n"
                    "Thursday, June 5, 2025, 9:00 AM –\n"
                    "Saturday, June 7, 2025, 6:00 PM (GMT+7)\n\n"
                    "📍 *Location:*\n"
                    "KOI Resort & Residence Da Nang\n"
                    "11 Trường Sa, Hòa Hải, Ngũ Hành Sơn, Đà Nẵng, Vietnam\n\n"
                    "🔍 *About the Event:*\n"
                    "• 1000+ attendees, ~100+ speakers & workshops\n"
                    "• Code, connect, collaborate, and conquer\n"
                    "• Networking with founders, developers, and creators\n"
                    "• Workshops and hands-on sessions with industry experts\n\n"
                    "🔗 *Event Link:*\n"
                    "[Register on Lu.ma](https://lu.ma/solana-summit-apac-2025)\n\n"
                    "📌 *Location Link:*\n"
                    "[View on Google Maps](https://maps.app.goo.gl/6z9UTCNKni83CQweA)"
                )
            else:
                # Parse JSON content from the API response
                try:
                    content_json = json.loads(summit_data.get('content'))
                    
                    # Format the data with emojis and Markdown
                    solana_summit_info = (
                        f"🌟 *{content_json.get('title', 'Solana Summit')}* 🌟\n\n"
                        f"{content_json.get('description', '')}\n\n"
                        f"📅 *Date & Time:*\n"
                        f"{content_json.get('date', 'TBA')}\n\n"
                        f"📍 *Location:*\n"
                        f"{content_json.get('location', 'TBA')}\n\n"
                        f"🔍 *About the Event:*\n"
                        f"{content_json.get('details', 'No details available.')}\n\n"
                    )
                    
                    # Add registration URL if available
                    if content_json.get('registration_url'):
                        solana_summit_info += f"🔗 *Registration:*\n[Register here]({content_json.get('registration_url')})\n\n"
                except Exception as json_error:
                    logger.error(f"Error parsing Solana Summit JSON: {json_error}")
                    solana_summit_info = summit_data.get('content', "Solana Summit information is available but couldn't be formatted properly.")
            
            # Send the formatted message with links
            await update.effective_message.reply_text(
                solana_summit_info,
                parse_mode="Markdown",
                disable_web_page_preview=False  # Allow link previews
            )
            
            # Update session with response
            session_id = context.user_data.get("last_session_id")
            await update_session_with_response(session_id, solana_summit_info)
            
            # Show the keyboard again to ensure the button doesn't disappear
            keyboard = [
                [KeyboardButton("Da Nang's bucket list"), KeyboardButton("Solana Summit Event")],
                [KeyboardButton("Events"), KeyboardButton("About Pixity")],
                [KeyboardButton("Emergency"), KeyboardButton("FAQ")]
            ]
            reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
            await update.effective_message.reply_text("", reply_markup=reply_markup)
            
            # Also update session with follow-up question
            await update_session_with_response(session_id, solana_summit_info)
        else:
            error_text = f"Failed to fetch Solana Summit information. Status: {response.status_code}"
            logger.error(f"Failed to fetch Solana Summit info: {response.status_code} - {response.text}")
            await update.effective_message.reply_text(error_text)
            
            # Update session with error response
            session_id = context.user_data.get("last_session_id")
            await update_session_with_response(session_id, error_text)
    except Exception as e:
        error_text = "An error occurred while fetching Solana Summit information. Please try again later."
        logger.error(f"Error fetching Solana Summit information: {e}")
        await update.effective_message.reply_text(error_text)
        
        # Update session with error response
        session_id = context.user_data.get("last_session_id")
        await update_session_with_response(session_id, error_text)

async def get_danang_bucket_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Get Da Nang's Bucket List information from API and display it."""
    try:
        if not API_DATABASE_URL:
            response_text = "Database API not configured. Cannot fetch Da Nang's Bucket List information."
            await update.effective_message.reply_text(response_text)
            # Update session with response
            session_id = context.user_data.get("last_session_id")
            await update_session_with_response(session_id, response_text)
            return
            
        # Using the documented danang-bucket-list endpoint from PostgreSQL API with cache
        endpoint_url = fix_url(API_DATABASE_URL, "/postgres/danang-bucket-list")
        params = {
            "use_cache": True
        }
        logger.info(f"Fetching Da Nang's Bucket List info from: {endpoint_url}")
        
        response = requests.get(endpoint_url, params=params)
        if response.status_code == 200:
            bucket_data = response.json()
            
            if not bucket_data or not bucket_data.get('content'):
                # Fallback text if API doesn't return data
                bucket_list = (
                    "📋 Da Nang's bucket list:\n\n"
                    "🏖️ Relax at My Khe Beach\n"
                    "🐉 Watch the Dragon Bridge Breathe Fire\n"
                    "⛰️ Explore the Marble Mountains\n"
                    "🍜 Join a Local Food Tour\n"
                    "🏄‍♂️ Go Stand-Up Paddleboarding (Chèo SUP) at Sunrise & Eat Squid instant noodles\n"
                    "🛒 Stroll Through Han Market\n"
                    "🚣‍♀️ Take a Basket Boat Ride in the Coconut Forest\n"
                    "🏍️ Ride motorbike on the Hai Van Pass\n"
                    "📸 Snap Photos at the Pink Cathedral (Da Nang Cathedral)\n"
                    "🍲 Try Night Street Food at Helio Market\n"
                    "☕ Chill with a Coffee at a Rooftop Café\n"
                    "🏮 Take a Day Trip to Hoi An Ancient Town"
                )
            else:
                # Parse JSON content from the API response
                try:
                    content_json = json.loads(bucket_data.get('content'))
                    
                    # Format the data from json
                    title_text = content_json.get('title', "Da Nang's bucket list")
                    bucket_list = f"📋 {title_text}:\n\n"
                    bucket_list += f"{content_json.get('description', '')}\n\n"
                    
                    # Add each item from the bucket list
                    for item in content_json.get('items', []):
                        emoji = item.get('emoji', '•')
                        name = item.get('name', '')
                        desc = item.get('description', '')
                        bucket_list += f"{emoji} {name}"
                        if desc:
                            bucket_list += f" - {desc}"
                        bucket_list += "\n"
                except Exception as json_error:
                    logger.error(f"Error parsing Bucket List JSON: {json_error}")
                    bucket_list = bucket_data.get('content', "Da Nang's Bucket List information is available but couldn't be formatted properly.")
            
            # Send response to user
            await update.effective_message.reply_text(bucket_list)
            
            # Update session with response
            session_id = context.user_data.get("last_session_id")
            await update_session_with_response(session_id, bucket_list)
            
            # Show the keyboard again to ensure buttons are available
            keyboard = [
                [KeyboardButton("Da Nang's bucket list"), KeyboardButton("Solana Summit Event")],
                [KeyboardButton("Events"), KeyboardButton("About Pixity")],
                [KeyboardButton("Emergency"), KeyboardButton("FAQ")]
            ]
            reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
            await update.effective_message.reply_text("", reply_markup=reply_markup)
            
            # Also update session with follow-up question
            await update_session_with_response(session_id, bucket_list)
        else:
            error_text = f"Failed to fetch Da Nang's Bucket List information. Status: {response.status_code}"
            logger.error(f"Failed to fetch Da Nang's Bucket List info: {response.status_code} - {response.text}")
            await update.effective_message.reply_text(error_text)
            
            # Update session with error response
            session_id = context.user_data.get("last_session_id")
            await update_session_with_response(session_id, error_text)
    except Exception as e:
        error_text = "An error occurred while fetching Da Nang's Bucket List information. Please try again later."
        logger.error(f"Error fetching Da Nang's Bucket List information: {e}")
        await update.effective_message.reply_text(error_text)
        
        # Update session with error response
        session_id = context.user_data.get("last_session_id")
        await update_session_with_response(session_id, error_text)

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