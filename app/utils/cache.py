import os
import time
import threading
import logging
from typing import Dict, Any, Optional, Tuple, List, Callable, Generic, TypeVar, Union
from datetime import datetime
from dotenv import load_dotenv
import json

# Thiết lập logging
logger = logging.getLogger(__name__)

# Load biến môi trường
load_dotenv()

# Cấu hình cache từ biến môi trường
DEFAULT_CACHE_TTL = int(os.getenv("CACHE_TTL_SECONDS", "300"))  # Mặc định 5 phút
DEFAULT_CACHE_CLEANUP_INTERVAL = int(os.getenv("CACHE_CLEANUP_INTERVAL", "60"))  # Mặc định 1 phút
DEFAULT_CACHE_MAX_SIZE = int(os.getenv("CACHE_MAX_SIZE", "1000"))  # Mặc định 1000 phần tử

# Generic type để có thể sử dụng cho nhiều loại giá trị khác nhau
T = TypeVar('T')

# Cấu trúc cho một phần tử trong cache
class CacheItem(Generic[T]):
    def __init__(self, value: T, ttl: int = DEFAULT_CACHE_TTL):
        self.value = value
        self.expire_at = time.time() + ttl
        self.last_accessed = time.time()
    
    def is_expired(self) -> bool:
        """Kiểm tra xem item có hết hạn chưa"""
        return time.time() > self.expire_at
    
    def touch(self) -> None:
        """Cập nhật thời gian truy cập lần cuối"""
        self.last_accessed = time.time()
    
    def extend(self, ttl: int = DEFAULT_CACHE_TTL) -> None:
        """Gia hạn thời gian sống của item"""
        self.expire_at = time.time() + ttl

# Lớp cache chính
class InMemoryCache:
    def __init__(
        self, 
        ttl: int = DEFAULT_CACHE_TTL,
        cleanup_interval: int = DEFAULT_CACHE_CLEANUP_INTERVAL,
        max_size: int = DEFAULT_CACHE_MAX_SIZE
    ):
        self.cache: Dict[str, CacheItem] = {}
        self.ttl = ttl
        self.cleanup_interval = cleanup_interval
        self.max_size = max_size
        self.lock = threading.RLock()  # Sử dụng RLock để tránh deadlock
        
        # Khởi động thread dọn dẹp cache định kỳ (active expiration)
        self.cleanup_thread = threading.Thread(target=self._cleanup_task, daemon=True)
        self.cleanup_thread.start()
    
    def set(self, key: str, value: Any, ttl: Optional[int] = None) -> None:
        """Lưu một giá trị vào cache"""
        with self.lock:
            ttl_value = ttl if ttl is not None else self.ttl
            
            # Nếu cache đã đầy, xóa bớt các item ít được truy cập nhất
            if len(self.cache) >= self.max_size and key not in self.cache:
                self._evict_lru_items()
                
            self.cache[key] = CacheItem(value, ttl_value)
            logger.debug(f"Cache set: {key} (expires in {ttl_value}s)")
    
    def get(self, key: str, default: Any = None) -> Any:
        """
        Lấy giá trị từ cache. Nếu key không tồn tại hoặc đã hết hạn, trả về giá trị mặc định.
        Áp dụng lazy expiration: kiểm tra và xóa các item hết hạn khi truy cập.
        """
        with self.lock:
            item = self.cache.get(key)
            
            # Nếu không tìm thấy key hoặc item đã hết hạn
            if item is None or item.is_expired():
                # Nếu item tồn tại nhưng đã hết hạn, xóa nó (lazy expiration)
                if item is not None:
                    logger.debug(f"Cache miss (expired): {key}")
                    del self.cache[key]
                else:
                    logger.debug(f"Cache miss (not found): {key}")
                return default
            
            # Cập nhật thời gian truy cập
            item.touch()
            logger.debug(f"Cache hit: {key}")
            return item.value
    
    def delete(self, key: str) -> bool:
        """Xóa một key khỏi cache"""
        with self.lock:
            if key in self.cache:
                del self.cache[key]
                logger.debug(f"Cache delete: {key}")
                return True
            return False
    
    def clear(self) -> None:
        """Xóa tất cả dữ liệu trong cache"""
        with self.lock:
            self.cache.clear()
            logger.debug("Cache cleared")
    
    def get_or_set(self, key: str, callback: Callable[[], T], ttl: Optional[int] = None) -> T:
        """
        Lấy giá trị từ cache nếu tồn tại, nếu không thì gọi callback để lấy giá trị
        và lưu vào cache trước khi trả về.
        """
        with self.lock:
            value = self.get(key)
            if value is None:
                value = callback()
                self.set(key, value, ttl)
            return value
    
    def _cleanup_task(self) -> None:
        """Thread để dọn dẹp các item đã hết hạn (active expiration)"""
        while True:
            time.sleep(self.cleanup_interval)
            try:
                self._remove_expired_items()
            except Exception as e:
                logger.error(f"Error in cache cleanup task: {e}")
    
    def _remove_expired_items(self) -> None:
        """Xóa tất cả các item đã hết hạn trong cache"""
        with self.lock:
            now = time.time()
            expired_keys = [k for k, v in self.cache.items() if v.is_expired()]
            for key in expired_keys:
                del self.cache[key]
            
            if expired_keys:
                logger.debug(f"Cleaned up {len(expired_keys)} expired cache items")
    
    def _evict_lru_items(self, count: int = 1) -> None:
        """Xóa bỏ các item ít được truy cập nhất khi cache đầy"""
        items = sorted(self.cache.items(), key=lambda x: x[1].last_accessed)
        for i in range(min(count, len(items))):
            del self.cache[items[i][0]]
        logger.debug(f"Evicted {min(count, len(items))} least recently used items from cache")
    
    def stats(self) -> Dict[str, Any]:
        """Trả về thống kê về cache"""
        with self.lock:
            now = time.time()
            total_items = len(self.cache)
            expired_items = sum(1 for item in self.cache.values() if item.is_expired())
            memory_usage = self._estimate_memory_usage()
            return {
                "total_items": total_items,
                "expired_items": expired_items,
                "active_items": total_items - expired_items,
                "memory_usage_bytes": memory_usage,
                "memory_usage_mb": memory_usage / (1024 * 1024),
                "max_size": self.max_size
            }
    
    def _estimate_memory_usage(self) -> int:
        """Ước tính dung lượng bộ nhớ của cache (gần đúng)"""
        # Ước tính dựa trên kích thước của các key và giá trị
        cache_size = sum(len(k) for k in self.cache.keys())
        for item in self.cache.values():
            try:
                # Ước tính kích thước của value (gần đúng)
                if isinstance(item.value, (str, bytes)):
                    cache_size += len(item.value)
                elif isinstance(item.value, (dict, list)):
                    cache_size += len(json.dumps(item.value))
                else:
                    # Giá trị mặc định cho các loại dữ liệu khác
                    cache_size += 100
            except:
                cache_size += 100
        
        return cache_size

# Singleton instance
_cache_instance = None

def get_cache() -> InMemoryCache:
    """Trả về instance singleton của InMemoryCache"""
    global _cache_instance
    if _cache_instance is None:
        _cache_instance = InMemoryCache()
    return _cache_instance 