FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DB_PATH=/app/data/uzex.duckdb

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app
COPY scripts ./scripts
COPY data/uzex_spot_data ./data/uzex_spot_data

# Build the DuckDB database inside the image (one-off, ~1-2 minutes).
RUN python scripts/build_db.py

CMD ["python", "-m", "app.bot"]
