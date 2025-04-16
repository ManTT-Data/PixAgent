import logging
import time
import uuid
import threading
from functools import wraps
from datetime import datetime, timedelta
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

# Simple in-memory cache for frequent database queries
class SimpleCache:
    def __init__(self, default_ttl=300):  # Default TTL 5 minutes
        self.cache = {}
        self.locks = {}
        self.default_ttl = default_ttl
        self._cleanup_thread = threading.Thread(target=self._cleanup_loop, daemon=True)
        self._cleanup_thread.start()
    
    def get(self, key):
        """Get value from cache if it exists and is not expired"""
        if key not in self.cache:
            return None
        
        value, expiry = self.cache[key]
        if expiry and datetime.now() > expiry:
            # Expired
            del self.cache[key]
            if key in self.locks:
                del self.locks[key]
            return None
            
        return value
    
    def set(self, key, value, ttl=None):
        """Set value in cache with expiry time"""
        ttl = ttl if ttl is not None else self.default_ttl
        expiry = datetime.now() + timedelta(seconds=ttl) if ttl > 0 else None
        self.cache[key] = (value, expiry)
        return value
    
    def delete(self, key):
        """Delete key from cache"""
        if key in self.cache:
            del self.cache[key]
        if key in self.locks:
            del self.locks[key]
    
    def clear(self):
        """Clear entire cache"""
        self.cache.clear()
        self.locks.clear()
    
    def get_lock(self, key):
        """Get lock for key to prevent thundering herd"""
        if key not in self.locks:
            self.locks[key] = threading.Lock()
        return self.locks[key]
    
    def _cleanup_loop(self):
        """Background thread to clean up expired entries"""
        while True:
            time.sleep(60)  # Run every minute
            try:
                now = datetime.now()
                keys_to_delete = []
                
                for key, (_, expiry) in self.cache.items():
                    if expiry and now > expiry:
                        keys_to_delete.append(key)
                
                for key in keys_to_delete:
                    self.delete(key)
                    
                logger.debug(f"Cache cleanup: removed {len(keys_to_delete)} expired entries")
            except Exception as e:
                logger.error(f"Error in cache cleanup: {e}")
    
    def cached(self, ttl=None):
        """Decorator to cache function results"""
        def decorator(func):
            @wraps(func)
            def wrapper(*args, **kwargs):
                # Create cache key from function name and arguments
                key_parts = [func.__name__]
                key_parts.extend(str(arg) for arg in args)
                key_parts.extend(f"{k}={v}" for k, v in sorted(kwargs.items()))
                key = ":".join(key_parts)
                
                # Try to get from cache
                result = self.get(key)
                if result is not None:
                    logger.debug(f"Cache hit for {key}")
                    return result
                
                # Use lock to prevent multiple executions for same key
                with self.get_lock(key):
                    # Check cache again in case another thread filled it
                    result = self.get(key)
                    if result is not None:
                        return result
                    
                    # Execute function and cache result
                    result = func(*args, **kwargs)
                    return self.set(key, result, ttl)
            return wrapper
        return decorator

# Create global cache instance
cache = SimpleCache() 