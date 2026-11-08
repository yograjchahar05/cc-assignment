FROM python:3.11-slim

WORKDIR /app

# Ensure curl is available for container healthchecks
RUN apt-get update && apt-get install -y --no-install-recommends curl && rm -rf /var/lib/apt/lists/*

# Install pinned dependencies using CPU-only PyTorch to keep image < 2 GB
COPY service/requirements.txt requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Copy service code and schema
COPY service/ /app/service/
COPY data/schema.json /app/data/schema.json

ENV PYTHONPATH=/app
ENV PORT=8000
ENV MODEL_URI=models/v1
ENV MODEL_VERSION=v1
ENV S3_ENDPOINT=""
ENV MAX_NEW_TOKENS=128
ENV FAULT_INJECT=0
ENV SCHEMA_PATH=/app/data/schema.json

EXPOSE 8000

CMD ["uvicorn", "service.app:app", "--host", "0.0.0.0", "--port", "8000"]

