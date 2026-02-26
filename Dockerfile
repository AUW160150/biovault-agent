FROM python:3.11-slim

# System deps: no build caches, keep image lean
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python deps first (layer cache)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Data directory — SQLite DB and uploaded files live here
# Mount a persistent volume at /data in deploy.yaml
RUN mkdir -p /data/uploads

# Expose the API port
EXPOSE 8000

# Health check — Akash and load balancers will poll this
HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# startup.sh: runs uvicorn (agent loop starts inside FastAPI lifespan)
COPY startup.sh /startup.sh
RUN chmod +x /startup.sh

CMD ["/startup.sh"]
