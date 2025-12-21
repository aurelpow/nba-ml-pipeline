# 🚀 Quick Start - Google Cloud Setup

This guide will help you set up Cloud Run jobs for your NBA ML training pipeline.

## 📋 Step 1: Configure GCP Settings

You have **two options** to configure your GCP settings:

### Option A: Copy and Edit the Example File (Recommended for First Time)

The repository includes an example configuration file with placeholders. This is the safest way to get started:

```bash
cd ~/<your_nba_ml_project_directory>

# 1. Copy the example file to create your actual config
cp scripts/gcp_config.sh.example scripts/gcp_config.sh

# 2. Open the file in your editor
nano scripts/gcp_config.sh
# save and exit (Ctrl+O, Enter, Ctrl+X)
# or
vim scripts/gcp_config.sh
# or use any IDE of your choice
```

**What to update in `gcp_config.sh`:**

Replace these placeholder values with your actual GCP information:

```bash
# 🌐 Google Cloud Project Settings
export PROJECT_ID="your-project-id"              # ← Change to: ml-nba-project
export REGION="us-central1"                      # ← Keep or change to your region

# 🪣 Cloud Storage Settings
export BUCKET_NAME="your-bucket-name"            # ← Change to: ml-nba-project_cloudbuild
export MODELS_FOLDER="models_trained"            # ← Keep this

# 🔐 Service Account
export SERVICE_ACCOUNT="your-service-account@your-project-id.iam.gserviceaccount.com"
# ← Change to: nba-cloud-run-sa@ml-nba-project.iam.gserviceaccount.com

# 🐳 Artifact Registry Settings
export REPO_NAME="your-docker-repo"              # ← Change to: nba-docker-repo
export IMAGE_NAME="nba_project"                  # ← Keep this

# 🔑 Secret Manager Settings
export NBA_PROXY_USER_SECRET="nba-proxy-user"    # ← Name of your secret in GCP
export NBA_PROXY_PASS_SECRET="nba-proxy-pass"    # ← Name of your secret in GCP

# 📁 Git & Project Settings
export PROJECT_DIR="~/nba_project_ML"            # ← Adjust if your path is different
export DEV_BRANCH="develop"                      # ← Change to your dev branch name
export PROD_BRANCH="main"                        # ← Keep this
```

**💡 Example of filled values:**

```bash
export PROJECT_ID="ml-nba-project"
export REGION="us-central1"
export BUCKET_NAME="ml-nba-project_cloudbuild"
export SERVICE_ACCOUNT="nba-cloud-run-sa@ml-nba-project.iam.gserviceaccount.com"
export REPO_NAME="nba-docker-repo"
```

**⚠️ Important Notes:**
- The file `gcp_config.sh` is in `.gitignore` and will NOT be committed to version control
- The example file `gcp_config.sh.example` contains only placeholders (safe to commit)
- Never commit your actual `gcp_config.sh` with real credentials!

### Option B: Use Interactive Setup Script

If you prefer an interactive wizard:

```bash
cd ~/<your-project-directory>
chmod +x scripts/setup_gcp_config.sh
./scripts/setup_gcp_config.sh
```

This will prompt you for each value and create `scripts/gcp_config.sh` automatically.

---

### ✅ Verify Your Configuration

After creating your `gcp_config.sh`, verify it:

```bash
source scripts/gcp_config.sh --show
```

You should see your actual values displayed (not the placeholders).

---

## 📋 Step 2: Create Cloud Storage Folders

**Important:** In Google Cloud Storage, folders are virtual—they don't need to be explicitly created. They appear automatically when you upload files to those paths.

However, to verify your bucket exists and is accessible, you can:

```bash
# Source your configuration
source scripts/gcp_config.sh

# Verify bucket exists and is accessible
gsutil ls gs://${BUCKET_NAME}/

# Optional: Create empty placeholder files to "create" the folder structure visually
echo "Folder for production models" | gsutil cp - gs://${BUCKET_NAME}/models_trained/prod/.keep
echo "Folder for development models" | gsutil cp - gs://${BUCKET_NAME}/models_trained/develop/.keep
```

**Note:** The `.keep` files are optional placeholders. Your training scripts will automatically create the folder structure when they save models.

If your bucket doesn't exist yet, create it first:

```bash
gsutil mb -l ${REGION} gs://${BUCKET_NAME}/
```

## 📋 Step 3: Deploy Your Image

### For Development Testing

```bash
./scripts/deploy_develop.sh
```

This deploys your code with `:develop` tag.

### For Production

```bash
./scripts/deploy_production.sh
```

This deploys your code with `:latest` tag from main branch.

## 📋 Step 4: Create Cloud Run Jobs

### Development Job

The job configuration (targets, tuning) is loaded from `scripts/gcp_config.sh`.

```bash
# Create training job using settings from gcp_config.sh
./scripts/create_cloud_run_job_develop.sh
```

