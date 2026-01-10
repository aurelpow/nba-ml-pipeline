# Jenkins CI/CD Setup for NBA ML Pipeline

Complete guide for setting up continuous integration and deployment using Jenkins.

---

## 📋 Table of Contents
- [Current Implementation (Local)](#current-implementation-local)
- [How It Works](#how-it-works)
- [Setup Instructions](#setup-instructions)
- [Triggering Pipelines](#triggering-pipelines)
- [Production Alternatives](#production-alternatives)
- [Troubleshooting](#troubleshooting)

---

## Current Implementation (Local)

### Architecture Overview
```
Local Machine (Windows/Mac/Linux)
    ↓
Docker Container (Jenkins)
    ↓
GitHub Repository (nba-ml-pipeline)
    ↓
Google Cloud Platform
    ├─ Cloud Build (Image Building)
    ├─ Artifact Registry (Image Storage)
    └─ Cloud Run Jobs (ML Training)
```

### ⚠️ Limitations of Local Setup
- ❌ **Requires computer to be running** - No automation when machine is off
- ❌ **Single-user access** - Team members can't trigger builds
- ❌ **No mobile access** - Can't merge PRs and auto-deploy from phone
- ✅ **Zero infrastructure costs** - Only pay for GCP compute time
- ✅ **Full control** - Complete visibility into build process
- ✅ **Quick to setup** - No cloud provisioning required

---

## How It Works

### Pipeline Stages

#### 1. **Initialize & Auth**
- Detects branch (`dev`, `master`, or feature branch)
- Authenticates with Google Cloud using service account key
- Loads configuration from secure credentials

#### 2. **Quality Check**
- Runs `flake8` linting for Python syntax errors
- Non-blocking (continues even if warnings found)

#### 3. **Deploy & Create Job** (only on `dev`/`master`)
- Builds Docker image using **Google Cloud Build**
- Pushes to Artifact Registry
- Creates/updates Cloud Run Job with latest configuration

#### 4. **Smoke Test** (only on `dev`/`master`)
- Triggers Cloud Run Job to verify deployment
- Ensures ML pipeline can execute end-to-end

### Branch → Environment Mapping

| Branch | Environment | Image Tag | Cloud Run Job |
|--------|-------------|-----------|---------------|
| `dev` | Develop | `develop` | `nba-training-develop` |
| `master` | Production | `latest` | `nba-training-prod` |
| `feature/*` | ❌ No deploy | - | Quality checks only |

---

## Setup Instructions

### Prerequisites
- Docker Desktop installed and running
- Google Cloud account with project setup
- GitHub repository access
- GCP service account JSON key

### 1. Start Jenkins Container

```bash
cd jenkins
docker-compose up -d
```

Access Jenkins at: `http://localhost:8080`

### 2. Initial Jenkins Configuration

1. **Unlock Jenkins:**
   ```bash
   docker exec jenkins cat /var/jenkins_home/secrets/initialAdminPassword
   ```
   Copy the password and paste in the web UI.

2. **Install Suggested Plugins** (or skip and install manually later)

3. **Create Admin User** (save credentials securely)

### 3. Add Credentials

Go to **Manage Jenkins → Credentials → System → Global credentials**

#### a) GCP Service Account Key
- **Kind:** Secret file
- **ID:** `gcp-service-account-key`
- **File:** Upload your GCP JSON key (`ml-nba-project-xxxxx.json`)

#### b) GCP Configuration File
- **Kind:** Secret file
- **ID:** `gcp-config-sh`
- **File:** Upload your `scripts/gcp_config.sh`

#### c) GitHub Token
- **Kind:** Username with password
- **ID:** `github-token`
- **Username:** Your GitHub username
- **Password:** Personal Access Token (PAT) with `repo` scope

### 4. Create Multibranch Pipeline (Recommended)

**Why Multibranch?**
- ✅ Automatically discovers branches with Jenkinsfiles
- ✅ Ignores branches without Jenkinsfiles (no errors)
- ✅ Auto-removes deleted branches
- ✅ Cleaner management for multiple environments

**Setup:**

1. **New Item** → **Multibranch Pipeline**
2. **Name:** `NBA-ML-Pipeline`
3. Click **OK**

**Configure Branch Sources:**

4. **Branch Sources** → **Add source** → **Git**
5. **Project Repository:**
   ```
   https://github.com/aurelpow/nba-ml-pipeline.git
   ```
6. **Credentials:** Select `github-token`

**Configure Branch Discovery:**

7. **Behaviors** → **Add** → **"Discover branches"**
   - **Strategy:** All branches

8. **Behaviors** → **Add** → **"Filter by name (with regular expression)"**
   - **Regular expression:**
     ```
     (dev|master)
     ```
   - This ensures only `dev` and `master` branches trigger builds

**Build Configuration:**

9. **Build Configuration:**
   - **Mode:** by Jenkinsfile
   - **Script Path:** `Jenkinsfile`

**Scan Trigger:**

10. **Scan Multibranch Pipeline Triggers:**
    - ✅ Enable: "Periodically if not otherwise run"
    - **Interval:** `5 minutes`

11. Click **Save**

Jenkins will immediately scan your repository and create sub-jobs for each matching branch.

---

## Triggering Pipelines

### Manual Trigger
1. Go to Jenkins dashboard
2. Click on **NBA-ML-Pipeline**
3. Click on the branch (e.g., **dev**)
4. Click **"Build Now"**

### Automatic Trigger (Periodic Scanning)

The multibranch pipeline **automatically scans** for changes (configured in step 10 above).

**How it works:**
- Every 5 minutes, Jenkins scans the GitHub repository
- Detects new commits on `dev` or `master` branches
- Automatically triggers builds for changed branches
- Also discovers new branches matching the regex filter

**View scan activity:**
- Go to **NBA-ML-Pipeline** main page
- Click **"Scan Repository Log"** (left sidebar)
- See timestamps of scans and detected changes

**Manual scan:**
- Click **"Scan Repository Now"** to trigger immediate scan

### Expected Pipeline Structure

After setup, your Jenkins dashboard shows:

```
NBA-ML-Pipeline (Multibranch Pipeline)
  ├─ dev
  │   └─ #1, #2, #3... (build history)
  └─ master (appears after Jenkinsfile is merged)
      └─ #1, #2, #3... (build history)
```

**Branch Status:**
- ✅ **Green** - Build successful, deployed to environment
- ❌ **Red** - Build failed, check console output
- ⏸️ **Gray** - Not built yet (no Jenkinsfile found)

**⚠️ Limitations:**
- Your computer must be running for polling to work
- 5-minute delay between push and build (vs instant with webhooks)
- Uses GitHub API quota (shouldn't be an issue for normal use)

### ❌ Why GitHub Webhooks Don't Work Here

**GitHub Webhook Requirements:**
- Jenkins must be **publicly accessible** via internet
- Requires public IP or domain (e.g., `https://jenkins.example.com`)
- GitHub sends HTTP POST to your Jenkins URL on every push

**Your Current Setup:**
- Jenkins runs on `localhost:8080` (only accessible from your machine)
- Behind NAT/firewall with private IP
- No public endpoint for GitHub to reach

**To Enable Webhooks, You Need:**
1. **Port forwarding** on your router (exposes your machine - security risk)
2. **ngrok** tunnel (temporary public URL - free tier limited)
3. **Cloud-hosted Jenkins** (see Production Alternatives below)

---

## Production Alternatives

### Option 1: GitHub Actions ⭐

**Cost:** Free for public repos (2000 minutes/month)

**Pros:**
- ✅ Always available (GitHub-hosted)
- ✅ Zero infrastructure management
- ✅ Native GitHub integration
- ✅ Works from any device

**Cons:**
- ❌ Must convert Jenkinsfile to YAML
- ❌ Limited to GitHub ecosystem

**Migration Effort:** ~1-2 hours

---

### Option 2: Jenkins on Google Compute Engine

**Cost:** ~$15-30/month (e2-small instance)

**Setup:**
```bash
# Create VM
gcloud compute instances create jenkins-server \
  --zone=us-central1-a \
  --machine-type=e2-small \
  --image-family=ubuntu-2204-lts \
  --image-project=ubuntu-os-cloud

# Install Docker & Jenkins (same as local)
# Open firewall port 8080
# Configure static IP
```

**Pros:**
- ✅ Always available
- ✅ Keep existing Jenkinsfile
- ✅ Full control

**Cons:**
- ❌ Monthly infrastructure cost
- ❌ Must manage VM (updates, backups)
- ❌ Security configuration required

---

### Option 3: Google Cloud Build Triggers

**Cost:** First 120 build-minutes/day free, then $0.003/minute

**Setup:**
1. Go to Cloud Build → Triggers
2. Connect GitHub repository
3. Create trigger for `dev` and `master` branches
4. Use `cloudbuild.yaml` (similar to Jenkinsfile)

**Pros:**
- ✅ Integrated with GCP
- ✅ Pay-per-use pricing
- ✅ No server management

**Cons:**
- ❌ Must convert Jenkinsfile to cloudbuild.yaml
- ❌ Tied to GCP ecosystem

**Migration Effort:** ~2-3 hours

---

### Option 4: Managed Jenkins (CloudBees)

**Cost:** Starts at $75/month (hobby tier)

**Pros:**
- ✅ Enterprise-grade Jenkins
- ✅ No infrastructure management
- ✅ Keep Jenkinsfile unchanged

**Cons:**
- ❌ Expensive for solo developers
- ❌ Overkill for small projects

---

## Cost Comparison Table

| Solution | Monthly Cost | Setup Time | Always Available | Maintenance |
|----------|--------------|------------|------------------|-------------|
| **Local Jenkins** | $0 | 30 min | ❌ | Low |
| **GitHub Actions** | $0 (public) | 1-2 hrs | ✅ | None |
| **GCE VM** | $15-30 | 1-2 hrs | ✅ | Medium |
| **Cloud Build** | ~$5-15 | 2-3 hrs | ✅ | Low |
| **CloudBees CI** | $75+ | 1 hr | ✅ | None |

---

## Troubleshooting

### No Branches Showing in Multibranch Pipeline
**Symptom:** Multibranch pipeline created but no branches appear

**Solution:**
1. Click **"Scan Repository Now"**
2. Check **"Scan Repository Log"** for errors
3. Verify GitHub credentials are correct
4. Ensure regex filter `(dev|master)` matches your branch names

### Branch Shows But Not Building
**Symptom:** Branch appears but no builds triggered

**Solution:**
- Gray status = No Jenkinsfile found in that branch
- Push Jenkinsfile to the branch
- Click **"Scan Repository Now"** to refresh

### Multiple Pipelines Conflicting
**Symptom:** Getting "Changes found" but builds fail

**Solution:**
- Delete old single-branch pipeline jobs
- Keep only the multibranch pipeline
- Disable "Poll SCM" on old jobs before deleting

### Jenkins Not Starting
```bash
# Check container status
docker ps -a

# View logs
docker logs jenkins

# Restart container
docker-compose restart
```

### Pipeline Fails at GCP Auth
- Verify `gcp-service-account-key` credential is uploaded correctly
- Check service account has required permissions:
  - Cloud Build Editor
  - Artifact Registry Writer
  - Cloud Run Admin
  - Storage Object Admin

### Image Build Fails
```bash
# Test locally
gcloud builds submit --tag=us-central1-docker.pkg.dev/ml-nba-project/nba-docker-repo/nba_project:test

# Check Cloud Build logs in GCP Console
```

### Periodic Scanning Not Working
**Symptom:** Repository not being scanned automatically

**Solution:**
1. Configure → **Scan Multibranch Pipeline Triggers**
2. Enable "Periodically if not otherwise run"
3. Set interval to `5 minutes`
4. Check **"Scan Repository Log"** for scan history

### "Permission Denied" on Scripts
```bash
# Fix inside Jenkins pipeline
sh "chmod +x scripts/*.sh"
```

---

## Security Best Practices

1. **Never commit secrets:**
   - `gcp_config.sh` is gitignored ✅
   - Service account keys in Jenkins credentials only ✅

2. **Rotate credentials regularly:**
   - Service account keys every 90 days
   - GitHub PAT annually

3. **Limit service account permissions:**
   - Use principle of least privilege
   - Separate dev/prod service accounts

4. **Enable 2FA:**
   - Jenkins admin account
   - GitHub account
   - GCP account

---

## Next Steps

- [ ] Merge `feature/jenkins-integration` to `dev`
- [ ] Test automatic trigger on `dev` branch
- [ ] Monitor first production deployment to `master`
- [ ] Consider migration to GitHub Actions for 24/7 availability

---

## Resources

- [Jenkins Documentation](https://www.jenkins.io/doc/)
- [Google Cloud Build](https://cloud.google.com/build/docs)
- [GitHub Actions Guide](https://docs.github.com/en/actions)
- [Jenkinsfile Reference](https://www.jenkins.io/doc/book/pipeline/syntax/)
