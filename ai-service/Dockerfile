FROM python:3.11-slim

# Only libsndfile1 needed - no gcc/g++ (all ML packages are pre-built wheels)
RUN apt-get update && \
    apt-get install -y --no-install-recommends --fix-missing libsndfile1 || \
    (sleep 5 && apt-get update && apt-get install -y --no-install-recommends --fix-missing libsndfile1) && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .

# Step 1: lightweight packages (fast)
RUN pip install --no-cache-dir \
    "fastapi>=0.111.0,<0.112.0" \
    "uvicorn[standard]>=0.29.0,<0.30.0" \
    "httpx>=0.27.0,<0.28.0" \
    "structlog>=24.1.0,<25.0.0" \
    "pydantic>=2.7.0,<2.8.0" \
    "pydantic-settings>=2.2.0,<2.3.0" \
    "python-dotenv>=1.0.0,<2.0.0" \
    "asyncpg>=0.29.0,<0.30.0" \
    "cryptography>=42.0.0,<44.0.0"

# Step 2: numpy + scikit-learn (medium size, separate layer)
RUN pip install --no-cache-dir --timeout 300 --retries 5 \
    "numpy>=1.26.0,<2.0.0" \
    "scikit-learn>=1.5.0,<1.6.0"

# Step 3: torch CPU-only (~250MB vs 779MB GPU version)
RUN pip install --no-cache-dir --timeout 300 --retries 5 \
    --extra-index-url https://download.pytorch.org/whl/cpu \
    "torch>=2.3.0,<2.4.0"

# Step 4: transformers + tokenizers (depends on torch)
RUN pip install --no-cache-dir --timeout 300 --retries 5 \
    "transformers>=4.41.0,<4.42.0"

# Step 5: sentence-transformers
RUN pip install --no-cache-dir --timeout 300 --retries 5 \
    "sentence-transformers>=3.0.0,<3.1.0"

# Step 6: faster-whisper (ctranslate2 + onnxruntime are large, separate layer)
RUN pip install --no-cache-dir --timeout 300 --retries 5 \
    "faster-whisper>=1.0.0,<2.0.0"

# Step 7: Pre-download models into /app/models (owned by aiuser)
ENV TRANSFORMERS_CACHE=/app/models \
    HF_HOME=/app/models \
    SENTENCE_TRANSFORMERS_HOME=/app/models

COPY download_models.py .
RUN python3 download_models.py

COPY *.py ./

RUN mkdir -p /app/encrypted_uploads

RUN useradd -m -u 1000 aiuser && chown -R aiuser:aiuser /app
USER aiuser

EXPOSE 8001

CMD ["python", "inference.py"]