**To override settings for a specific run:**

You can pass `true` or `false` for tuning as an argument:
```bash
# Force tuning enabled
./scripts/create_cloud_run_job_develop.sh true
```

Or update the job configuration directly in GCP to change targets or tuning:
```bash
# Update existing job to change targets or tuning
gcloud run jobs update nba-training-develop \
  --set-env-vars="TARGET=points,TUNE_HYPERPARAMETERS=true" \
  --region=${REGION}
```

**What happens:**
- Job name: `nba-training-develop`
- **Targets**: Defined in `gcp_config.sh` (default: `points fantasy_points`)
- **Model Path**: `gs://bucket/models_trained/develop` (directory)
- **Execution**: `main.py` loops through targets and trains models sequentially.
- Secrets injected: `NBA_PROXY_USER`, `NBA_PROXY_PASS`

### Production Job

```bash
# Create production training job
./scripts/create_cloud_run_job_production.sh
```

## 📋 Step 5: Run Jobs

### Execute Development Job

```bash
./scripts/run_cloud_job_develop.sh
```

This will train **both** the points model and fantasy points model in a single execution.

### Execute Production Job

```bash
./scripts/run_cloud_job_production.sh
```

---

## 🗂️ Model Organization

Your models are organized as follows:

```
gs://your-bucket/models_trained/
├── prod/
│   ├── points_model.pkl              ← Production points model
│   └── fantasy_points_model.pkl      ← Production fantasy model
└── develop/
    ├── points_model.pkl              ← Development points model
    └── fantasy_points_model.pkl      ← Development fantasy model
```

**Benefits:**
- ✅ No risk of overwriting production models during testing
- ✅ Clear separation between environments
- ✅ Two separate models: one for points, one for fantasy points
- ✅ Easy rollback if needed

---

## 🎯 Available Scripts

| Script | Purpose |
|--------|---------|
| `setup_gcp_config.sh` | Interactive GCP configuration |
| `deploy_develop.sh` | Deploy develop image to Artifact Registry |
| `deploy_production.sh` | Deploy production image to Artifact Registry |
| `create_cloud_run_job_develop.sh` | Create development Cloud Run job |
| `create_cloud_run_job_production.sh` | Create production Cloud Run job |
| `run_cloud_job_develop.sh` | Execute development job |
| `run_cloud_job_production.sh` | Execute production job |
| `update_cloud_job_develop.sh` | Update development job config |
| `delete_cloud_job_develop.sh` | Delete development job |

---

## 📚 Full Documentation

For detailed information, see:
- **[Cloud Jobs Guide](docs/CLOUD_JOBS_GUIDE.md)** - Complete job management documentation
- **[Deployment Guide](docs/DEPLOYMENT_GUIDE.md)** - Image deployment details
- **[Training Guide](docs/TRAINING_GUIDE.md)** - Training parameters and usage

---

## ✅ Example Workflow

```bash
# 1. Configure GCP (one-time setup)
./scripts/setup_gcp_config.sh

# 2. Create storage folders (one-time setup)
source scripts/gcp_config.sh
gsutil mkdir gs://${BUCKET_NAME}/models_trained/prod/
gsutil mkdir gs://${BUCKET_NAME}/models_trained/develop/

# 3. Deploy develop image
./scripts/deploy_develop.sh

# 4. Create and test fantasy points job
./scripts/create_cloud_run_job_develop.sh fantasy_points false

# 5. Verify model was saved
gsutil ls gs://${BUCKET_NAME}/models_trained/develop/

# 6. Create and test points job
./scripts/create_cloud_run_job_develop.sh points false

# 7. When satisfied, deploy to production
git checkout main
git merge feature/fantsay-points-prediction
./scripts/deploy_production.sh

# 8. Create production jobs
./scripts/create_cloud_run_job_production.sh fantasy_points true
./scripts/create_cloud_run_job_production.sh points true
```

---

## 🆘 Troubleshooting

### Docker Push Failed - Invalid Registry URL

**Error: "error parsing HTTP 404 response body" with corrupted registry URL**

```bash
error pushing image "yes-docker.pkg.dev/ml-nba-project/..."
```

**Cause:**  
The `REGION` variable in `gcp_config.sh` got corrupted (e.g., changed from "us-central1" to "yes").

**Solution:**

1. **Check your REGION variable:**
   ```bash
   source scripts/gcp_config.sh
   echo $REGION
   echo $DEV_IMAGE_URI
   ```

2. **If REGION is wrong, fix it:**
   ```bash
   nano scripts/gcp_config.sh
   # Change: export REGION="yes"
   # To:     export REGION="us-central1"
   ```

3. **Re-source and verify:**
   ```bash
   source scripts/gcp_config.sh
   echo $REGION
   # Should show: us-central1
   
   echo $DEV_IMAGE_URI
   # Should show: us-central1-docker.pkg.dev/ml-nba-project/nba-docker-repo/nba_project:develop
   ```

