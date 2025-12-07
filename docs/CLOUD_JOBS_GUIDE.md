# ☁️ Google Cloud Job Management Guide

This guide explains how to create, manage, and execute Cloud Run jobs for NBA ML training pipeline.

## 📁 Prerequisites

### 1. Configure GCP Settings

Edit `scripts/gcp_config.sh` with your GCP details:

```bash
# Required configurations
export PROJECT_ID="your-project-id"              # Your GCP project ID
export REGION="us-central1"                      # Your region
export BUCKET_NAME="your-bucket-name"            # Cloud Storage bucket
export SERVICE_ACCOUNT="your-sa@project.iam.gserviceaccount.com"
export REPO_NAME="your-artifact-repo"            # Artifact Registry repo
export IMAGE_NAME="your-image-name"              # Docker image name
```

### 2. Verify Configuration

```bash
# View current configuration
source scripts/gcp_config.sh --show
```

---

## 🏗️ Model Storage Structure

Your Cloud Storage bucket organizes models by environment and target:

```
gs://your-bucket/models_trained/
├── prod/
│   ├── points_model.pkl              # Production points model
│   └── fantasy_points_model.pkl      # Production fantasy model
└── develop/
    ├── points_model.pkl              # Development points model
    └── fantasy_points_model.pkl      # Development fantasy model
```

**Key Benefits:**
- ✅ Separate dev and prod models
- ✅ No risk of overwriting production models during testing
- ✅ Clear model versioning per environment
- ✅ Easy rollback if needed

---

## 🧪 Development Jobs

### Create Development Job

```bash
# Create fantasy points job (fast, no tuning)
./scripts/create_cloud_run_job_develop.sh fantasy_points false

# Create points job with tuning
./scripts/create_cloud_run_job_develop.sh points true
```

**What happens:**
- Creates job: `nba-training-fantasy_points-develop` or `nba-training-points-develop`
- Uses `:develop` image tag
- Saves to `develop/` folder in Cloud Storage
- Executes immediately for testing

### Run Existing Development Job

```bash
# Run fantasy points training
./scripts/run_cloud_job_develop.sh fantasy_points

# Run points training
./scripts/run_cloud_job_develop.sh points
```

### Update Development Job

```bash
# Update fantasy job, enable tuning
./scripts/update_cloud_job_develop.sh fantasy_points true

# Update points job, disable tuning
./scripts/update_cloud_job_develop.sh points false
```

### Delete Development Job

```bash
./scripts/delete_cloud_job_develop.sh fantasy_points
./scripts/delete_cloud_job_develop.sh points
```

---

## 🚀 Production Jobs

### Create Production Job

```bash
# Create fantasy points job
./scripts/create_cloud_run_job_production.sh fantasy_points false

# Create points job with tuning
./scripts/create_cloud_run_job_production.sh points true
```

**What happens:**
- Creates job: `nba-training-fantasy_points-prod` or `nba-training-points-prod`
- Uses `:latest` image tag
- Saves to `prod/` folder in Cloud Storage
- Requires confirmation prompt

### Run Production Job

```bash
# Run fantasy points training
./scripts/run_cloud_job_production.sh fantasy_points

# Run points training
./scripts/run_cloud_job_production.sh points
```

**Safety Features:**
- ⚠️ Confirmation prompt before execution
- 📊 Automatic log display after completion
- 🔍 Direct link to Cloud Console logs

---

## 📊 Job Configuration

All jobs use settings from `gcp_config.sh`:

| Setting | Default | Description |
|---------|---------|-------------|
| Memory | 4Gi | RAM allocated |
| CPU | 2 | CPU cores |
| Timeout | 3600s | Max execution time (1 hour) |
| Max Retries | 1 | Retry on failure |

### Environment Variables Passed to Jobs

```bash
PROCESS=train                    # Always "train"
TARGET=points|fantasy_points     # What to predict
MODEL_PATH=gs://...              # Where to save model
SAVE_MODE=bq                     # Always BigQuery mode
TUNE_PARAMS=true|false           # Enable hyperparameter tuning
SEASON=2025-26                   # NBA season
SEASON_TYPE=Regular Season       # Season type
```

---

## 🔄 Typical Workflow

### Development Cycle

1. **Deploy develop image**
   ```bash
   ./scripts/deploy_develop.sh
   ```

2. **Create and test fantasy points job**
   ```bash
   ./scripts/create_cloud_run_job_develop.sh fantasy_points false
   ```

3. **Verify model in Cloud Storage**
   ```bash
   gsutil ls gs://your-bucket/models_trained/develop/
   ```

4. **Test points model**
   ```bash
   ./scripts/create_cloud_run_job_develop.sh points false
   ```

5. **When satisfied, deploy to production**
   ```bash
   # Merge to main branch first
   git checkout main
   git merge feature/fantsay-points-prediction
   git push origin main
   
   # Deploy production image
   ./scripts/deploy_production.sh
   
   # Create production jobs
   ./scripts/create_cloud_run_job_production.sh fantasy_points true
   ./scripts/create_cloud_run_job_production.sh points true
   ```

---

