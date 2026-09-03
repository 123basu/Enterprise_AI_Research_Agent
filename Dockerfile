FROM python:3.12-slim

WORKDIR /app

# Install deps first for caching
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy app
COPY app ./app
COPY data ./data
# Ensure data dir exists and is writable (ephemeral on free hosts)
RUN mkdir -p data

EXPOSE 8000

# Use $PORT if provided by host (Render/Railway/Fly), else 8000
CMD sh -c "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"
