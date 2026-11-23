# Dockerfile per Re:Zero Japanese Reader
# Deploy su Fly.io con volume persistente

FROM python:3.12-slim

WORKDIR /app

# Dipendenze sistema
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Python deps
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Codice app
COPY reader/ ./reader/

# Script entrypoint
COPY docker-entrypoint.sh .
RUN chmod +x docker-entrypoint.sh

# Porta esposta
EXPOSE 8080

ENTRYPOINT ["./docker-entrypoint.sh"]
