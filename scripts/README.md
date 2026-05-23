# 📋 Scripts Overview

This directory contains all deployment and job management scripts for Google Cloud Platform.

## 🎯 Quick Navigation

### Setup & Configuration
- **[setup_gcp_config.sh](#setup_gcp_configsh)** - Interactive GCP configuration wizard
- **[gcp_config.sh.example](#gcp_configshexample)** - Example configuration template

### Image Deployment
- **[deploy_develop.sh](#deploy_developsh)** - Deploy develop image
- **[deploy_production.sh](#deploy_productionsh)** - Deploy production image

### Development Jobs
- **[create_cloud_run_job_develop.sh](#create_cloud_run_job_developsh)** - Create dev job
- **[run_cloud_job_develop.sh](#run_cloud_job_developsh)** - Execute dev job
- **[update_cloud_job_develop.sh](#update_cloud_job_developsh)** - Update dev job
- **[delete_cloud_job_develop.sh](#delete_cloud_job_developsh)** - Delete dev job

### Production Jobs
- **[create_cloud_run_job_production.sh](#create_cloud_run_job_productionsh)** - Create prod job
- **[run_cloud_job_production.sh](#run_cloud_job_productionsh)** - Execute prod job

---

## 📝 Script Details

### setup_gcp_config.sh
**Purpose:** Interactive wizard to configure GCP settings

**Usage:**
```bash
./scripts/setup_gcp_config.sh
```

**What it does:**
- Prompts for GCP project ID, region, bucket, etc.
- Creates `gcp_config.sh` with your settings
- Validates configuration
- Shows summary of created paths

**First-time setup required:** Yes (run once)

---

### gcp_config.sh.example
**Purpose:** Template configuration file with example values

**Usage:**
```bash
# Option 1: Use the wizard (recommended)
./scripts/setup_gcp_config.sh

# Option 2: Manual copy and edit
cp scripts/gcp_config.sh.example scripts/gcp_config.sh
# Then edit gcp_config.sh with your values
```

**What it contains:**
- Project ID and region
- Cloud Storage bucket name
- Service account
- Artifact Registry details
- Model storage paths
- Compute resources
- Secret Manager secret names for proxy credentials and Discord webhook

**Note:** The actual `gcp_config.sh` is in `.gitignore` (contains sensitive info)

---

### deploy_develop.sh
**Purpose:** Deploy Docker image with `:develop` tag to Artifact Registry

**Usage:**
```bash
./scripts/deploy_develop.sh
```

**What it does:**
1. Syncs code from `origin/feature/fantsay-points-prediction`
2. Builds Docker image
3. Pushes to Artifact Registry as `IMAGE:develop`

**When to use:**
- Testing new features
- Before creating develop jobs
- After code changes in feature branch

**Prerequisites:**
- `gcp_config.sh` configured
- Docker authentication set up
- Feature branch pushed to GitHub

---

### deploy_production.sh
**Purpose:** Deploy Docker image with `:latest` tag to Artifact Registry

**Usage:**
```bash
./scripts/deploy_production.sh
```

**What it does:**
1. **Requires confirmation** (production deployment)
2. Syncs code from `origin/main`
3. Builds Docker image
4. Pushes to Artifact Registry as `IMAGE:latest`

**When to use:**
- After merging to main
- Ready for production deployment
- Creating production jobs

**Prerequisites:**
- `gcp_config.sh` configured
- Changes merged to main branch
- Tested in develop environment

---

### create_cloud_run_job_develop.sh
**Purpose:** Create Cloud Run job for development testing

**Usage:**
```bash
./scripts/create_cloud_run_job_develop.sh <target> [tune_params]
```

**Examples:**
```bash
# Fantasy points - fast training (no tuning)
./scripts/create_cloud_run_job_develop.sh fantasy_points false

# Points - with hyperparameter tuning
./scripts/create_cloud_run_job_develop.sh points true
```

**What it does:**
1. Creates job: `nba-training-<target>-develop`
2. Configures environment variables
3. Uses `:develop` image
4. Executes job immediately
5. Saves model to `develop/` folder
6. Mounts `DISCORD_WEBHOOK_URL` so post-evaluation alerts can fire when present

**Job names created:**
- `nba-training-fantasy_points-develop`
- `nba-training-points-develop`

---

### run_cloud_job_develop.sh
**Purpose:** Execute existing development job

**Usage:**
```bash
./scripts/run_cloud_job_develop.sh <target>
```

**Examples:**
```bash
./scripts/run_cloud_job_develop.sh fantasy_points
./scripts/run_cloud_job_develop.sh points
```

**What it does:**
1. Executes the specified job
2. Waits for completion
3. Shows execution details
4. Displays recent logs
5. Mounts `DISCORD_WEBHOOK_URL` so post-evaluation alerts can fire when present
**When to use:**
- After creating a job
- Re-running training with same config
- Testing after image update

---

### update_cloud_job_develop.sh
**Purpose:** Update existing development job configuration

**Usage:**
```bash
./scripts/update_cloud_job_develop.sh <target> [tune_params]
```

**Examples:**
```bash
# Enable tuning for fantasy points
./scripts/update_cloud_job_develop.sh fantasy_points true

# Disable tuning for points
./scripts/update_cloud_job_develop.sh points false
```

**What it does:**
1. Updates job configuration
2. Changes environment variables
3. Updates to latest `:develop` image
4. Does NOT execute (use `run_cloud_job_develop.sh` after)

**When to use:**
- Changing training parameters
- After deploying new image
- Modifying job settings

---

### delete_cloud_job_develop.sh
**Purpose:** Delete development job

**Usage:**
```bash
./scripts/delete_cloud_job_develop.sh <target>
```

**Examples:**
```bash
./scripts/delete_cloud_job_develop.sh fantasy_points
./scripts/delete_cloud_job_develop.sh points
```

**What it does:**
1. **Requires confirmation**
2. Deletes the specified job
3. Removes all job metadata

**When to use:**
- Cleaning up test jobs
- Before recreating with different config
- Removing unused jobs

**Note:** Does NOT delete the trained models in Cloud Storage

---

### create_cloud_run_job_production.sh
**Purpose:** Create Cloud Run job for production

**Usage:**
```bash
./scripts/create_cloud_run_job_production.sh <target> [tune_params]
```

**Examples:**
```bash
# Fantasy points with tuning
./scripts/create_cloud_run_job_production.sh fantasy_points true

# Points with tuning
./scripts/create_cloud_run_job_production.sh points true
```

**What it does:**
1. **Requires confirmation** (production)
2. Creates job: `nba-training-<target>-prod`
3. Uses `:latest` image
4. Configures for production
5. Saves model to `prod/` folder
6. Mounts `DISCORD_WEBHOOK_URL` so post-evaluation alerts can fire when present

**Job names created:**
- `nba-training-fantasy_points-prod`
- `nba-training-points-prod`

**When to use:**
- After testing in develop
- Ready for production deployment
- Setting up scheduled training

---

### run_cloud_job_production.sh
**Purpose:** Execute production job

**Usage:**
```bash
./scripts/run_cloud_job_production.sh <target>
```

**Examples:**
```bash
./scripts/run_cloud_job_production.sh fantasy_points
./scripts/run_cloud_job_production.sh points
```

**What it does:**
1. **Requires confirmation** (production)
2. Executes the specified job
3. Waits for completion
4. Shows logs and results

**When to use:**
- Manual production training
- After deploying new production image
- Testing production setup

---

## 🗺️ Typical Workflows

### First-Time Setup

```bash
# 1. Configure GCP
./scripts/setup_gcp_config.sh

# 2. Verify config
source scripts/gcp_config.sh --show

# 3. Create storage folders
gsutil mkdir gs://${BUCKET_NAME}/models_trained/prod/
gsutil mkdir gs://${BUCKET_NAME}/models_trained/develop/
```

### Development Testing

```bash
# 1. Deploy develop image
./scripts/deploy_develop.sh

# 2. Create job
./scripts/create_cloud_run_job_develop.sh fantasy_points false

# 3. Check results
gsutil ls gs://${BUCKET_NAME}/models_trained/develop/
```

### Production Deployment

```bash
# 1. Merge to main
git checkout main
git merge feature/fantsay-points-prediction
git push origin main

# 2. Deploy production image
./scripts/deploy_production.sh

# 3. Create production jobs
./scripts/create_cloud_run_job_production.sh fantasy_points true
./scripts/create_cloud_run_job_production.sh points true

# 4. Run manually or set up Cloud Scheduler
./scripts/run_cloud_job_production.sh fantasy_points
```

---

## 🔐 Security Notes

- ✅ `gcp_config.sh` is in `.gitignore` (contains project IDs)
- ✅ `gcp_config.sh.example` is committed (safe template)
- ✅ Service accounts have minimal required permissions
- ✅ Production jobs require confirmation prompts

---

## 📚 Related Documentation

- [Cloud Setup Quickstart](../docs/CLOUD_SETUP_QUICKSTART.md)
- [Cloud Jobs Guide](../docs/CLOUD_JOBS_GUIDE.md)
- [Deployment Guide](../docs/DEPLOYMENT_GUIDE.md)

---

## 🆘 Getting Help

```bash
# View your configuration
source scripts/gcp_config.sh --show

# Check if image exists
gcloud artifacts docker images list \
  ${REGION}-docker.pkg.dev/${PROJECT_ID}/${REPO_NAME}

# List all jobs
gcloud run jobs list --region=${REGION}

# View job details
gcloud run jobs describe JOB_NAME --region=${REGION}
```
