#!/bin/bash
set -e

echo "=== CELERY BEAT STARTUP ==="
echo "REDIS_URL set: $([ -n "$REDIS_URL" ] && echo 'yes' || echo 'no')"
echo "DATABASE_URL set: $([ -n "$DATABASE_URL" ] && echo 'yes' || echo 'no')"
echo "==========================="

# Test Redis connection
echo "Testing Redis connection..."
python -c "
import os
redis_url = os.environ.get('REDIS_URL')
if redis_url:
    try:
        import redis
        r = redis.from_url(redis_url)
        r.ping()
        print('Redis connection: SUCCESS')
    except Exception as e:
        print(f'Redis connection: FAILED - {e}')
        exit(1)
else:
    print('Redis connection: SKIPPED (no REDIS_URL)')
    exit(1)
"

echo "Starting Celery beat scheduler..."
exec celery -A provisions_link beat \
    --loglevel=info