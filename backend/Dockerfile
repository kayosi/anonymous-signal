FROM python:3.11-slim

# Install system dependencies
RUN apt-get update && apt-get install -y \
    libmagic1 \
    libpq-dev \
    gcc \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application
COPY app/ ./app/
COPY sql/ ./sql/

# Create encrypted uploads directory
RUN mkdir -p /app/encrypted_uploads && chmod 700 /app/encrypted_uploads

# Create non-root user for security (useradd = Debian, not adduser -D which is Alpine)
RUN useradd -m -u 1000 appuser && chown -R appuser:appuser /app
USER appuser

EXPOSE 8000

# PRIVACY: --no-access-log — no request logging
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--no-access-log", "--workers", "4"]