FROM nvcr.io/nvidia/pytorch:24.01-py3

WORKDIR /app

# System deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    redis-tools curl git && \
    rm -rf /var/lib/apt/lists/*

# Python deps
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Source
COPY src/ src/
COPY configs/ configs/
COPY api/ api/

ENV PYTHONPATH=/app
ENV LOG_DIR=/logs
ENV CHECKPOINT_DIR=/checkpoints

# Default: launch the API server
CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]
