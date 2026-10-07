# API image: slim Python 3.11, runtime dependencies only, non-root user.
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app
COPY requirements-api.txt .
RUN pip install -r requirements-api.txt

# Only the packages the API imports: no pipeline code, data or config
COPY src/fibre_planning/__init__.py src/fibre_planning/__init__.py
COPY src/fibre_planning/db src/fibre_planning/db
COPY src/fibre_planning/api src/fibre_planning/api
ENV PYTHONPATH=/app/src

RUN useradd --create-home --uid 10001 api
USER api

EXPOSE 8000
HEALTHCHECK --interval=15s --timeout=3s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health')"
CMD ["uvicorn", "fibre_planning.api.app:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2"]
