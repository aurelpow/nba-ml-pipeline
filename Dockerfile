FROM python:3.9-slim

WORKDIR /app

# 0) Install OS-level deps (libgomp for LightGBM + cleanup)
RUN apt-get update \
 && apt-get install -y --no-install-recommends libgomp1 \
 && rm -rf /var/lib/apt/lists/*

# 1) Install Python deps
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 2) Copy application code
COPY main.py .
COPY src/    ./src
COPY common/ ./common
COPY run_all.sh .

# 3) Copy your model artifact(s)
#COPY ml_dev/models/best_lgbm_model_v2.pkl ml_dev/models/
RUN mkdir -p ml_dev/models
# 4) Ensure run_all.sh is executable
RUN chmod +x run_all.sh

# 5) Use  launcher as the entrypoint
ENTRYPOINT ["./run_all.sh"]