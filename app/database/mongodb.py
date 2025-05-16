import os
from pymongo import MongoClient
from pymongo.errors import ConnectionFailure, ServerSelectionTimeoutError
from dotenv import load_dotenv
from datetime import datetime, timedelta
import pytz
import logging

# Configure logging
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()

# MongoDB connection string from .env
MONGODB_URL = os.getenv("MONGODB_URL")
DB_NAME = os.getenv("DB_NAME", "Telegram")
COLLECTION_NAME = os.getenv("COLLECTION_NAME", "session_chat")

# Set timeout for MongoDB connection
MONGODB_TIMEOUT = int(os.getenv("MONGODB_TIMEOUT", "5000"))  # 5 seconds by default

# Legacy cache settings - now only used for configuration purposes
HISTORY_CACHE_TTL = int(os.getenv("HISTORY_CACHE_TTL", "3600"))  # 1 hour by default
HISTORY_QUEUE_SIZE = int(os.getenv("HISTORY_QUEUE_SIZE", "10"))  # 10 items by default

# Create MongoDB connection with timeout
try:
    client = MongoClient(MONGODB_URL, serverSelectionTimeoutMS=MONGODB_TIMEOUT)
    db = client[DB_NAME]

    # Collections
    session_collection = db[COLLECTION_NAME]
    logger.info(f"MongoDB connection initialized to {DB_NAME}.{COLLECTION_NAME}")
    
except Exception as e:
    logger.error(f"Failed to initialize MongoDB connection: {e}")
    # Don't raise exception to avoid crash during startup, error handling will be done in functions

# Check MongoDB connection
def check_db_connection():
    """Check MongoDB connection"""
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

# Timezone for Asia/Ho_Chi_Minh
asia_tz = pytz.timezone('Asia/Ho_Chi_Minh')

def get_local_time():
    """Get current time in Asia/Ho_Chi_Minh timezone"""
    return datetime.now(asia_tz).strftime("%Y-%m-%d %H:%M:%S")

def get_local_datetime():
    """Get current datetime object in Asia/Ho_Chi_Minh timezone"""
    return datetime.now(asia_tz)

# For backward compatibility
get_vietnam_time = get_local_time
get_vietnam_datetime = get_local_datetime

# Utility functions
def save_session(session_id, factor, action, first_name, last_name, message, user_id, username, response=None):
    """Save user session to MongoDB"""
    try:
        session_data = {
            "session_id": session_id,
            "factor": factor,
            "action": action,
            "created_at": get_local_time(),
            "created_at_datetime": get_local_datetime(),
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
        # Lấy session hiện có
        existing_session = session_collection.find_one({"session_id": session_id})
        
        if not existing_session:
            logger.warning(f"No session found with ID: {session_id}")
            return False
        
        result = session_collection.update_one(
            {"session_id": session_id},
            {"$set": {"response": response}}
        )
        
        logger.info(f"Session {session_id} updated with response")
        return True
    except Exception as e:
        logger.error(f"Error updating session response: {e}")
        raise

def get_recent_sessions(user_id, action, n=3):
    """Get n most recent sessions for a specific user and action"""
    try:
        # Truy vấn trực tiếp từ MongoDB
        result = list(
            session_collection.find(
                {"user_id": user_id, "action": action},
                {"_id": 0, "message": 1, "response": 1}
            ).sort("created_at_datetime", -1).limit(n)
        )
        
        logger.debug(f"Retrieved {len(result)} recent sessions for user {user_id}, action {action}")
        return result
    except Exception as e:
        logger.error(f"Error getting recent sessions: {e}")
        return []

def get_chat_history(user_id, n = 5) -> str:
    """
    Lấy lịch sử chat cho user_id từ MongoDB và ghép thành chuỗi theo định dạng:
    
    User: ...
    Bot: ...
    User: ...
    Bot: ...
    """
    try:
        # Truy vấn các document có user_id, sắp xếp theo created_at tăng dần
        # Get the 4 most recent documents first, then sort them in ascending order
        docs = list(session_collection.find({"user_id": str(user_id)}).sort("created_at", -1).limit(n))
        # Reverse the list to get chronological order (oldest to newest)
        docs.reverse()
        if not docs:
            logger.info(f"Không tìm thấy dữ liệu cho user_id: {user_id}")
            return ""
        
        conversation_lines = []
        # Xử lý từng document theo cấu trúc mới
        for doc in docs:
            factor = doc.get("factor", "").lower()
            action = doc.get("action", "").lower()
            message = doc.get("message", "")
            response = doc.get("response", "")
            
            if factor == "user" and action == "asking_freely":
                conversation_lines.append(f"User: {message}")
                conversation_lines.append(f"Bot: {response}")
        
        # Ghép các dòng thành chuỗi
        return "\n".join(conversation_lines)
    except Exception as e:
        logger.error(f"Lỗi khi lấy lịch sử chat cho user_id {user_id}: {e}")
        return ""

def get_request_history(user_id, n=3):
    """Get the most recent user requests to use as context for retrieval"""
    try:
        # Lấy lịch sử trực tiếp từ MongoDB (thông qua get_user_history đã sửa đổi)
        history = get_chat_history(user_id, n)
        
        # Just extract the questions for context
        requests = []
        for item in history:
            requests.append(item['question'])
            
        # Join all recent requests into a single string for context
        return " ".join(requests)
    except Exception as e:
        logger.error(f"Error getting request history: {e}")
        return "" 