# ─────────────────────────────────────────────────────────────────────────
#  RoboGrid AI — application image
#  One image runs every role (web/asgi/celery/beat/mqtt-bridge); the command
#  is chosen per-service in docker-compose. Multi-stage keeps it lean.
# ─────────────────────────────────────────────────────────────────────────
FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# System deps: libpq for psycopg, build tools for any wheels that need them.
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential libpq-dev curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .

# Run as an unprivileged user.
RUN useradd --create-home --uid 1000 robogrid \
    && mkdir -p /app/staticfiles /app/media \
    && chown -R robogrid:robogrid /app
USER robogrid

EXPOSE 8000

COPY --chown=robogrid:robogrid deploy/entrypoint.sh /app/deploy/entrypoint.sh
ENTRYPOINT ["/app/deploy/entrypoint.sh"]

# Default: ASGI server (HTTP + WebSockets) via uvicorn workers under gunicorn.
CMD ["gunicorn", "config.asgi:application", \
     "-k", "uvicorn.workers.UvicornWorker", \
     "-b", "0.0.0.0:8000", "--workers", "4", "--timeout", "120"]
