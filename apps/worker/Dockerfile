# Dracara Growth OS worker (Celery). Build from the repo root:
#   docker build -f apps/worker/Dockerfile -t dracara-worker .
# One image, two processes -- run exactly ONE beat alongside any number of workers:
#   docker run dracara-worker                                   # worker (default)
#   docker run dracara-worker celery -A worker_app beat --loglevel=info
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app
COPY packages/scoring packages/scoring
COPY packages/billing packages/billing
COPY packages/ai packages/ai
COPY apps/worker/requirements.txt apps/worker/requirements.txt
WORKDIR /app/apps/worker
RUN pip install -r requirements.txt

COPY apps/worker/*.py ./
RUN useradd --system --uid 10001 app
USER app

ARG RELEASE=""
ENV RELEASE=${RELEASE}

CMD ["celery", "-A", "worker_app", "worker", "--loglevel=info", "--concurrency=2"]
