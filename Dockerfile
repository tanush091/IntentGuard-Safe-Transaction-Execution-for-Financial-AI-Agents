FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Install python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application source code and tests
COPY . .

# Expose Gateway & Payment ports
EXPOSE 8000 8001

CMD ["uvicorn", "src.gateway.api:app", "--host", "0.0.0.0", "--port", "8000"]
