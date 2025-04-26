import logging
import time
import uuid
import threading
import os
from functools import wraps
from datetime import datetime, timedelta
import pytz
from typing import Callable, Any, Dict, Optional, List, Tuple, Set
import gc
import heapq

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

class CacheStrategy:
    """Cache loading strategy enumeration"""
    LAZY = "lazy"  # Only load items into cache when requested
    EAGER = "eager"  # Preload items into cache at initialization
    MIXED = "mixed"  # Preload high-priority items, lazy load others

class CacheItem:
    """Represents an item in the cache with metadata"""
    def __init__(self, key: str, value: Any, ttl: int = 300, priority: int = 1):
        self.key = key
        self.value = value
        self.expiry = datetime.now() + timedelta(seconds=ttl)
        self.priority = priority  # Higher number = higher priority
        self.access_count = 0     # Track number of accesses
        self.last_accessed = datetime.now()
        
    def is_expired(self) -> bool:
        """Check if the item is expired"""
        return datetime.now() > self.expiry
    
    def touch(self):
        """Update last accessed time and access count"""
        self.last_accessed = datetime.now()
        self.access_count += 1
        
    def __lt__(self, other):
        """For heap comparisons - lower priority items are evicted first"""
        # First compare priority
        if self.priority != other.priority:
            return self.priority < other.priority
        # Then compare access frequency (less frequently accessed items are evicted first)
        if self.access_count != other.access_count:
            return self.access_count < other.access_count
        # Finally compare last access time (oldest accessed first)
        return self.last_accessed < other.last_accessed

    def get_size(self) -> int:
        """Approximate memory size of the cache item in bytes"""
        try:
            import sys
            return sys.getsizeof(self.value) + sys.getsizeof(self.key) + 64  # Additional overhead
        except:
            # Default estimate if we can't get the size
            return 1024

