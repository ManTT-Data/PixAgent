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

async def log_session(update: Update, action: str, message: str = ""):
    """Log user session to database."""
    try:
        user = update.effective_user
        session_id = generate_session_id(user.id)
        
        session_data = {
            "session_id": session_id,
            "factor": "user",
            "action": action,
            "created_at": get_current_time(),
            "first_name": user.first_name or "",
            "last_name": user.last_name or "",
            "message": message,
            "user_id": str(user.id),
            "username": user.username or "",
            "response": ""  # Add empty response field to avoid errors
        }
        
        if API_DATABASE_URL:
            # Try direct API endpoint without the path prefix
            endpoint_url = fix_url(API_DATABASE_URL, "/mongodb/session")
            logger.info(f"Attempting to log session to: {endpoint_url}")
            
            try:
                response = requests.post(endpoint_url, json=session_data)
                if response.status_code not in [200, 201]:  # Accept both 200 OK and 201 Created
                    logger.warning(f"Failed to log session: {response.status_code} - {response.text}")
                return session_id
            except Exception as e:
                logger.error(f"Error posting to {endpoint_url}: {e}")
        else:
            logger.warning("Database URL not configured, session not logged")
        return session_id
    except Exception as e:
        logger.error(f"Error logging session: {e}")
        return None

# Command handlers
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Send a message when the command /start is issued."""
    await log_session(update, "start")
    
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
    
    await update.message.reply_text(welcome_text, reply_markup=reply_markup)

async def events_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show upcoming events."""
    await log_session(update, "events")
    await get_events(update, context)

async def faq_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show frequently asked questions."""
    await log_session(update, "faq")
    await get_faq(update, context)
    
async def emergency_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show emergency information."""
    await log_session(update, "emergency")
    await get_emergency(update, context)

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Send a message when the command /help is issued."""
    await log_session(update, "help")
    
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

# Button handlers
async def handle_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle button presses."""
    query = update.callback_query
    if query:
        await query.answer()
        data = query.data
        
        if data.startswith("faq_"):
            # Handle FAQ answer selection
            faq_id = data.replace("faq_", "")
            await show_faq_answer(update, context, faq_id)
        elif data.startswith("emergency_"):
            # Handle emergency selection
            emergency_id = data.replace("emergency_", "")
            await show_emergency_details(update, context, emergency_id)
    
# Message handler
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle user messages."""
    text = update.message.text
    
    # Handle menu button presses
    if text == "Da Nang's bucket list":
        await log_session(update, "danang_bucket_list")
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
        await update.message.reply_text(bucket_list)
    elif text == "Solana Summit Event":
        await log_session(update, "solana_summit")
        
        # Create beautifully formatted event information with emojis
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

        # Send the formatted message with links
        await update.message.reply_text(
            solana_summit_info,
            parse_mode="Markdown",
            disable_web_page_preview=False  # Allow link previews
        )
        
        # Ask if they want more specific information
        await update.message.reply_text(
            "Do you have any specific questions about the Solana Summit?",
            reply_markup=ReplyKeyboardMarkup([
                ["Events", "About Pixity"],
                ["Emergency", "FAQ"],
                ["Da Nang's bucket list"]
            ], resize_keyboard=True)
        )
    elif text == "Events":
        await log_session(update, "events")
        await get_events(update, context)
    elif text == "Emergency":
        await log_session(update, "emergency")
        await get_emergency(update, context)
    elif text == "FAQ":
        await log_session(update, "faq")
        await get_faq(update, context)
    elif text == "About Pixity":
        await log_session(update, "about_pixity")
        about_text = (
            "PiXity is your smart, AI-powered local companion designed to help foreigners navigate life in any city of "
            "Vietnam with ease, starting with Da Nang. From finding late-night eats to handling visas, housing, and healthcare, "
            "PiXity bridges the gap in language, culture, and local know-how — so you can explore the city like a true insider.\n\n"
            "PiXity is proudly built by PiX.teq, the tech team behind PiX — a multidisciplinary collective based in Da Nang.\n\n"
            "X: x.com/pixity_bot\n"
            "Instagram: instagram.com/pixity.aibot/\n"
            "Tiktok: tiktok.com/@pixity.aibot"
        )
        await update.message.reply_text(about_text)
    else:
        # Send message to RAG API and get response
        session_id = await log_session(update, "asking_freely", text)
        context.user_data["last_session_id"] = session_id
        await get_rag_response(update, context, text)

# API interaction functions
async def get_events(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Get events from API and display them."""
    try:
        if not API_DATABASE_URL:
            await update.effective_message.reply_text("Database API not configured. Cannot fetch events.")
            return
            
        # Using the documented events endpoint from PostgreSQL with fixed URL
        endpoint_url = fix_url(API_DATABASE_URL, "/postgres/events")
        logger.info(f"Fetching events from: {endpoint_url}")
        
        response = requests.get(endpoint_url)
        if response.status_code == 200:
            events = response.json()
            if not events:
                await update.effective_message.reply_text("No upcoming events at the moment.")
                return
                
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
        else:
            logger.error(f"Failed to fetch events: {response.status_code} - {response.text}")
            await update.effective_message.reply_text(f"Failed to fetch events. Status: {response.status_code}")
    except Exception as e:
        logger.error(f"Error fetching events: {e}")
        await update.effective_message.reply_text("An error occurred while fetching events. Please try again later.")

