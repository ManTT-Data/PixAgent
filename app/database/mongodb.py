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

# Initialize variables
client = None
db = None
session_collection = None

# Create MongoDB connection with timeout
try:
    client = MongoClient(MONGODB_URL, serverSelectionTimeoutMS=MONGODB_TIMEOUT)
    db = client[DB_NAME]
    session_collection = db[COLLECTION_NAME]
    logger.info(f"MongoDB connection initialized to {DB_NAME}.{COLLECTION_NAME}")
except Exception as e:
    logger.error(f"Failed to initialize MongoDB connection: {e}")
    # Create dummy client and collection for type safety
    client = MongoClient()
    db = client[DB_NAME]
    session_collection = db[COLLECTION_NAME]

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
    
    Chỉ lấy history sau lệnh /start hoặc /clear mới nhất
    """
    try:
        # Tìm session /start hoặc /clear mới nhất
        reset_session = session_collection.find_one(
            {
                "user_id": str(user_id), 
                "$or": [
                    {"action": "start"},
                    {"action": "clear"}
                ]
            },
            sort=[("created_at_datetime", -1)]
        )
        
        # Nếu không tìm thấy session reset nào, lấy n session gần nhất
        if reset_session:
            reset_time = reset_session["created_at_datetime"]
            # Lấy các session sau reset_time
            docs = list(
                session_collection.find({
                    "user_id": str(user_id),
                    "created_at_datetime": {"$gt": reset_time}
                }).sort("created_at_datetime", 1)
            )
            logger.info(f"Lấy {len(docs)} session sau lệnh {reset_session['action']} lúc {reset_time}")
        else:
            # Không tìm thấy reset session, lấy n session gần nhất
            docs = list(session_collection.find({"user_id": str(user_id)}).sort("created_at", -1).limit(n))
            # Đảo ngược để có thứ tự từ cũ đến mới
            docs.reverse()
            logger.info(f"Không tìm thấy session reset, lấy {len(docs)} session gần nhất")
            
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
            
            # Bỏ qua lệnh start và clear
            if action in ["start", "clear"]:
                continue
                
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
        # Truy vấn trực tiếp từ MongoDB
        history = get_chat_history(user_id, n)
        
        # Just extract the questions for context
        requests = []
        for line in history.split('\n'):
            if line.startswith("User: "):
                requests.append(line[6:])  # Lấy nội dung sau "User: "
            
        # Join all recent requests into a single string for context
        return " ".join(requests)
    except Exception as e:
        logger.error(f"Error getting request history: {e}")
        return "" 