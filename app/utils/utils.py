import logging
import time
import uuid
import threading
from functools import wraps
from datetime import datetime, timedelta
import pytz
from typing import Callable, Any, Dict, Optional

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
)
logger = logging.getLogger(__name__)

# Asia/Ho_Chi_Minh timezone
asia_tz = pytz.timezone('Asia/Ho_Chi_Minh')

def generate_uuid():
    """Generate a unique identifier"""
    return str(uuid.uuid4())

def get_current_time():
    """Get current time in ISO format"""
    return datetime.now().isoformat()

def get_local_time():
    """Get current time in Asia/Ho_Chi_Minh timezone"""
    return datetime.now(asia_tz).strftime("%Y-%m-%d %H:%M:%S")

def get_local_datetime():
    """Get current datetime object in Asia/Ho_Chi_Minh timezone"""
    return datetime.now(asia_tz)

# For backward compatibility
get_vietnam_time = get_local_time
get_vietnam_datetime = get_local_datetime

def timer_decorator(func: Callable) -> Callable:
    """
    Decorator to time function execution and log results.
    """
    @wraps(func)
    async def wrapper(*args, **kwargs):
        start_time = time.time()
        try:
            result = await func(*args, **kwargs)
            elapsed_time = time.time() - start_time
            logger.info(f"Function {func.__name__} executed in {elapsed_time:.4f} seconds")
            return result
        except Exception as e:
            elapsed_time = time.time() - start_time
            logger.error(f"Function {func.__name__} failed after {elapsed_time:.4f} seconds: {e}")
            raise
    return wrapper

def sanitize_input(text):
    """Sanitize input text"""
    if not text:
        return ""
    # Remove potential dangerous characters or patterns
    return text.strip()

def truncate_text(text, max_length=100):
    """
    Truncate text to given max length and add ellipsis.
    """
    if not text or len(text) <= max_length:
        return text
    return text[:max_length] + "..."

# Simple in-memory cache implementation (replaces Redis dependency)
class SimpleCache:
    def __init__(self):
        self._cache = {}
        self._expiry = {}
    
    def get(self, key: str) -> Optional[Any]:
        """Get value from cache if it exists and hasn't expired"""
        if key in self._cache:
            # Check if the key has expired
            if key in self._expiry and self._expiry[key] > datetime.now():
                return self._cache[key]
            else:
                # Clean up expired keys
                if key in self._cache:
                    del self._cache[key]
                if key in self._expiry:
                    del self._expiry[key]
        return None
    
    def set(self, key: str, value: Any, ttl: int = 300) -> None:
        """Set a value in the cache with TTL in seconds"""
        self._cache[key] = value
        # Set expiry time
        self._expiry[key] = datetime.now() + timedelta(seconds=ttl)
    
    def delete(self, key: str) -> None:
        """Delete a key from the cache"""
        if key in self._cache:
            del self._cache[key]
        if key in self._expiry:
            del self._expiry[key]
    
    def clear(self) -> None:
        """Clear the entire cache"""
        self._cache.clear()
        self._expiry.clear()

# Initialize cache
cache = SimpleCache()

def get_host_url(request) -> str:
    """
    Get the host URL from a request object.
    """
    host = request.headers.get("host", "localhost")
    scheme = request.headers.get("x-forwarded-proto", "http")
    return f"{scheme}://{host}"

def format_time(timestamp):
    """
    Format a timestamp into a human-readable string.
    """
    return timestamp.strftime("%Y-%m-%d %H:%M:%S") 