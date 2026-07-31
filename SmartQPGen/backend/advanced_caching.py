"""
Advanced Caching System for SmartQPGen
=====================================
This module provides:
- Redis-based distributed caching
- Multi-level caching (memory + Redis)
- Cache invalidation strategies
- Performance monitoring
- Cache warming
"""

import json
import time
import hashlib
import pickle
from typing import Any, Optional, Dict, List
from functools import wraps
import logging

# Try to import Redis, fallback to in-memory if not available
try:
    import redis
    REDIS_AVAILABLE = True
except ImportError:
    REDIS_AVAILABLE = False
    print("Redis not available, using in-memory cache only")

logger = logging.getLogger(__name__)

class AdvancedCache:
    def __init__(self, redis_url=None, default_ttl=300):
        self.default_ttl = default_ttl
        self.memory_cache = {}
        self.cache_stats = {
            'hits': 0,
            'misses': 0,
            'sets': 0,
            'deletes': 0
        }
        
        # Initialize Redis if available
        if REDIS_AVAILABLE and redis_url:
            try:
                self.redis_client = redis.from_url(redis_url)
                self.redis_client.ping()  # Test connection
                self.redis_enabled = True
                logger.info("Redis cache initialized successfully")
            except Exception as e:
                logger.warning(f"Redis connection failed: {e}, using memory cache only")
                self.redis_enabled = False
        else:
            self.redis_enabled = False
            logger.info("Using in-memory cache only")
    
    def _generate_key(self, prefix: str, *args) -> str:
        """Generate a cache key from prefix and arguments"""
        key_data = f"{prefix}:{':'.join(str(arg) for arg in args)}"
        return hashlib.md5(key_data.encode()).hexdigest()
    
    def get(self, key: str) -> Optional[Any]:
        """Get value from cache (Redis first, then memory)"""
        # Try Redis first
        if self.redis_enabled:
            try:
                value = self.redis_client.get(key)
                if value:
                    self.cache_stats['hits'] += 1
                    return pickle.loads(value)
            except Exception as e:
                logger.warning(f"Redis get error: {e}")
        
        # Fallback to memory cache
        if key in self.memory_cache:
            data, timestamp, ttl = self.memory_cache[key]
            if time.time() - timestamp < ttl:
                self.cache_stats['hits'] += 1
                return data
            else:
                # Expired, remove it
                del self.memory_cache[key]
        
        self.cache_stats['misses'] += 1
        return None
    
    def set(self, key: str, value: Any, ttl: Optional[int] = None) -> bool:
        """Set value in cache (both Redis and memory)"""
        ttl = ttl or self.default_ttl
        success = True
        
        # Set in Redis
        if self.redis_enabled:
            try:
                serialized_value = pickle.dumps(value)
                self.redis_client.setex(key, ttl, serialized_value)
            except Exception as e:
                logger.warning(f"Redis set error: {e}")
                success = False
        
        # Set in memory cache
        self.memory_cache[key] = (value, time.time(), ttl)
        self.cache_stats['sets'] += 1
        
        return success
    
    def delete(self, key: str) -> bool:
        """Delete value from cache"""
        success = True
        
        # Delete from Redis
        if self.redis_enabled:
            try:
                self.redis_client.delete(key)
            except Exception as e:
                logger.warning(f"Redis delete error: {e}")
                success = False
        
        # Delete from memory cache
        if key in self.memory_cache:
            del self.memory_cache[key]
        
        self.cache_stats['deletes'] += 1
        return success
    
    def invalidate_pattern(self, pattern: str) -> int:
        """Invalidate all keys matching a pattern"""
        count = 0
        
        # Redis pattern invalidation
        if self.redis_enabled:
            try:
                keys = self.redis_client.keys(pattern)
                if keys:
                    count += self.redis_client.delete(*keys)
            except Exception as e:
                logger.warning(f"Redis pattern delete error: {e}")
        
        # Memory cache pattern invalidation
        keys_to_delete = [key for key in self.memory_cache.keys() if pattern.replace('*', '') in key]
        for key in keys_to_delete:
            del self.memory_cache[key]
            count += 1
        
        return count
    
    def get_stats(self) -> Dict:
        """Get cache statistics"""
        total_requests = self.cache_stats['hits'] + self.cache_stats['misses']
        hit_rate = (self.cache_stats['hits'] / total_requests * 100) if total_requests > 0 else 0
        
        return {
            **self.cache_stats,
            'hit_rate': round(hit_rate, 2),
            'memory_cache_size': len(self.memory_cache),
            'redis_enabled': self.redis_enabled
        }
    
    def clear_all(self):
        """Clear all caches"""
        if self.redis_enabled:
            try:
                self.redis_client.flushdb()
            except Exception as e:
                logger.warning(f"Redis flush error: {e}")
        
        self.memory_cache.clear()
        logger.info("All caches cleared")

