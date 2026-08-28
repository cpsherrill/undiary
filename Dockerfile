FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Static files are baked into the image; whitenoise serves them.
# DEBUG=0 so the hashed manifest the production settings expect exists.
RUN SECRET_KEY=build-time-only DEBUG=0 python manage.py collectstatic --noinput

# Cloud Run provides PORT.
CMD exec gunicorn undiary.wsgi:application \
    --bind "0.0.0.0:${PORT:-8080}" --workers 2 --threads 4 --timeout 60
