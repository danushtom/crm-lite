# Dracara Growth OS API. Build from the repo root, which holds the shared workspace packages:
#   docker build -f apps/api/Dockerfile -t dracara-api .
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app
# Same layout as the repo, so requirements.txt's `-e ../../packages/...` paths resolve.
COPY packages/scoring packages/scoring
COPY packages/billing packages/billing
COPY packages/ai packages/ai
COPY apps/api/requirements.txt apps/api/requirements.txt
WORKDIR /app/apps/api
RUN pip install -r requirements.txt

COPY apps/api/app app
RUN useradd --system --uid 10001 app
USER app

ARG RELEASE=""
ENV RELEASE=${RELEASE} \
    PORT=8000 \
    WEB_CONCURRENCY=2 \
    # Trusted proxies whose X-Forwarded-For uvicorn honours (--proxy-headers), so rate limits
    # and logs see the real client address. Set it to your load balancer's address range, or
    # "*" only when the platform's proxy is the sole way in to this container.
    FORWARDED_ALLOW_IPS=127.0.0.1
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD python -c "import os,urllib.request; urllib.request.urlopen(f'http://127.0.0.1:{os.environ.get(\"PORT\",\"8000\")}/health/live', timeout=4)"

CMD ["sh", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT} --workers ${WEB_CONCURRENCY} --proxy-headers --no-server-header"]
