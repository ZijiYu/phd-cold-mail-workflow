# Outreach dashboard image. Build from the repository root:
#   docker build -f dashboard/Dockerfile -t phd-outreach-dashboard .
# Or use dashboard/compose.yaml (recommended: it keeps the port on 127.0.0.1).
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PHD_DASHBOARD_CONTAINER=1

WORKDIR /app
# Runtime deps only (requirements.txt also lists httpx, which is for tests).
RUN pip install --no-cache-dir "fastapi>=0.110" "uvicorn>=0.27"

COPY dashboard/__init__.py dashboard/__main__.py dashboard/
COPY dashboard/app dashboard/app
COPY dashboard/static dashboard/static

RUN useradd --uid 1000 --create-home app \
    && mkdir -p /data /state \
    && chown app:app /data /state
USER app

# /data  : campaign folders (outreach/spring-2027, outreach/fall-2027, ...)
# /state : API token, Google OAuth client, Gmail token
VOLUME ["/data", "/state"]
EXPOSE 8765

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8765/', timeout=4)"

CMD ["python", "-m", "dashboard", "--data", "/data", "--state-dir", "/state", "--host", "0.0.0.0", "--port", "8765"]
