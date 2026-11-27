#!/bin/sh
set -eu
python - <<'PY'
import os
import time
import psycopg
for attempt in range(60):
    try:
        with psycopg.connect(host=os.environ["POSTGRES_HOST"], user=os.environ["POSTGRES_USER"],
                             dbname=os.environ["POSTGRES_DB"], password=os.environ["POSTGRES_PASSWORD"],
                             connect_timeout=2):
            break
    except psycopg.OperationalError:
        if attempt == 59:
            raise
        time.sleep(1)
PY
python manage.py migrate --noinput
python manage.py bootstrap
exec gunicorn --bind 0.0.0.0:8000 --workers 2 --threads 2 --timeout 120 config.wsgi:application
