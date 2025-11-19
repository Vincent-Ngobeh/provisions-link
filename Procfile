web: cd backend && daphne -b 0.0.0.0 -p $PORT provisions_link.asgi:application
worker: cd backend && celery -A provisions_link worker --loglevel=info --concurrency=2
beat: cd backend && celery -A provisions_link beat --loglevel=info