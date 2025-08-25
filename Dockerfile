FROM python:3.11-slim

WORKDIR /app

# 0) Install OS-level deps (libgomp for LightGBM + cleanup)
RUN apt-get update \
&& apt-get install -y --no-install-recommends libgomp1 \
&& rm -rf /var/lib/apt/lists/*

# 1) Install Python deps
COPY requirements.txt .
RUN pip install --upgrade pip
RUN pip install --no-cache-dir -r requirements.txt

# 2) Copy application code
COPY main.py .
COPY src/    ./src
COPY common/ ./common
COPY run_all.sh .

# 3) Ensure run_all.sh has proper line endings and is executable
RUN apt-get update && apt-get install -y --no-install-recommends dos2unix \
  && dos2unix run_all.sh \
  && chmod +x run_all.sh \
  && apt-get purge -y dos2unix && apt-get autoremove -y \
  && rm -rf /var/lib/apt/lists/*

# 4) Use  launcher as the entrypoint
ENTRYPOINT ["./run_all.sh"]