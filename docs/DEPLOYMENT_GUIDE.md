# 🚀 Deployment Guide

This guide explains how to deploy your Docker image to Google Cloud Artifact Registry for different environments.

## 📁 Available Scripts

- `scripts/deploy_develop.sh` - Deploy to **develop** environment
- `scripts/deploy_production.sh` - Deploy to **production** environment

## 🔧 Environment Setup

### Development Environment
- **Branch**: `feature/fantsay-points-prediction`
- **Image Tag**: `develop`
- **Purpose**: Testing new features and changes

### Production Environment
- **Branch**: `main`
- **Image Tag**: `latest`
- **Purpose**: Live production workloads

---

## 🛠️ Prerequisites

1. **Google Cloud SDK** installed and authenticated
   ```bash
   gcloud auth login
   gcloud config set project ml-nba-project
   ```

2. **Git repository** configured
   ```bash
   git remote -v  # Verify origin points to your GitHub repo
   ```

3. **Permissions** in GCP project:
   - Artifact Registry Writer
   - Cloud Build Editor
   - Storage Admin

---

## 🚀 Deployment Steps

### Deploy to Develop

1. Navigate to project directory:
   ```bash
   cd ~/nba_project_ML
   ```

2. Make script executable (first time only):
   ```bash
   chmod +x scripts/deploy_develop.sh
   ```

3. Run deployment:
   ```bash
   ./scripts/deploy_develop.sh
   ```

**What happens:**
- ✅ Syncs code from `origin/feature/fantsay-points-prediction`
- ✅ Builds Docker image
- ✅ Pushes to Artifact Registry with `develop` tag
- ✅ Image URI: `us-central1-docker.pkg.dev/ml-nba-project/nba-docker-repo/nba_project:develop`

### Deploy to Production

1. Navigate to project directory:
   ```bash
   cd ~/nba_project_ML
   ```

2. Make script executable (first time only):
   ```bash
   chmod +x scripts/deploy_production.sh
   ```

3. Run deployment:
   ```bash
   ./scripts/deploy_production.sh
   ```

**What happens:**
- ⚠️ Prompts for confirmation (production deployment)
- ✅ Syncs code from `origin/main`
- ✅ Builds Docker image
- ✅ Pushes to Artifact Registry with `latest` tag
- ✅ Image URI: `us-central1-docker.pkg.dev/ml-nba-project/nba-docker-repo/nba_project:latest`

---

## 📊 Verify Deployment

### List all images in repository:
```bash
gcloud artifacts docker images list \
  us-central1-docker.pkg.dev/ml-nba-project/nba-docker-repo \
  --filter='package=nba_project'
```

### Describe specific image:
```bash
# Develop image
gcloud artifacts docker images describe \
  us-central1-docker.pkg.dev/ml-nba-project/nba-docker-repo/nba_project:develop

# Production image
gcloud artifacts docker images describe \
  us-central1-docker.pkg.dev/ml-nba-project/nba-docker-repo/nba_project:latest
```

### Pull image locally for testing:
```bash
# Pull develop image
docker pull us-central1-docker.pkg.dev/ml-nba-project/nba-docker-repo/nba_project:develop

# Run locally
docker run --rm \
  -e PROCESS=train \
  -e TARGET=fantasy_points \
  us-central1-docker.pkg.dev/ml-nba-project/nba-docker-repo/nba_project:develop
```

---

## 🔄 Typical Workflow

### Feature Development Cycle

1. **Develop feature** on feature branch
   ```bash
   git checkout feature/fantsay-points-prediction
   # Make changes, commit, push
   ```

2. **Deploy to develop**
   ```bash
   ./scripts/deploy_develop.sh
   ```

3. **Test in develop environment**
   - Run Cloud Run jobs with `:develop` tag
   - Verify functionality
   - Check logs and metrics

4. **Merge to main** when ready
   ```bash
   git checkout main
   git merge feature/fantsay-points-prediction
   git push origin main
   ```

5. **Deploy to production**
   ```bash
   ./scripts/deploy_production.sh
   ```

---

## 🏷️ Tagging Strategy

| Environment | Git Branch | Image Tag | Use Case |
|-------------|------------|-----------|----------|
| **Develop** | `feature/*` | `develop` | Testing features before merge |
| **Production** | `main` | `latest` | Live production workloads |

---

## 🐛 Troubleshooting

### Authentication Issues
```bash
# Re-authenticate
gcloud auth login
gcloud auth configure-docker us-central1-docker.pkg.dev
```

### Build Timeout
```bash
# Increase timeout in script (default: 20m)
gcloud builds submit --timeout=30m ...
```

### Permission Denied
```bash
# Check your roles
gcloud projects get-iam-policy ml-nba-project \
  --flatten="bindings[].members" \
  --filter="bindings.members:user:YOUR_EMAIL"
```

### Git Sync Issues
```bash
# Force clean reset
cd ~/nba_project_ML
git fetch origin
git reset --hard origin/feature/fantsay-points-prediction
git clean -fdx
```

---

## 📝 Manual Deployment (Alternative)

If you prefer to run commands manually:

```bash
# 1. Navigate and sync
cd ~/nba_project_ML
git fetch origin
git reset --hard origin/feature/fantsay-points-prediction

# 2. Set variables
export PROJECT_ID="ml-nba-project"
export REGION="us-central1"
export REPO="nba-docker-repo"
export IMAGE="nba_project"
export IMAGE_URI="${REGION}-docker.pkg.dev/${PROJECT_ID}/${REPO}/${IMAGE}"

# 3. Authenticate
gcloud auth configure-docker "${REGION}-docker.pkg.dev"

# 4. Build and push (develop)
gcloud builds submit --tag "${IMAGE_URI}:develop" --project "${PROJECT_ID}"

# OR for production
gcloud builds submit --tag "${IMAGE_URI}:latest" --project "${PROJECT_ID}"
```

---

## 🎯 Next Steps After Deployment

1. **Update Cloud Run job** to use new image tag
2. **Run integration tests** in target environment
3. **Monitor logs** for any issues
4. **Update documentation** if needed

---

## 📚 Related Documentation

- [Google Cloud Artifact Registry](https://cloud.google.com/artifact-registry/docs)
- [Google Cloud Build](https://cloud.google.com/build/docs)
- [Docker Best Practices](https://docs.docker.com/develop/dev-best-practices/)
