"""
Simple in-memory cache for frequently accessed data
Can be upgraded to Redis for production
"""
from functools import wraps
from datetime import datetime, timedelta
import hashlib
import json

# Simple in-memory cache
_cache = {}
_cache_timestamps = {}

# Default TTL (Time To Live) in seconds
DEFAULT_TTL = 900  # 15 minutes (data only changes on import; cache is invalidated then)


def get_cache_key(*args, **kwargs):
    """Generate cache key from function arguments"""
    key_data = {
        'args': args,
        'kwargs': sorted(kwargs.items())
    }
    key_string = json.dumps(key_data, sort_keys=True, default=str)
    return hashlib.md5(key_string.encode()).hexdigest()


def cache_result(ttl=DEFAULT_TTL):
    """
    Decorator to cache function results
    
    Args:
        ttl: Time to live in seconds (default: 5 minutes)
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            # Generate cache key
            cache_key = f"{func.__name__}:{get_cache_key(*args, **kwargs)}"
            
            # Check if cached and not expired
            if cache_key in _cache:
                timestamp = _cache_timestamps.get(cache_key)
                if timestamp and datetime.now() - timestamp < timedelta(seconds=ttl):
                    return _cache[cache_key]
            
            # Execute function and cache result
            result = func(*args, **kwargs)
            _cache[cache_key] = result
            _cache_timestamps[cache_key] = datetime.now()
            
            return result
        return wrapper
    return decorator


def clear_cache(pattern=None):
    """
    Clear cache entries
    
    Args:
        pattern: Optional pattern to match cache keys (e.g., 'dashboard:*')
    """
    if pattern:
        keys_to_remove = [k for k in _cache.keys() if pattern in k]
        for key in keys_to_remove:
            _cache.pop(key, None)
            _cache_timestamps.pop(key, None)
    else:
        _cache.clear()
        _cache_timestamps.clear()


def clear_dashboard_cache():
    """Clear all cached dashboard payloads (every cohort/period) plus the cross-cohort
    overlap cache. Call this whenever registration data changes (import / UTS sync)."""
    clear_cache('_get_dashboard_data_cached')
    clear_cache('_get_prior_cohort_overlap_cached')
    clear_cache('_get_region_breakdown_cached')


def get_cache_stats():
    """Get cache statistics"""
    return {
        'total_entries': len(_cache),
        'cache_keys': list(_cache.keys())
    }