# Global cache instance
cache = AdvancedCache()

def cached(ttl: int = 300, key_prefix: str = "default"):
    """Decorator for caching function results"""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            # Generate cache key
            cache_key = cache._generate_key(
                key_prefix, 
                func.__name__, 
                str(args), 
                str(sorted(kwargs.items()))
            )
            
            # Try to get from cache
            result = cache.get(cache_key)
            if result is not None:
                logger.debug(f"Cache hit for {func.__name__}")
                return result
            
            # Execute function and cache result
            logger.debug(f"Cache miss for {func.__name__}")
            result = func(*args, **kwargs)
            cache.set(cache_key, result, ttl)
            
            return result
        return wrapper
    return decorator

class CacheManager:
    """Advanced cache management for different data types"""
    
    @staticmethod
    def cache_user_questions(user_uid: str, questions: List[Dict], source_file: str = None):
        """Cache user questions with proper invalidation"""
        cache_key = f"user_questions:{user_uid}"
        if source_file:
            cache_key += f":{source_file}"
        
        cache.set(cache_key, questions, ttl=600)  # 10 minutes
        
        # Also cache individual question lookups
        for question in questions:
            q_key = f"question:{question.get('firestore_id', question.get('id'))}"
            cache.set(q_key, question, ttl=600)
    
    @staticmethod
    def get_cached_user_questions(user_uid: str, source_file: str = None):
        """Get cached user questions"""
        cache_key = f"user_questions:{user_uid}"
        if source_file:
            cache_key += f":{source_file}"
        
        return cache.get(cache_key)
    
    @staticmethod
    def invalidate_user_cache(user_uid: str):
        """Invalidate all cache entries for a user"""
        patterns = [
            f"user_questions:{user_uid}*",
            f"user_papers:{user_uid}*",
            f"user_banks:{user_uid}*"
        ]
        
        total_invalidated = 0
        for pattern in patterns:
            total_invalidated += cache.invalidate_pattern(pattern)
        
        logger.info(f"Invalidated {total_invalidated} cache entries for user {user_uid}")
        return total_invalidated
    
    @staticmethod
    def cache_generated_paper(paper_id: str, paper_data: Dict):
        """Cache generated question paper"""
        cache_key = f"generated_paper:{paper_id}"
        cache.set(cache_key, paper_data, ttl=1800)  # 30 minutes
    
    @staticmethod
    def get_cached_paper(paper_id: str):
        """Get cached question paper"""
        cache_key = f"generated_paper:{paper_id}"
        return cache.get(cache_key)
    
    @staticmethod
    def warm_cache_for_user(user_uid: str):
        """Pre-warm cache for frequently accessed user data"""
        # This would typically be called during user login
        # to pre-load commonly accessed data
        logger.info(f"Warming cache for user {user_uid}")
        
        # Example: Pre-load user's recent papers
        # This would be implemented based on your specific needs
        pass

# Performance monitoring
class CachePerformanceMonitor:
    def __init__(self):
        self.operation_times = []
        self.max_samples = 1000
    
    def record_operation(self, operation: str, duration: float):
        """Record cache operation performance"""
        self.operation_times.append({
            'operation': operation,
            'duration': duration,
            'timestamp': time.time()
        })
        
        # Keep only recent samples
        if len(self.operation_times) > self.max_samples:
            self.operation_times = self.operation_times[-self.max_samples:]
    
    def get_performance_stats(self) -> Dict:
        """Get performance statistics"""
        if not self.operation_times:
            return {}
        
        # Calculate average times by operation
        operation_stats = {}
        for record in self.operation_times:
            op = record['operation']
            if op not in operation_stats:
                operation_stats[op] = []
            operation_stats[op].append(record['duration'])
        
        # Calculate averages
        avg_times = {}
        for op, times in operation_stats.items():
            avg_times[op] = {
                'avg_duration': sum(times) / len(times),
                'count': len(times),
                'min_duration': min(times),
                'max_duration': max(times)
            }
        
        return avg_times

# Global performance monitor
performance_monitor = CachePerformanceMonitor()

def monitor_cache_performance(operation_name: str):
    """Decorator to monitor cache operation performance"""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            start_time = time.time()
            result = func(*args, **kwargs)
            duration = time.time() - start_time
            
            performance_monitor.record_operation(operation_name, duration)
            return result
        return wrapper
    return decorator
