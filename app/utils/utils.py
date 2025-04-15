import logging
import time
import uuid
from functools import wraps
from datetime import datetime
import pytz

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
)
logger = logging.getLogger(__name__)

# Vietnam timezone
vietnam_tz = pytz.timezone('Asia/Ho_Chi_Minh')

def generate_uuid():
    """Generate a unique identifier"""
    return str(uuid.uuid4())

def get_current_time():
    """Get current time in ISO format"""
    return datetime.now().isoformat()

def get_vietnam_time():
    """Get current time in Vietnam timezone and format as string"""
    return datetime.now(vietnam_tz).strftime("%Y-%m-%d %H:%M:%S")

def get_vietnam_datetime():
    """Get current time in Vietnam timezone as datetime object"""
    return datetime.now(vietnam_tz)

def timer_decorator(func):
    """Decorator to measure function execution time"""
    @wraps(func)
    async def wrapper(*args, **kwargs):
        start_time = time.time()
        result = await func(*args, **kwargs)
        execution_time = time.time() - start_time
        logger.info(f"Function {func.__name__} executed in {execution_time:.2f} seconds")
        return result
    return wrapper

def sanitize_input(text):
    """Sanitize input text"""
    if not text:
        return ""
    # Remove potential dangerous characters or patterns
    return text.strip()

def truncate_text(text, max_length=100):
    """Truncate text to a maximum length"""
    if not text or len(text) <= max_length:
        return text
    return text[:max_length] + "..." 