# Enhanced in-memory cache implementation
class EnhancedCache:
    def __init__(self, 
                 strategy: str = "lazy", 
                 max_items: int = 10000, 
                 max_size_mb: int = 100,
                 cleanup_interval: int = 60,
                 stats_enabled: bool = True):
        """
        Initialize enhanced cache with configurable strategy.
        
        Args:
            strategy: Cache loading strategy (lazy, eager, mixed)
            max_items: Maximum number of items to store in cache
            max_size_mb: Maximum size of cache in MB
            cleanup_interval: Interval in seconds to run cleanup
            stats_enabled: Whether to collect cache statistics
        """
        self._cache: Dict[str, CacheItem] = {}
        self._namespace_cache: Dict[str, Set[str]] = {}  # Tracking keys by namespace
        self._strategy = strategy
        self._max_items = max_items
        self._max_size_bytes = max_size_mb * 1024 * 1024
        self._current_size_bytes = 0
        self._stats_enabled = stats_enabled
        
        # Statistics
        self._hits = 0
        self._misses = 0
        self._evictions = 0
        self._total_get_time = 0
        self._total_set_time = 0
        
        # Setup cleanup thread
        self._last_cleanup = datetime.now()
        self._cleanup_interval = cleanup_interval
        self._lock = threading.RLock()
        
        if cleanup_interval > 0:
            self._start_cleanup_thread(cleanup_interval)
        
        logger.info(f"Enhanced cache initialized with strategy={strategy}, max_items={max_items}, max_size={max_size_mb}MB")
    
    def _start_cleanup_thread(self, interval: int):
        """Start background thread for periodic cleanup"""
        def cleanup_worker():
            while True:
                time.sleep(interval)
                try:
                    self.cleanup()
                except Exception as e:
                    logger.error(f"Error in cache cleanup: {e}")
        
        thread = threading.Thread(target=cleanup_worker, daemon=True)
        thread.start()
        logger.info(f"Cache cleanup thread started with interval {interval}s")
    
    def get(self, key: str, namespace: str = None) -> Optional[Any]:
        """Get value from cache if it exists and hasn't expired"""
        if self._stats_enabled:
            start_time = time.time()
            
        # Use namespaced key if namespace is provided
        cache_key = f"{namespace}:{key}" if namespace else key
        
        with self._lock:
            cache_item = self._cache.get(cache_key)
            
            if cache_item:
                if cache_item.is_expired():
                    # Clean up expired key
                    self._remove_item(cache_key, namespace)
                    if self._stats_enabled:
                        self._misses += 1
                    value = None
                else:
                    # Update access metadata
                    cache_item.touch()
                    if self._stats_enabled:
                        self._hits += 1
                    value = cache_item.value
            else:
                if self._stats_enabled:
                    self._misses += 1
                value = None
                
            if self._stats_enabled:
                self._total_get_time += time.time() - start_time
                
            return value
    
    def set(self, key: str, value: Any, ttl: int = 300, priority: int = 1, namespace: str = None) -> None:
        """Set a value in the cache with TTL in seconds"""
        if self._stats_enabled:
            start_time = time.time()
            
        # Use namespaced key if namespace is provided
        cache_key = f"{namespace}:{key}" if namespace else key
            
        with self._lock:
            # Create cache item
            cache_item = CacheItem(cache_key, value, ttl, priority)
            item_size = cache_item.get_size()
            
            # Check if we need to make room
            if (len(self._cache) >= self._max_items or 
                self._current_size_bytes + item_size > self._max_size_bytes):
                self._evict_items(item_size)
            
            # Update size tracking
            if cache_key in self._cache:
                # If replacing, subtract old size first
                self._current_size_bytes -= self._cache[cache_key].get_size()
            self._current_size_bytes += item_size
            
            # Store the item
            self._cache[cache_key] = cache_item
            
            # Update namespace tracking
            if namespace:
                if namespace not in self._namespace_cache:
                    self._namespace_cache[namespace] = set()
                self._namespace_cache[namespace].add(cache_key)
                
            if self._stats_enabled:
                self._total_set_time += time.time() - start_time
    
    def delete(self, key: str, namespace: str = None) -> None:
        """Delete a key from the cache"""
        # Use namespaced key if namespace is provided
        cache_key = f"{namespace}:{key}" if namespace else key
        
        with self._lock:
            self._remove_item(cache_key, namespace)
    
    def _remove_item(self, key: str, namespace: str = None):
        """Internal method to remove an item and update tracking"""
        if key in self._cache:
            # Update size tracking
            self._current_size_bytes -= self._cache[key].get_size()
            # Remove from cache
            del self._cache[key]
            
            # Update namespace tracking
            if namespace and namespace in self._namespace_cache:
                if key in self._namespace_cache[namespace]:
                    self._namespace_cache[namespace].remove(key)
                # Cleanup empty sets
                if not self._namespace_cache[namespace]:
                    del self._namespace_cache[namespace]
    
    def _evict_items(self, needed_space: int = 0) -> None:
        """Evict items to make room in the cache"""
        if not self._cache:
            return
            
        with self._lock:
            # Convert cache items to a list for sorting
            items = list(self._cache.values())
            
            # Sort by priority, access count, and last accessed time
            items.sort()  # Uses the __lt__ method of CacheItem
            
            # Evict items until we have enough space
            space_freed = 0
            evicted_count = 0
            
            for item in items:
                # Stop if we've made enough room
                if (len(self._cache) - evicted_count <= self._max_items * 0.9 and
                    (space_freed >= needed_space or 
                     self._current_size_bytes - space_freed <= self._max_size_bytes * 0.9)):
                    break
                    
                # Skip high priority items unless absolutely necessary
                if item.priority > 9 and evicted_count < len(items) // 2:
                    continue
                    
                # Evict this item
                item_size = item.get_size()
                namespace = item.key.split(':', 1)[0] if ':' in item.key else None
                self._remove_item(item.key, namespace)
                
                space_freed += item_size
                evicted_count += 1
                if self._stats_enabled:
                    self._evictions += 1
            
            logger.info(f"Cache eviction: removed {evicted_count} items, freed {space_freed / 1024:.2f}KB")
    
    def clear(self, namespace: str = None) -> None:
        """
        Clear the cache or a specific namespace
        """
        with self._lock:
            if namespace:
                # Clear only keys in the specified namespace
                if namespace in self._namespace_cache:
                    keys_to_remove = list(self._namespace_cache[namespace])
                    for key in keys_to_remove:
                        self._remove_item(key, namespace)
                    # The namespace should be auto-cleaned in _remove_item
            else:
                # Clear the entire cache
                self._cache.clear()
                self._namespace_cache.clear()
                self._current_size_bytes = 0
                
            logger.info(f"Cache cleared{' for namespace ' + namespace if namespace else ''}")
    
    def cleanup(self) -> None:
        """Remove expired items and run garbage collection if needed"""
        with self._lock:
            now = datetime.now()
            # Only run if it's been at least cleanup_interval since last cleanup
            if (now - self._last_cleanup).total_seconds() < self._cleanup_interval:
                return
                
            # Find expired items
            expired_keys = []
            for key, item in self._cache.items():
                if item.is_expired():
                    expired_keys.append((key, key.split(':', 1)[0] if ':' in key else None))
            
            # Remove expired items
            for key, namespace in expired_keys:
                self._remove_item(key, namespace)
            
            # Update last cleanup time
            self._last_cleanup = now
            
            # Run garbage collection if we removed several items
            if len(expired_keys) > 100:
                gc.collect()
                
            logger.info(f"Cache cleanup: removed {len(expired_keys)} expired items")
    
    def get_stats(self) -> Dict:
        """Get cache statistics"""
        with self._lock:
            if not self._stats_enabled:
                return {"stats_enabled": False}
                
            # Calculate hit rate
            total_requests = self._hits + self._misses
            hit_rate = (self._hits / total_requests) * 100 if total_requests > 0 else 0
            
            # Calculate average times
            avg_get_time = (self._total_get_time / total_requests) * 1000 if total_requests > 0 else 0
            avg_set_time = (self._total_set_time / self._evictions) * 1000 if self._evictions > 0 else 0
            
            return {
                "stats_enabled": True,
                "item_count": len(self._cache),
                "max_items": self._max_items,
                "size_bytes": self._current_size_bytes,
                "max_size_bytes": self._max_size_bytes,
                "hits": self._hits,
                "misses": self._misses,
                "hit_rate_percent": round(hit_rate, 2),
                "evictions": self._evictions,
                "avg_get_time_ms": round(avg_get_time, 3),
                "avg_set_time_ms": round(avg_set_time, 3),
                "namespace_count": len(self._namespace_cache),
                "namespaces": list(self._namespace_cache.keys())
            }
    
    def preload(self, items: List[Tuple[str, Any, int, int]], namespace: str = None) -> None:
        """
        Preload a list of items into the cache
        
        Args:
            items: List of (key, value, ttl, priority) tuples
            namespace: Optional namespace for all items
        """
        for key, value, ttl, priority in items:
            self.set(key, value, ttl, priority, namespace)
        
        logger.info(f"Preloaded {len(items)} items into cache{' namespace ' + namespace if namespace else ''}")
    
    def get_or_load(self, key: str, loader_func: Callable[[], Any], 
                   ttl: int = 300, priority: int = 1, namespace: str = None) -> Any:
        """
        Get from cache or load using the provided function
        
        Args:
            key: Cache key
            loader_func: Function to call if cache miss occurs
            ttl: TTL in seconds
            priority: Item priority
            namespace: Optional namespace
            
        Returns:
            Cached or freshly loaded value
        """
        # Try to get from cache first
        value = self.get(key, namespace)
        
        # If not in cache, load it
        if value is None:
            value = loader_func()
            # Only cache if we got a valid value
            if value is not None:
                self.set(key, value, ttl, priority, namespace)
                
        return value

