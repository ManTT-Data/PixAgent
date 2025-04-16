import os
from pymongo import MongoClient
from pymongo.errors import ConnectionFailure, ServerSelectionTimeoutError
from dotenv import load_dotenv
from datetime import datetime, timedelta
import pytz
import logging

# Cấu hình logging
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()

# MongoDB connection string from .env
MONGODB_URL = os.getenv("MONGODB_URL")
DB_NAME = os.getenv("DB_NAME", "Telegram")
COLLECTION_NAME = os.getenv("COLLECTION_NAME", "session_chat")

# Thiết lập thời gian timeout cho kết nối MongoDB
MONGODB_TIMEOUT = int(os.getenv("MONGODB_TIMEOUT", "5000"))  # 5 seconds by default

# Tạo kết nối MongoDB với timeout
try:
    client = MongoClient(MONGODB_URL, serverSelectionTimeoutMS=MONGODB_TIMEOUT)
    db = client[DB_NAME]

    # Collections
    session_collection = db[COLLECTION_NAME]
    logger.info(f"MongoDB connection initialized to {DB_NAME}.{COLLECTION_NAME}")
    
except Exception as e:
    logger.error(f"Failed to initialize MongoDB connection: {e}")
    # Không raise exception để tránh crash khi khởi động, các xử lý lỗi sẽ được thực hiện ở các function

# Kiểm tra kết nối MongoDB
def check_db_connection():
    """Kiểm tra kết nối MongoDB"""
    try:
        # Issue a ping to confirm a successful connection
        client.admin.command('ping')
        logger.info("MongoDB connection is working")
        return True
    except (ConnectionFailure, ServerSelectionTimeoutError) as e:
        logger.error(f"MongoDB connection failed: {e}")
        return False
    except Exception as e:
        logger.error(f"Unknown error when checking MongoDB connection: {e}")
        return False

# Timezone for Vietnam
vietnam_tz = pytz.timezone('Asia/Ho_Chi_Minh')

def get_vietnam_time():
    """Get current time in Vietnam timezone"""
    return datetime.now(vietnam_tz).strftime("%Y-%m-%d %H:%M:%S")

def get_vietnam_datetime():
    """Get current datetime object in Vietnam timezone"""
    return datetime.now(vietnam_tz)

# Utility functions
def save_session(session_id, factor, action, first_name, last_name, message, user_id, username, response=None):
    """Save user session to MongoDB"""
    try:
        session_data = {
            "session_id": session_id,
            "factor": factor,
            "action": action,
            "created_at": get_vietnam_time(),
            "created_at_datetime": get_vietnam_datetime(),
            "first_name": first_name,
            "last_name": last_name,
            "message": message,
            "user_id": user_id,
            "username": username,
            "response": response
        }
        result = session_collection.insert_one(session_data)
        logger.info(f"Session saved with ID: {result.inserted_id}")
        return {
            "acknowledged": result.acknowledged,
            "inserted_id": str(result.inserted_id),
            "session_data": session_data
        }
    except Exception as e:
        logger.error(f"Error saving session: {e}")
        raise

def update_session_response(session_id, response):
    """Update a session with response"""
    try:
        result = session_collection.update_one(
            {"session_id": session_id},
            {"$set": {"response": response}}
        )
        
        if result.matched_count == 0:
            logger.warning(f"No session found with ID: {session_id}")
            return False
            
        logger.info(f"Session {session_id} updated with response")
        return True
    except Exception as e:
        logger.error(f"Error updating session response: {e}")
        raise

def get_recent_sessions(user_id, action, n=3):
    """Get n most recent sessions for a specific user and action"""
    try:
        return list(
            session_collection.find(
                {"user_id": user_id, "action": action},
                {"_id": 0, "message": 1, "response": 1}
            ).sort("created_at_datetime", -1).limit(n)
        )
    except Exception as e:
        logger.error(f"Error getting recent sessions: {e}")
        return []

def get_user_history(user_id, n=3):
    """Get user history for a specific user"""
    try:
        # Truy vấn trực tiếp các phiên gần nhất mà có cả message và response
        sessions = list(
            session_collection.find(
                {
                    "user_id": user_id, 
                    "action": "asking_freely",
                    "message": {"$exists": True, "$ne": None},
                    "response": {"$exists": True, "$ne": None}
                },
                {"_id": 0, "message": 1, "response": 1, "created_at_datetime": 1}
            ).sort("created_at_datetime", -1).limit(n)
        )
        
        # Chuyển đổi định dạng
        history = []
        for session in sessions:
            history.append({
                "question": session["message"],
                "answer": session["response"]
            })
        
        logger.info(f"Retrieved {len(history)} history items for user {user_id}")
        return history
    except Exception as e:
        logger.error(f"Error getting user history: {e}")
        return []

# Functions from chatbot.py
def get_chat_history(user_id, n=5):
    """Get conversation history for a specific user from MongoDB in format suitable for LLM prompt"""
    try:
        history = get_user_history(user_id, n)
        
        # Format history for prompt context
        formatted_history = ""
        for item in history:
            formatted_history += f"User: {item['question']}\nAssistant: {item['answer']}\n\n"
            
        return formatted_history
    except Exception as e:
        logger.error(f"Error getting chat history for prompt: {e}")
        return ""

def get_request_history(user_id, n=3):
    """Get the most recent user requests to use as context for retrieval"""
    try:
        history = get_user_history(user_id, n)
        
        # Just extract the questions for context
        requests = []
        for item in history:
            requests.append(item['question'])
            
        # Join all recent requests into a single string for context
        return " ".join(requests)
    except Exception as e:
        logger.error(f"Error getting request history: {e}")
        return "" 