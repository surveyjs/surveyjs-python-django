# The app's image: Python's slim image with the runtime requirements only (no Node), one process.
# Python 3.15.2 is the current patch release (2026-11-19); move the tag forward with each patch release.
FROM python:3.15.2-slim

# Production settings as real environment variables, which win over settings.env (included in the image) and .env
# (not copied: see .dockerignore). Debug off; listen on every interface; keep the data on the volume; trust
# X-Forwarded-For/-Proto from the proxy in front of the container. In your own production, set DJANGO_ALLOWED_HOSTS
# to your host names and FORWARDED_ALLOW_IPS to the proxy's addresses.
ENV DJANGO_DEBUG=false DJANGO_ALLOWED_HOSTS=* APP_HOST=0.0.0.0 APP_PORT=8000 DATA_DIR=/app/storage \
    FORWARDED_ALLOW_IPS=* PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
RUN python manage.py collectstatic --noinput -v 0

# Not root: the app only writes to /app/storage (the database, uploads, visitor sandboxes, relay snapshots, the key)
RUN useradd --system --uid 10001 --home-dir /app --shell /usr/sbin/nologin app \
    && mkdir -p /app/storage && chown app:app /app/storage
USER app

EXPOSE 8000
# One uvicorn process: the relay rooms, the channel layer, the cache and the demo's AI counter live in its memory.
# `serve` refuses a busy port, migrates (creating and seeding the database), then runs uvicorn.
CMD ["python", "manage.py", "serve"]
