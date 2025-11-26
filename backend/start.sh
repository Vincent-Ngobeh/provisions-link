#!/bin/bash
set -e

echo "=== STARTUP SCRIPT ==="
echo "PORT: $PORT"
echo "DATABASE_URL set: $([ -n "$DATABASE_URL" ] && echo 'yes' || echo 'no')"
echo "SECRET_KEY set: $([ -n "$SECRET_KEY" ] && echo 'yes' || echo 'no')"
echo "REDIS_URL set: $([ -n "$REDIS_URL" ] && echo 'yes' || echo 'no')"
echo "AWS_ACCESS_KEY_ID set: $([ -n "$AWS_ACCESS_KEY_ID" ] && echo 'yes' || echo 'no')"
echo "======================"

# Create staticfiles directory if it doesn't exist
mkdir -p /app/staticfiles

echo "Running migrations..."
python manage.py migrate

echo "Collecting static files..."
python manage.py collectstatic --noinput --clear 2>&1 || echo "Warning: collectstatic had issues but continuing..."

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
else:
    print('Redis connection: SKIPPED (no REDIS_URL)')
"

echo "Testing database connection..."
python -c "
import os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'provisions_link.settings.production')
import django
django.setup()
from django.db import connection
try:
    with connection.cursor() as cursor:
        cursor.execute('SELECT 1')
    print('Database connection: SUCCESS')
except Exception as e:
    print(f'Database connection: FAILED - {e}')
"

echo "Starting uvicorn on port ${PORT:-8000}..."

exec uvicorn provisions_link.asgi:application \
    --host 0.0.0.0 \
    --port ${PORT:-8000} \
    --workers 1 \
    --log-level info \
    --access-log \
    --proxy-headers \
    --forwarded-allow-ips='*'