4. **Try deploying again:**
   ```bash
   ./scripts/deploy_develop.sh
   ```

**Valid GCP Regions:**
- `us-central1` (Iowa)
- `us-east1` (South Carolina)
- `us-west1` (Oregon)
- `europe-west1` (Belgium)
- `asia-east1` (Taiwan)
- [Full list](https://cloud.google.com/artifact-registry/docs/repositories/repo-locations)

### Permission Denied Error

**Error: "Permission denied" when running scripts**

```bash
bash: ./scripts/deploy_develop.sh: Permission denied
```

**Solution:**  
The script files need execute permissions. Fix this by running:

```bash
# Make all scripts executable
chmod +x scripts/*.sh

# Or make individual scripts executable
chmod +x scripts/deploy_develop.sh
chmod +x scripts/deploy_production.sh
chmod +x scripts/create_cloud_run_job_develop.sh
chmod +x scripts/run_cloud_job_develop.sh
```

After setting permissions, run the script again:

```bash
./scripts/deploy_develop.sh
```

**Alternative:** You can also run scripts with `bash` directly (doesn't require execute permission):

```bash
bash scripts/deploy_develop.sh
```

### Folder Creation Issues

**Error: "The mb command requires a URL that specifies a bucket"**

```bash
CommandException: The mb command requires a URL that specifies a bucket.
"gs://ml-nba-project_cloudbuild/models_trained/prod/" is not valid.
```

**Explanation:**  
There is no `gsutil mkdir` command for Cloud Storage. Folders are virtual and created automatically when you upload files.

**Solution:**  
Don't try to create folders explicitly. Instead:

1. **Just verify your bucket exists:**
   ```bash
   gsutil ls gs://${BUCKET_NAME}/
   ```

2. **Your training scripts will create the folder structure automatically** when they save models to:
   - `gs://${BUCKET_NAME}/models_trained/prod/points_model.pkl`
   - `gs://${BUCKET_NAME}/models_trained/develop/fantasy_points_model.pkl`

3. **Optional:** If you want to see the folders before training, create placeholder files:
   ```bash
   echo "placeholder" | gsutil cp - gs://${BUCKET_NAME}/models_trained/prod/.keep
   echo "placeholder" | gsutil cp - gs://${BUCKET_NAME}/models_trained/develop/.keep
   ```

### Bucket Name Issues

**Error: "is not valid" when creating folders**

```bash
CommandException: The mb command requires a URL that specifies a bucket.
"gs://ml-nba-project_cloudbouild/..." is not valid.
```

**Solution:**
1. Check for typos in your bucket name:
   ```bash
   echo $BUCKET_NAME
   gsutil ls  # List all your buckets
   ```

2. Fix the typo in `scripts/gcp_config.sh` and re-source:
   ```bash
   nano scripts/gcp_config.sh
   source scripts/gcp_config.sh
   ```

3. If the bucket doesn't exist, create it first:
   ```bash
   gsutil mb -l ${REGION} gs://${BUCKET_NAME}/
   ```

### View Configuration

```bash
source scripts/gcp_config.sh --show
```

### Check if Image Exists

```bash
gcloud artifacts docker images list \
  ${REGION}-docker.pkg.dev/${PROJECT_ID}/${REPO_NAME}
```

### View Job Logs

If you cannot access the Cloud Console or get "Permission Denied", use the CLI:

```bash
# 1. Get the latest execution ID
JOB_NAME="nba-training-develop"
EXECUTION_ID=$(gcloud run jobs executions list --job=${JOB_NAME} --region=${REGION} --limit=1 --format="value(name)")

# 2. View logs (requires beta component)
gcloud beta run jobs executions logs ${EXECUTION_ID} --region=${REGION}
```

**Alternative (Standard Logging):**

```bash
gcloud logging read "resource.type=cloud_run_job AND resource.labels.job_name=${JOB_NAME}" --limit=50 --format="value(textPayload)"
```

### List Models

```bash
# Development models
gsutil ls -lh gs://${BUCKET_NAME}/models_trained/develop/

# Production models
gsutil ls -lh gs://${BUCKET_NAME}/models_trained/prod/
```

---

## 🔑 Key Points

1. **Configure Once**: Run `setup_gcp_config.sh` to create `gcp_config.sh`
2. **Two Environments**: Develop (for testing) and Production (for live use)
3. **One Job, Two Models**: Each job trains **both** points and fantasy_points models
4. **Separate Storage**: Dev and prod models saved in different GCS folders
5. **No Hardcoding**: All GCP settings in `gcp_config.sh`
6. **Secrets Management**: Proxy credentials injected via Secret Manager

---

**Need help?** Check the full guides in the `docs/` folder!
