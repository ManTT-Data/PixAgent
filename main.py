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

# Add a new function to update the session with bot response
async def update_session_with_response(session_id: str, response_text: str):
    """Update the session with the bot's response."""
    if not session_id or not API_DATABASE_URL:
        return False
    
    try:
        # Create endpoint URL for updating the session
        endpoint_url = fix_url(API_DATABASE_URL, f"/mongodb/session/{session_id}")
        logger.info(f"Updating session with response at: {endpoint_url}")
        
        # Update data with the response text
        update_data = {
            "response": response_text
        }
        
        response = requests.put(endpoint_url, json=update_data)
        if response.status_code not in [200, 201, 204]:  # Accept success status codes
            logger.warning(f"Failed to update session with response: {response.status_code} - {response.text}")
            return False
        return True
    except Exception as e:
        logger.error(f"Error updating session with response: {e}")
        return False

# Command handlers
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Send a message when the command /start is issued."""
    session_id = await log_session(update, "start")
    context.user_data["last_session_id"] = session_id
    
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
    
    # Update session with bot's response
    await update_session_with_response(session_id, welcome_text)

async def events_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show upcoming events."""
    session_id = await log_session(update, "events")
    context.user_data["last_session_id"] = session_id
    await get_events(update, context)

async def faq_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show frequently asked questions."""
    session_id = await log_session(update, "faq")
    context.user_data["last_session_id"] = session_id
    await get_faq(update, context)
    
async def emergency_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show emergency information."""
    session_id = await log_session(update, "emergency")
    context.user_data["last_session_id"] = session_id
    await get_emergency(update, context)

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
async def handle_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle button presses."""
    query = update.callback_query
    if query:
        await query.answer()
        data = query.data
        
        if data.startswith("faq_"):
            # Handle FAQ answer selection
            session_id = await log_session(update, "faq_answer_selection", f"Selected FAQ ID: {data}")
            context.user_data["last_session_id"] = session_id
            faq_id = data.replace("faq_", "")
            await show_faq_answer(update, context, faq_id)
        elif data.startswith("emergency_"):
            # Handle emergency selection
            session_id = await log_session(update, "emergency_selection", f"Selected emergency ID: {data}")
            context.user_data["last_session_id"] = session_id
            emergency_id = data.replace("emergency_", "")
            await show_emergency_details(update, context, emergency_id)
    
# Message handler
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle user messages."""
    text = update.message.text
    
    # Handle menu button presses - store session_id for all actions
    session_id = None
    if text == "Da Nang's bucket list":
        session_id = await log_session(update, "danang_bucket_list")
        context.user_data["last_session_id"] = session_id
        await get_danang_bucket_list(update, context)
    elif text == "Solana Summit Event":
        session_id = await log_session(update, "solana_summit")
        context.user_data["last_session_id"] = session_id
        await get_solana_summit(update, context)
    elif text == "Events":
        session_id = await log_session(update, "events")
        context.user_data["last_session_id"] = session_id
        await get_events(update, context)
    elif text == "Emergency":
        session_id = await log_session(update, "emergency")
        context.user_data["last_session_id"] = session_id
        await get_emergency(update, context)
    elif text == "FAQ":
        session_id = await log_session(update, "faq")
        context.user_data["last_session_id"] = session_id
        await get_faq(update, context)
    elif text == "About Pixity":
        session_id = await log_session(update, "about_pixity")
        context.user_data["last_session_id"] = session_id
        await get_about_pixity(update, context)
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
            response_text = "Database API not configured. Cannot fetch events."
            await update.effective_message.reply_text(response_text)
            # Update session with response
            session_id = context.user_data.get("last_session_id")
            await update_session_with_response(session_id, response_text)
            return
            
        # Using the documented events endpoint from PostgreSQL with fixed URL
        endpoint_url = fix_url(API_DATABASE_URL, "/postgres/events")
        logger.info(f"Fetching events from: {endpoint_url}")
        
        response = requests.get(endpoint_url)
        if response.status_code == 200:
            events = response.json()
            if not events:
                response_text = "No upcoming events at the moment."
                await update.effective_message.reply_text(response_text)
                # Update session with response
                session_id = context.user_data.get("last_session_id")
                await update_session_with_response(session_id, response_text)
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
            
            # Update session with all events response
            session_id = context.user_data.get("last_session_id")
            await update_session_with_response(session_id, all_events_text)
            
            # Show the keyboard again to ensure buttons are available
            keyboard = [
                [KeyboardButton("Da Nang's bucket list"), KeyboardButton("Solana Summit Event")],
                [KeyboardButton("Events"), KeyboardButton("About Pixity")],
                [KeyboardButton("Emergency"), KeyboardButton("FAQ")]
            ]
            reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
            follow_up_text = "What else would you like to know?"
            await update.effective_message.reply_text(follow_up_text, reply_markup=reply_markup)
        else:
            error_text = f"Failed to fetch events. Status: {response.status_code}"
            logger.error(f"Failed to fetch events: {response.status_code} - {response.text}")
            await update.effective_message.reply_text(error_text)
            
            # Update session with error response
            session_id = context.user_data.get("last_session_id")
            await update_session_with_response(session_id, error_text)
    except Exception as e:
        error_text = "An error occurred while fetching events. Please try again later."
        logger.error(f"Error fetching events: {e}")
        await update.effective_message.reply_text(error_text)
        
        # Update session with error response
        session_id = context.user_data.get("last_session_id")
        await update_session_with_response(session_id, error_text)

