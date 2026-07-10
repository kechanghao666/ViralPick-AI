FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    VIRALPICK_ENV=production \
    VIRALPICK_API_HOST=0.0.0.0 \
    VIRALPICK_API_PORT=5000 \
    VIRALPICK_SERVE_FRONTEND=1

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY backend backend
COPY data/processed data/processed
COPY frontend frontend
COPY scripts scripts
COPY wsgi.py .

RUN python scripts/init_database.py --force \
    && python scripts/migrate_database.py

EXPOSE 5000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD curl -fsS http://127.0.0.1:5000/api/ready || exit 1

CMD ["gunicorn", "--bind", "0.0.0.0:5000", "--workers", "2", "--threads", "4", "--timeout", "120", "wsgi:app"]
