# Performance Optimization Guide

This document outlines the optimizations implemented to handle large datasets (200k-300k records).

## Database Optimizations

### 1. Database Indexes
**File:** `server/migrations/add_indexes.py`

Run this script to add indexes on frequently queried columns:
```bash
python server/migrations/add_indexes.py
```

**Indexes Added:**
- Email (unique constraint)
- Organization name
- Domain
- Country, State, City
- Created at, Registered at
- Gender, Class stream, Designation, Occupation
- Composite indexes for common query patterns
- Full-text search indexes (trigram) for name and email search

**Note:** For full-text search indexes, you may need to enable the `pg_trgm` extension:
```sql
CREATE EXTENSION IF NOT EXISTS pg_trgm;
```

### 2. Connection Pooling
**File:** `server/config.py`

Connection pooling is configured with:
- Pool size: 10 connections (configurable via `DB_POOL_SIZE`)
- Max overflow: 20 connections (configurable via `DB_MAX_OVERFLOW`)
- Pool pre-ping: Enabled (verifies connections before use)
- Pool recycle: 3600 seconds (configurable via `DB_POOL_RECYCLE`)

### 3. Query Optimizations

#### Dashboard Queries
- Age calculations moved to SQL using `EXTRACT` and `AGE` functions
- Aggregations use efficient `GROUP BY` with indexes
- Date filtering uses indexed `created_at` and `registered_at` columns
- Limited result sets (top 10 for most charts)

#### Profile Queries
- Efficient count queries using subqueries
- Pagination with proper ordering
- Filter options cached for 10 minutes
- Limited filter options to top 1000 results

## Import Optimizations

### Batch Processing
**File:** `server/utils/excel_parser.py`

- Batch size: 1000 records per commit
- Bulk insert using `bulk_insert_mappings` for new records
- Pre-fetches existing emails in a set for O(1) lookup
- Processes updates in batches

**Performance:** Can handle 200k+ records efficiently with batch commits.

## Caching

### In-Memory Cache
**File:** `server/utils/cache.py`

Simple in-memory cache for frequently accessed data:
- Dashboard summary: 5 minutes TTL
- Filter options: 10 minutes TTL
- Cache can be cleared programmatically

**Future:** Can be upgraded to Redis for distributed caching.

## Frontend Optimizations

### Search Debouncing
**File:** `server/static/js/profiles.js`

- Search input debounced to 500ms
- Prevents excessive API calls while typing

### Pagination
- Default: 20 records per page
- Maximum: 100 records per page
- Efficient server-side pagination

## Configuration

### Environment Variables

Add these to your `.env` file for fine-tuning:

```env
# Database Connection Pooling
DB_POOL_SIZE=10
DB_MAX_OVERFLOW=20
DB_POOL_RECYCLE=3600
DB_ECHO=False  # Set to True for SQL query logging
```

## Performance Benchmarks

### Expected Performance (with indexes):

- **Dashboard Summary:** < 500ms for 300k records
- **Dashboard Charts:** < 1s for 300k records
- **Profile List (paginated):** < 200ms per page
- **Filter Options:** < 100ms (cached)
- **Data Import:** ~1000 records/second

## Monitoring

### Database Query Performance

To monitor slow queries, enable query logging:
```env
DB_ECHO=True
```

### Cache Statistics

Check cache statistics programmatically:
```python
from server.utils.cache import get_cache_stats
stats = get_cache_stats()
```

## Next Steps for Further Optimization

1. **Redis Caching:** Replace in-memory cache with Redis for distributed systems
2. **Read Replicas:** Use read replicas for dashboard queries
3. **Materialized Views:** Create materialized views for complex aggregations
4. **Partitioning:** Partition large tables by date if needed
5. **Full-Text Search:** Use PostgreSQL full-text search for better search performance
6. **CDN:** Use CDN for static assets
7. **Compression:** Enable gzip compression for API responses

## Troubleshooting

### Slow Queries

1. Check if indexes are created:
   ```bash
   python server/migrations/add_indexes.py
   ```

2. Verify connection pool settings in `.env`

3. Check database query logs (if `DB_ECHO=True`)

### Import Performance

1. Ensure batch processing is working (check logs)
2. Verify database connection pool is sufficient
3. Consider increasing `BATCH_SIZE` in `excel_parser.py` if needed

### Cache Issues

1. Clear cache if data seems stale:
   ```python
   from server.utils.cache import clear_cache
   clear_cache('dashboard:*')  # Clear dashboard cache
   clear_cache()  # Clear all cache
   ```
