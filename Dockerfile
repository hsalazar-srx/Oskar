# OSKAR — Backend Image
# Python 3.12 / FastAPI
# Built and pushed to Harbor registry by push-image.sh
#
# Build: docker build -t oskar-app .
# Run:   docker compose -f docker/docker-compose.yml up

FROM python:3.12-slim

WORKDIR /app

# Install system dependencies for ldap3 and asyncpg
RUN apt-get update && apt-get install -y --no-install-recommends \
    libldap2-dev \
    libsasl2-dev \
    gcc \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application source
COPY src/ ./src/

# Non-root user for container security
RUN useradd -m -u 1000 oskar && chown -R oskar:oskar /app
USER oskar

# Expose FastAPI port
EXPOSE 8000

# Health check — matches docker-compose healthcheck
HEALTHCHECK --interval=30s --timeout=10s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000"]
