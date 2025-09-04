FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# OS deps (LightGBM runtime) + clean
RUN apt-get update \
 && apt-get install -y --no-install-recommends libgomp1 ca-certificates bash dos2unix \
 && rm -rf /var/lib/apt/lists/*

# Create an empty writable data dir in the image
RUN mkdir -p /app/databases

# Install deps first for better caching
COPY requirements.txt .
RUN pip install --upgrade pip \
 && pip install --no-cache-dir -r requirements.txt

# Copy code
COPY main.py ./ 
COPY src/    ./src
COPY common/ ./common
COPY scripts/ ./scripts

# Ensure LF endings + executable; then remove build-only pkgs
RUN dos2unix ./scripts/run_all.sh \
 && chmod +x ./scripts/run_all.sh \
 && apt-get purge -y dos2unix \
 && apt-get autoremove -y \
 && rm -rf /var/lib/apt/lists/*

# Entrypoint provides the orchestrator
ENTRYPOINT ["./scripts/run_all.sh"]

# CMD can be empty because the script reads env
CMD []