async def get_emergency(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Get emergency information from API and display it."""
    try:
        if not API_DATABASE_URL:
            await update.effective_message.reply_text("Database API not configured. Cannot fetch emergency information.")
            return
            
        # Using the documented emergency endpoint from PostgreSQL with fixed URL
        endpoint_url = fix_url(API_DATABASE_URL, "/postgres/emergency")
        logger.info(f"Fetching emergency info from: {endpoint_url}")
        
        response = requests.get(endpoint_url)
        if response.status_code == 200:
            emergencies = response.json()
            if not emergencies:
                await update.effective_message.reply_text("No emergency information available.")
                return
                
            keyboard = []
            for i, emergency in enumerate(emergencies):
                keyboard.append([InlineKeyboardButton(
                    emergency.get('name', f'Emergency {i+1}'), 
                    callback_data=f"emergency_{i}"
                )])
                
            reply_markup = InlineKeyboardMarkup(keyboard)
            await update.effective_message.reply_text(
                "Please select an emergency type:", 
                reply_markup=reply_markup
            )
            
            # Store emergencies in context for later use
            context.user_data["emergencies"] = emergencies
        else:
            logger.error(f"Failed to fetch emergency info: {response.status_code} - {response.text}")
            await update.effective_message.reply_text(f"Failed to fetch emergency information. Status: {response.status_code}")
    except Exception as e:
        logger.error(f"Error fetching emergency information: {e}")
        await update.effective_message.reply_text("An error occurred while fetching emergency information. Please try again later.")

async def show_emergency_details(update: Update, context: ContextTypes.DEFAULT_TYPE, emergency_id: str):
    """Show details for a specific emergency."""
    query = update.callback_query
    emergencies = context.user_data.get("emergencies", [])
    
    try:
        emergency_index = int(emergency_id)
        if emergency_index < len(emergencies):
            emergency = emergencies[emergency_index]
            emergency_text = (
                f"🚨 *{emergency.get('name', 'Emergency')}*\n\n"
                f"{emergency.get('description', 'No description available.')}\n\n"
                f"📞 Contact: {emergency.get('phone_number', 'N/A')}"
            )
            # Send as a new message instead of editing the existing one
            await query.message.reply_text(emergency_text, parse_mode="Markdown")
            # Acknowledge the callback query to stop loading indicator
            await query.answer()
        else:
            await query.answer("Emergency information not found.")
    except Exception as e:
        logger.error(f"Error showing emergency details: {e}")
        await query.answer("An error occurred while showing emergency details.")

async def get_faq(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Get FAQ from API and display it."""
    try:
        if not API_DATABASE_URL:
            await update.effective_message.reply_text("Database API not configured. Cannot fetch FAQ.")
            return
            
        # Using the documented FAQ endpoint from PostgreSQL with fixed URL
        endpoint_url = fix_url(API_DATABASE_URL, "/postgres/faq")
        logger.info(f"Fetching FAQ from: {endpoint_url}")
        
        response = requests.get(endpoint_url)
        if response.status_code == 200:
            faqs = response.json()
            if not faqs:
                await update.effective_message.reply_text("No FAQ available.")
                return
                
            keyboard = []
            for i, faq in enumerate(faqs):
                keyboard.append([InlineKeyboardButton(
                    faq.get('question', f'Question {i+1}')[:40] + "...", 
                    callback_data=f"faq_{i}"
                )])
                
            reply_markup = InlineKeyboardMarkup(keyboard)
            await update.effective_message.reply_text(
                "Frequently Asked Questions:", 
                reply_markup=reply_markup
            )
            
            # Store FAQs in context for later use
            context.user_data["faqs"] = faqs
        else:
            logger.error(f"Failed to fetch FAQ: {response.status_code} - {response.text}")
            await update.effective_message.reply_text(f"Failed to fetch FAQ. Status: {response.status_code}")
    except Exception as e:
        logger.error(f"Error fetching FAQ: {e}")
        await update.effective_message.reply_text("An error occurred while fetching FAQ. Please try again later.")

async def show_faq_answer(update: Update, context: ContextTypes.DEFAULT_TYPE, faq_id: str):
    """Show answer for a specific FAQ question."""
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
            # Send as a new message instead of editing the existing one
            await query.message.reply_text(faq_text, parse_mode="Markdown")
            # Acknowledge the callback query to stop loading indicator
            await query.answer()
        else:
            await query.answer("FAQ not found.")
    except Exception as e:
        logger.error(f"Error showing FAQ answer: {e}")
        await query.answer("An error occurred while showing the answer.")

async def get_rag_response(update: Update, context: ContextTypes.DEFAULT_TYPE, query_text: str):
    """Get response from RAG API."""
    try:
        if not API_RAG_URL and not API_DATABASE_URL:
            await update.message.reply_text("API not configured. Cannot process your question.")
            return
            
        user = update.effective_user
        
        # Select appropriate RAG endpoint
        if API_RAG_URL:
            rag_url = fix_url(API_RAG_URL, "/rag/chat")
        else:
            rag_url = fix_url(API_DATABASE_URL, "/rag/chat")
            
        logger.info(f"Sending question to RAG at: {rag_url}")
        
        # Get session ID from context if available
        session_id = context.user_data.get("last_session_id")
        
        # Prepare payload based on API documentation
        payload = {
            "user_id": str(user.id),
            "question": query_text,
            "include_history": True,
            "use_rag": True,
            "similarity_top_k": 3,
            "vector_distance_threshold": 0.75,
            "session_id": session_id,
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
            
            # If there are sources, add them to the response
            sources = result.get("sources", [])
            if sources:
                # If using HTML mode, ensure text after this doesn't contain HTML tags
                if use_html_mode:
                    answer += "\n\n<b>Sources:</b>"
                    for i, source in enumerate(sources[:3]):  # Limit to 3 sources
                        answer += f"\n{i+1}. {source.get('source', 'Unknown')}"
                else:
                    answer += "\n\nSources:"
                    for i, source in enumerate(sources[:3]):  # Limit to 3 sources
                        answer += f"\n{i+1}. {source.get('source', 'Unknown')}"
            
            await update.message.reply_text(answer, parse_mode=parse_mode)
            
            # Note: According to API documentation, RAG chat now automatically 
            # saves the answer to MongoDB for the given session_id
            logger.info("RAG response sent to user and automatically saved to database")
        else:
            logger.error(f"Failed to get RAG response: {response.status_code} - {response.text}")
            await update.message.reply_text(f"Failed to get a response. Status: {response.status_code}")
    except Exception as e:
        logger.error(f"Error getting RAG response: {e}")
        await update.message.reply_text("An error occurred while processing your question. Please try again later.") 