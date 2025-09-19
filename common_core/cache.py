"""
TTL (Time To Live) Cache implementation for IPAM API Gateway

This module provides an in-memory cache with automatic expiration
for caching IPAM query results to reduce backend load and improve response times.
"""

import time
import threading
import logging
from typing import Any, Optional, Dict, Set

logger = logging.getLogger(__name__)


class TTLCache:
    """
    Thread-safe in-memory cache with TTL (Time To Live) support.
    
    Features:
    - Thread-safe operations using locks
    - Automatic expiration of entries based on TTL
    - Manual and automatic cleanup of expired entries
    - Simple key-value storage with timestamp tracking
    """
    
    def __init__(self):
        """Initialize empty cache with thread safety."""
        self._cache: Dict[str, Any] = {}
        self._timestamps: Dict[str, float] = {}
        self._lock = threading.Lock()
        logger.debug("TTLCache initialized")
    
    def get(self, key: str, ttl_seconds: int = 7200) -> Optional[Any]:
        """
        Retrieve an item from cache if it hasn't expired.
        
        Args:
            key: Cache key to retrieve
            ttl_seconds: Time to live in seconds (default: 7200 = 2 hours)
            
        Returns:
            Cached value if not expired, None otherwise
        """
        with self._lock:
            if key not in self._cache:
                logger.debug(f"Cache miss: key '{key}' not found")
                return None
            
            # Check if expired
            creation_time = self._timestamps.get(key, 0)
            current_time = time.time()
            age_seconds = current_time - creation_time
            
            if age_seconds > ttl_seconds:
                # Expired - remove from cache
                self._remove_key_unsafe(key)
                logger.debug(f"Cache expired: key '{key}' (age: {age_seconds:.1f}s, ttl: {ttl_seconds}s)")
                return None
            
            value = self._cache[key]
            logger.debug(f"Cache hit: key '{key}' (age: {age_seconds:.1f}s, ttl: {ttl_seconds}s)")
            return value
    
    def set(self, key: str, value: Any) -> None:
        """
        Store an item in cache with current timestamp.
        
        Args:
            key: Cache key to store under
            value: Value to cache
        """
        with self._lock:
            self._cache[key] = value
            self._timestamps[key] = time.time()
            logger.debug(f"Cache set: key '{key}' stored")
    
    def delete(self, key: str) -> bool:
        """
        Remove a specific key from cache.
        
        Args:
            key: Cache key to remove
            
        Returns:
            True if key was found and removed, False otherwise
        """
        with self._lock:
            if key in self._cache:
                self._remove_key_unsafe(key)
                logger.debug(f"Cache delete: key '{key}' removed")
                return True
            return False
    
    def clear_expired(self, ttl_seconds: int = 7200) -> int:
        """
        Remove all expired entries from cache.
        
        Args:
            ttl_seconds: TTL threshold for expiration (default: 7200 = 2 hours)
            
        Returns:
            Number of expired entries removed
        """
        with self._lock:
            current_time = time.time()
            expired_keys: Set[str] = set()
            
            for key, creation_time in self._timestamps.items():
                age_seconds = current_time - creation_time
                if age_seconds > ttl_seconds:
                    expired_keys.add(key)
            
            # Remove expired keys
            for key in expired_keys:
                self._remove_key_unsafe(key)
            
            if expired_keys:
                logger.info(f"Cache cleanup: removed {len(expired_keys)} expired entries")
            
            return len(expired_keys)
    
    def clear(self) -> None:
        """Clear entire cache."""
        with self._lock:
            cache_size = len(self._cache)
            self._cache.clear()
            self._timestamps.clear()
            if cache_size > 0:
                logger.info(f"Cache cleared: removed {cache_size} entries")
    
    def size(self) -> int:
        """
        Get current cache size.
        
        Returns:
            Number of items in cache
        """
        with self._lock:
            return len(self._cache)
    
    def keys(self) -> Set[str]:
        """
        Get all cache keys.
        
        Returns:
            Set of all cache keys
        """
        with self._lock:
            return set(self._cache.keys())
    
    def stats(self, ttl_seconds: int = 7200) -> Dict[str, Any]:
        """
        Get cache statistics.
        
        Args:
            ttl_seconds: TTL to use for expiration calculations
            
        Returns:
            Dictionary with cache statistics
        """
        with self._lock:
            current_time = time.time()
            total_entries = len(self._cache)
            expired_count = 0
            
            if total_entries > 0:
                for creation_time in self._timestamps.values():
                    age_seconds = current_time - creation_time
                    if age_seconds > ttl_seconds:
                        expired_count += 1
            
            return {
                "total_entries": total_entries,
                "valid_entries": total_entries - expired_count,
                "expired_entries": expired_count,
                "ttl_seconds": ttl_seconds
            }
    
    def _remove_key_unsafe(self, key: str) -> None:
        """
        Remove key from both cache and timestamps (unsafe - no locking).
        
        Args:
            key: Key to remove
        """
        self._cache.pop(key, None)
        self._timestamps.pop(key, None)


# Global cache instance for the application
# This allows sharing cache across all endpoints and handlers
_global_cache = TTLCache()


def get_cache() -> TTLCache:
    """
    Get the global cache instance.
    
    Returns:
        Global TTLCache instance
    """
    return _global_cache


def cache_get(key: str, ttl_seconds: int = 7200) -> Optional[Any]:
    """
    Convenience function to get from global cache.
    
    Args:
        key: Cache key
        ttl_seconds: TTL in seconds (default: 2 hours)
        
    Returns:
        Cached value or None
    """
    return _global_cache.get(key, ttl_seconds)


def cache_set(key: str, value: Any) -> None:
    """
    Convenience function to set in global cache.
    
    Args:
        key: Cache key
        value: Value to cache
    """
    _global_cache.set(key, value)


def cache_delete(key: str) -> bool:
    """
    Convenience function to delete from global cache.
    
    Args:
        key: Cache key to delete
        
    Returns:
        True if deleted, False if not found
    """
    return _global_cache.delete(key)


def cache_clear_expired(ttl_seconds: int = 7200) -> int:
    """
    Convenience function to clear expired entries from global cache.
    
    Args:
        ttl_seconds: TTL threshold
        
    Returns:
        Number of expired entries removed
    """
    return _global_cache.clear_expired(ttl_seconds)


def cache_stats(ttl_seconds: int = 7200) -> Dict[str, Any]:
    """
    Convenience function to get global cache statistics.
    
    Args:
        ttl_seconds: TTL for calculations
        
    Returns:
        Cache statistics dictionary
    """
    return _global_cache.stats(ttl_seconds)