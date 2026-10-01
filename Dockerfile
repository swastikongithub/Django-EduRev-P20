# syntax=docker/dockerfile:1.7
#
# LPU Reserve (EduRev P20) — one image for web (gunicorn), worker and beat (celery).
#   docker build -t lpu-reserve .
#   docker compose up --build        # full stack: web, worker, beat, PostgreSQL, Redis

ARG PYTHON_IMAGE=python:3.12-slim

# ── Stage 1: build wheels (build tools live only here) ──────────────────────
FROM ${PYTHON_IMAGE} AS builder

ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1

RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /build
COPY requirements.txt .
RUN pip wheel --wheel-dir /wheels -r requirements.txt


# ── Stage 2: runtime (no compilers, non-root) ───────────────────────────────
FROM ${PYTHON_IMAGE} AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    DJANGO_SETTINGS_MODULE=config.settings \
    PORT=8000 \
    WEB_CONCURRENCY=3 \
    LOG_JSON=1

RUN groupadd --system --gid 10001 app \
    && useradd --system --uid 10001 --gid app --home-dir /app --shell /usr/sbin/nologin app

COPY --from=builder /wheels /wheels
COPY requirements.txt /tmp/requirements.txt
RUN pip install --no-index --find-links=/wheels -r /tmp/requirements.txt \
    && rm -rf /wheels /tmp/requirements.txt

WORKDIR /app
COPY . .

# Static files are baked into the image. collectstatic needs settings to import, so it
# gets a throwaway build-only key; the real DJANGO_SECRET_KEY is supplied at runtime.
# Then create the only writable dirs: uploads, gunicorn's (>=25) control socket and the
# celery beat schedule. The application code itself stays owned by root.
RUN DJANGO_SECRET_KEY=build-only-collectstatic-not-a-secret \
    DATABASE_URL=postgres://build@localhost:5432/build \
    REDIS_URL= \
    python manage.py collectstatic --noinput \
    && mkdir -p /app/.media /app/.gunicorn /var/lib/celery \
    && chown -R app:app /app/staticfiles /app/.media /app/.gunicorn /var/lib/celery

USER app

EXPOSE 8000

# Liveness only: /health/ never touches the database. Worker/beat disable this in compose.
HEALTHCHECK --interval=15s --timeout=5s --start-period=40s --retries=3 \
    CMD python -c "import os,sys,urllib.request; sys.exit(0 if urllib.request.urlopen('http://localhost:%s/health/' % os.environ.get('PORT','8000'), timeout=4).status == 200 else 1)"

# entrypoint.sh waits for PostgreSQL, runs migrations when RUN_MIGRATIONS=1, then execs CMD.
# Invoked through sh so it does not depend on the file's executable bit.
ENTRYPOINT ["sh", "/app/docker/entrypoint.sh"]
CMD ["sh", "-c", "exec gunicorn config.wsgi:application --bind 0.0.0.0:${PORT} --workers ${WEB_CONCURRENCY} --worker-tmp-dir /dev/shm --timeout 30 --graceful-timeout 20 --access-logfile - --error-logfile -"]