# Load cache configuration from environment variables
CACHE_STRATEGY = os.getenv("CACHE_STRATEGY", "mixed")
CACHE_MAX_ITEMS = int(os.getenv("CACHE_MAX_ITEMS", "10000"))
CACHE_MAX_SIZE_MB = int(os.getenv("CACHE_MAX_SIZE_MB", "100"))
CACHE_CLEANUP_INTERVAL = int(os.getenv("CACHE_CLEANUP_INTERVAL", "60"))
CACHE_STATS_ENABLED = os.getenv("CACHE_STATS_ENABLED", "true").lower() in ("true", "1", "yes")

# Initialize the enhanced cache
cache = EnhancedCache(
    strategy=CACHE_STRATEGY,
    max_items=CACHE_MAX_ITEMS,
    max_size_mb=CACHE_MAX_SIZE_MB,
    cleanup_interval=CACHE_CLEANUP_INTERVAL,
    stats_enabled=CACHE_STATS_ENABLED
)

# Backward compatibility for SimpleCache - for a transition period
class SimpleCache:
    def __init__(self):
        """Legacy SimpleCache implementation that uses EnhancedCache underneath"""
        logger.warning("SimpleCache is deprecated, please use EnhancedCache directly")
        
    def get(self, key: str) -> Optional[Any]:
        """Get value from cache if it exists and hasn't expired"""
        return cache.get(key)
    
    def set(self, key: str, value: Any, ttl: int = 300) -> None:
        """Set a value in the cache with TTL in seconds"""
        cache.set(key, value, ttl)
    
    def delete(self, key: str) -> None:
        """Delete a key from the cache"""
        cache.delete(key)
    
    def clear(self) -> None:
        """Clear the entire cache"""
        cache.clear()

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