async def get_emergency(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Get emergency information from API and display it."""
    try:
        if not API_DATABASE_URL:
            response_text = "Database API not configured. Cannot fetch emergency information."
            await update.effective_message.reply_text(response_text)
            # Update session with response
            session_id = context.user_data.get("last_session_id")
            await update_session_with_response(session_id, response_text)
            return
            
        # Using the documented emergency endpoint from PostgreSQL with fixed URL
        endpoint_url = fix_url(API_DATABASE_URL, "/postgres/emergency")
        logger.info(f"Fetching emergency info from: {endpoint_url}")
        
        response = requests.get(endpoint_url)
        if response.status_code == 200:
            emergencies = response.json()
            if not emergencies:
                response_text = "No emergency information available."
                await update.effective_message.reply_text(response_text)
                # Update session with response
                session_id = context.user_data.get("last_session_id")
                await update_session_with_response(session_id, response_text)
                return
                
            keyboard = []
            for i, emergency in enumerate(emergencies):
                keyboard.append([InlineKeyboardButton(
                    emergency.get('name', f'Emergency {i+1}'), 
                    callback_data=f"emergency_{i}"
                )])
            
            prompt_text = "Please select an emergency type:"
            reply_markup = InlineKeyboardMarkup(keyboard)
            await update.effective_message.reply_text(
                prompt_text, 
                reply_markup=reply_markup
            )
            
            # Update session with response
            session_id = context.user_data.get("last_session_id")
            
            # Create a text representation of the emergency options for logging
            emergency_options = "Emergency Options:\n"
            for i, emergency in enumerate(emergencies):
                emergency_options += f"- {emergency.get('name', f'Emergency {i+1}')}\n"
            
            await update_session_with_response(session_id, prompt_text + "\n\n" + emergency_options)
            
            # Store emergencies in context for later use
            context.user_data["emergencies"] = emergencies
        else:
            error_text = f"Failed to fetch emergency information. Status: {response.status_code}"
            logger.error(f"Failed to fetch emergency info: {response.status_code} - {response.text}")
            await update.effective_message.reply_text(error_text)
            
            # Update session with error response
            session_id = context.user_data.get("last_session_id")
            await update_session_with_response(session_id, error_text)
    except Exception as e:
        error_text = "An error occurred while fetching emergency information. Please try again later."
        logger.error(f"Error fetching emergency information: {e}")
        await update.effective_message.reply_text(error_text)
        
        # Update session with error response
        session_id = context.user_data.get("last_session_id")
        await update_session_with_response(session_id, error_text)

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
            
            # Update session with response
            session_id = context.user_data.get("last_session_id")
            await update_session_with_response(session_id, emergency_text)
            
            # Acknowledge the callback query to stop loading indicator
            await query.answer()
            
            # Show the keyboard again to ensure buttons are available
            keyboard = [
                [KeyboardButton("Da Nang's bucket list"), KeyboardButton("Solana Summit Event")],
                [KeyboardButton("Events"), KeyboardButton("About Pixity")],
                [KeyboardButton("Emergency"), KeyboardButton("FAQ")]
            ]
            reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
            follow_up_text = "Is there anything else you would like to know?"
            await query.message.reply_text(follow_up_text, reply_markup=reply_markup)
            
            # Update session with follow-up question
            await update_session_with_response(session_id, emergency_text + "\n\n" + follow_up_text)
        else:
            error_text = "Emergency information not found."
            await query.answer(error_text)
            
            # Update session with error response
            session_id = context.user_data.get("last_session_id")
            await update_session_with_response(session_id, error_text)
    except Exception as e:
        error_text = "An error occurred while showing emergency details."
        logger.error(f"Error showing emergency details: {e}")
        await query.answer(error_text)
        
        # Update session with error response
        session_id = context.user_data.get("last_session_id")
        await update_session_with_response(session_id, error_text)

async def get_faq(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Get FAQ from API and display it."""
    try:
        if not API_DATABASE_URL:
            response_text = "Database API not configured. Cannot fetch FAQ."
            await update.effective_message.reply_text(response_text)
            # Update session with response
            session_id = context.user_data.get("last_session_id")
            await update_session_with_response(session_id, response_text)
            return
            
        # Using the documented FAQ endpoint from PostgreSQL with fixed URL
        endpoint_url = fix_url(API_DATABASE_URL, "/postgres/faq")
        logger.info(f"Fetching FAQ from: {endpoint_url}")
        
        response = requests.get(endpoint_url)
        if response.status_code == 200:
            faqs = response.json()
            if not faqs:
                response_text = "No FAQ available."
                await update.effective_message.reply_text(response_text)
                # Update session with response
                session_id = context.user_data.get("last_session_id")
                await update_session_with_response(session_id, response_text)
                return
                
            keyboard = []
            for i, faq in enumerate(faqs):
                keyboard.append([InlineKeyboardButton(
                    faq.get('question', f'Question {i+1}')[:40] + "...", 
                    callback_data=f"faq_{i}"
                )])
            
            prompt_text = "Frequently Asked Questions:"
            reply_markup = InlineKeyboardMarkup(keyboard)
            await update.effective_message.reply_text(
                prompt_text, 
                reply_markup=reply_markup
            )
            
            # Update session with response
            session_id = context.user_data.get("last_session_id")
            
            # Create a text representation of the FAQ options for logging
            faq_options = "FAQ Options:\n"
            for i, faq in enumerate(faqs):
                faq_options += f"- {faq.get('question', f'Question {i+1}')}\n"
            
            await update_session_with_response(session_id, prompt_text + "\n\n" + faq_options)
            
            # Store FAQs in context for later use
            context.user_data["faqs"] = faqs
        else:
            error_text = f"Failed to fetch FAQ. Status: {response.status_code}"
            logger.error(f"Failed to fetch FAQ: {response.status_code} - {response.text}")
            await update.effective_message.reply_text(error_text)
            
            # Update session with error response
            session_id = context.user_data.get("last_session_id")
            await update_session_with_response(session_id, error_text)
    except Exception as e:
        error_text = "An error occurred while fetching FAQ. Please try again later."
        logger.error(f"Error fetching FAQ: {e}")
        await update.effective_message.reply_text(error_text)
        
        # Update session with error response
        session_id = context.user_data.get("last_session_id")
        await update_session_with_response(session_id, error_text)

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
            
            # Update session with response
            session_id = context.user_data.get("last_session_id")
            await update_session_with_response(session_id, faq_text)
            
            # Acknowledge the callback query to stop loading indicator
            await query.answer()
            
            # Show the keyboard again to ensure buttons are available
            keyboard = [
                [KeyboardButton("Da Nang's bucket list"), KeyboardButton("Solana Summit Event")],
                [KeyboardButton("Events"), KeyboardButton("About Pixity")],
                [KeyboardButton("Emergency"), KeyboardButton("FAQ")]
            ]
            reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
            follow_up_text = "Is there anything else you would like to know?"
            await query.message.reply_text(follow_up_text, reply_markup=reply_markup)
            
            # Update session with follow-up question
            await update_session_with_response(session_id, faq_text + "\n\n" + follow_up_text)
        else:
            error_text = "FAQ not found."
            await query.answer(error_text)
            
            # Update session with error response
            session_id = context.user_data.get("last_session_id")
            await update_session_with_response(session_id, error_text)
    except Exception as e:
        error_text = "An error occurred while showing the answer."
        logger.error(f"Error showing FAQ answer: {e}")
        await query.answer(error_text)
        
        # Update session with error response
        session_id = context.user_data.get("last_session_id")
        await update_session_with_response(session_id, error_text)

async def get_rag_response(update: Update, context: ContextTypes.DEFAULT_TYPE, query_text: str):
    """Get response from RAG API."""
    try:
        if not API_RAG_URL and not API_DATABASE_URL:
            response_text = "API not configured. Cannot process your question."
            await update.message.reply_text(response_text)
            # Update session with response
            session_id = context.user_data.get("last_session_id")
            await update_session_with_response(session_id, response_text)
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
            response_with_sources = answer
            if sources:
                # If using HTML mode, ensure text after this doesn't contain HTML tags
                if use_html_mode:
                    response_with_sources += "\n\n<b>Sources:</b>"
                    for i, source in enumerate(sources[:3]):  # Limit to 3 sources
                        response_with_sources += f"\n{i+1}. {source.get('source', 'Unknown')}"
                else:
                    response_with_sources += "\n\nSources:"
                    for i, source in enumerate(sources[:3]):  # Limit to 3 sources
                        response_with_sources += f"\n{i+1}. {source.get('source', 'Unknown')}"
            
            # Send response to user
            await update.message.reply_text(response_with_sources, parse_mode=parse_mode)
            
            # Update session with bot's response
            await update_session_with_response(session_id, response_with_sources)
            
            # Show the keyboard again to ensure buttons are available
            keyboard = [
                [KeyboardButton("Da Nang's bucket list"), KeyboardButton("Solana Summit Event")],
                [KeyboardButton("Events"), KeyboardButton("About Pixity")],
                [KeyboardButton("Emergency"), KeyboardButton("FAQ")]
            ]
            reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
            follow_up_text = "Is there anything else you would like to know?"
            await update.message.reply_text(follow_up_text, reply_markup=reply_markup)
            
            # Note: According to API documentation, RAG chat now automatically 
            # saves the answer to MongoDB for the given session_id
            logger.info("RAG response sent to user and automatically saved to database")
        else:
            error_text = f"Failed to get a response. Status: {response.status_code}"
            logger.error(f"Failed to get RAG response: {response.status_code} - {response.text}")
            await update.message.reply_text(error_text)
            
            # Update session with error response
            await update_session_with_response(session_id, error_text)
    except Exception as e:
        error_text = "An error occurred while processing your question. Please try again later."
        logger.error(f"Error getting RAG response: {e}")
        await update.message.reply_text(error_text)
        
        # Update session with error response
        session_id = context.user_data.get("last_session_id")
        await update_session_with_response(session_id, error_text)

async def get_about_pixity(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Get About Pixity information from API and display it."""
    try:
        if not API_DATABASE_URL:
            response_text = "Database API not configured. Cannot fetch About Pixity information."
            await update.effective_message.reply_text(response_text)
            # Update session with response
            session_id = context.user_data.get("last_session_id")
            await update_session_with_response(session_id, response_text)
            return
            
        # Using the documented about-pixity endpoint from PostgreSQL API
        endpoint_url = fix_url(API_DATABASE_URL, "/postgres/about-pixity")
        logger.info(f"Fetching About Pixity info from: {endpoint_url}")
        
        response = requests.get(endpoint_url)
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
                about_text = about_data.get('content')
                
            # Send response to user
            await update.effective_message.reply_text(about_text)
            
            # Update session with response
            session_id = context.user_data.get("last_session_id")
            await update_session_with_response(session_id, about_text)
            
            # Show the keyboard again to ensure buttons are available
            keyboard = [
                [KeyboardButton("Da Nang's bucket list"), KeyboardButton("Solana Summit Event")],
                [KeyboardButton("Events"), KeyboardButton("About Pixity")],
                [KeyboardButton("Emergency"), KeyboardButton("FAQ")]
            ]
            reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
            follow_up_text = "What else would you like to know?"
            await update.effective_message.reply_text(follow_up_text, reply_markup=reply_markup)
        else:
            error_text = f"Failed to fetch About Pixity information. Status: {response.status_code}"
            logger.error(f"Failed to fetch About Pixity info: {response.status_code} - {response.text}")
            await update.effective_message.reply_text(error_text)
            
            # Update session with error response
            session_id = context.user_data.get("last_session_id")
            await update_session_with_response(session_id, error_text)
    except Exception as e:
        error_text = "An error occurred while fetching About Pixity information. Please try again later."
        logger.error(f"Error fetching About Pixity information: {e}")
        await update.effective_message.reply_text(error_text)
        
        # Update session with error response
        session_id = context.user_data.get("last_session_id")
        await update_session_with_response(session_id, error_text)

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
            
        # Using the documented solana-summit endpoint from PostgreSQL API
        endpoint_url = fix_url(API_DATABASE_URL, "/postgres/solana-summit")
        logger.info(f"Fetching Solana Summit info from: {endpoint_url}")
        
        response = requests.get(endpoint_url)
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
            follow_up_text = "Do you have any specific questions about the Solana Summit?"
            await update.effective_message.reply_text(
                follow_up_text,
                reply_markup=reply_markup
            )
            
            # Also update session with follow-up question
            await update_session_with_response(session_id, solana_summit_info + "\n\n" + follow_up_text)
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
            
        # Using the documented danang-bucket-list endpoint from PostgreSQL API
        endpoint_url = fix_url(API_DATABASE_URL, "/postgres/danang-bucket-list")
        logger.info(f"Fetching Da Nang's Bucket List info from: {endpoint_url}")
        
        response = requests.get(endpoint_url)
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
            follow_up_text = "What else would you like to know?"
            await update.effective_message.reply_text(follow_up_text, reply_markup=reply_markup)
            
            # Also update session with follow-up question
            await update_session_with_response(session_id, bucket_list + "\n\n" + follow_up_text)
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