## 🔍 Monitoring and Debugging

### View Job Executions

```bash
# List all executions for fantasy points develop job
gcloud run jobs executions list \
  --job=nba-training-fantasy_points-develop \
  --region=us-central1

# List all executions for points production job
gcloud run jobs executions list \
  --job=nba-training-points-prod \
  --region=us-central1
```

### View Logs

```bash
# Get logs from latest execution
gcloud run jobs executions logs $(
  gcloud run jobs executions list \
    --job=nba-training-fantasy_points-develop \
    --region=us-central1 \
    --limit=1 \
    --format='value(name)'
) --region=us-central1
```

### Check Model Files

```bash
# List develop models
gsutil ls -lh gs://your-bucket/models_trained/develop/

# List production models
gsutil ls -lh gs://your-bucket/models_trained/prod/

# Download model for inspection
gsutil cp gs://your-bucket/models_trained/develop/fantasy_points_model.pkl .
```

---

## 🗓️ Scheduling Jobs

### Create Cloud Scheduler for Production

```bash
# Schedule fantasy points training daily at 2 AM
gcloud scheduler jobs create http nba-fantasy-daily \
  --location=us-central1 \
  --schedule="0 2 * * *" \
  --uri="https://us-central1-run.googleapis.com/apis/run.googleapis.com/v1/namespaces/YOUR_PROJECT_ID/jobs/nba-training-fantasy_points-prod:run" \
  --http-method=POST \
  --oauth-service-account-email=nba-cloud-run-sa@YOUR_PROJECT_ID.iam.gserviceaccount.com

# Schedule points training weekly on Monday at 3 AM
gcloud scheduler jobs create http nba-points-weekly \
  --location=us-central1 \
  --schedule="0 3 * * 1" \
  --uri="https://us-central1-run.googleapis.com/apis/run.googleapis.com/v1/namespaces/YOUR_PROJECT_ID/jobs/nba-training-points-prod:run" \
  --http-method=POST \
  --oauth-service-account-email=nba-cloud-run-sa@YOUR_PROJECT_ID.iam.gserviceaccount.com
```

---

## ⚙️ Configuration Examples

### Example: gcp_config.sh (filled out)

```bash
export PROJECT_ID="ml-nba-project"
export REGION="us-central1"
export BUCKET_NAME="ml-nba-project_cloudbuild"
export MODELS_FOLDER="models_trained"
export SERVICE_ACCOUNT="nba-cloud-run-sa@ml-nba-project.iam.gserviceaccount.com"
export REPO_NAME="nba-docker-repo"
export IMAGE_NAME="nba_project"

# Automatically computed paths
export PROD_POINTS_MODEL="gs://ml-nba-project_cloudbuild/models_trained/prod/points_model.pkl"
export PROD_FANTASY_MODEL="gs://ml-nba-project_cloudbuild/models_trained/prod/fantasy_points_model.pkl"
export DEV_POINTS_MODEL="gs://ml-nba-project_cloudbuild/models_trained/develop/points_model.pkl"
export DEV_FANTASY_MODEL="gs://ml-nba-project_cloudbuild/models_trained/develop/fantasy_points_model.pkl"
```

---

## 🆘 Troubleshooting

### Job Creation Fails

```bash
# Verify configuration
source scripts/gcp_config.sh --show

# Check if image exists
gcloud artifacts docker images list \
  ${REGION}-docker.pkg.dev/${PROJECT_ID}/${REPO_NAME}

# Verify service account permissions
gcloud projects get-iam-policy ${PROJECT_ID} \
  --flatten="bindings[].members" \
  --filter="bindings.members:serviceAccount:${SERVICE_ACCOUNT}"
```

### Job Execution Fails

```bash
# View detailed logs
gcloud run jobs executions describe EXECUTION_NAME \
  --region=${REGION}

# Check environment variables
gcloud run jobs describe JOB_NAME \
  --region=${REGION} \
  --format="value(template.template.containers[0].env)"
```

### Model Not Saved

```bash
# Verify bucket exists and is accessible
gsutil ls gs://${BUCKET_NAME}/

# Check service account has storage permissions
gsutil iam get gs://${BUCKET_NAME}/
```

---

## 📚 Quick Reference

| Task | Command |
|------|---------|
| Configure GCP | Edit `scripts/gcp_config.sh` |
| View config | `source scripts/gcp_config.sh --show` |
| Create dev job | `./scripts/create_cloud_run_job_develop.sh <target> <tune>` |
| Run dev job | `./scripts/run_cloud_job_develop.sh <target>` |
| Create prod job | `./scripts/create_cloud_run_job_production.sh <target> <tune>` |
| Run prod job | `./scripts/run_cloud_job_production.sh <target>` |
| List models | `gsutil ls gs://BUCKET/models_trained/{prod,develop}/` |
| View logs | Check script output or Cloud Console |

---

## 🎯 Next Steps

1. ✅ Configure `gcp_config.sh` with your values
2. ✅ Test with develop jobs first
3. ✅ Verify models are saved correctly
4. ✅ When confident, create production jobs
5. ✅ Set up Cloud Scheduler for automation
