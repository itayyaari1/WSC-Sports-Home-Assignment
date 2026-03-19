FROM python:3.11-slim

WORKDIR /app

# Install system dependencies for confluent-kafka
RUN apt-get update && \
    apt-get install -y --no-install-recommends gcc librdkafka-dev && \
    rm -rf /var/lib/apt/lists/*

COPY producer/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY producer/src/ ./src/
COPY producer/tests/ ./tests/
COPY shared/ ./shared/

ENV PYTHONPATH=/app

CMD ["python", "-m", "src.main"]
