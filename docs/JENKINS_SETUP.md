# Jenkins CI/CD Setup for NBA ML Project

Step-by-step guide to run Jenkins locally and have it test, build and deploy the pipeline to Google Cloud Run. For a conceptual overview (architecture, production alternatives, troubleshooting) see [jenkins/README.md](../jenkins/README.md).

## What the pipeline does

The root [Jenkinsfile](../Jenkinsfile) runs these stages:

| Stage | What it does |
|---|---|
| Initialize & Auth | Copies the `gcp-config-sh` credential to `scripts/gcp_config.sh`, then logs in to GCP with the `gcp-service-account-key` credential |
| Setup Python | Creates a venv and installs `requirements.txt` |
| Quality Check | `flake8` (non-blocking) |
| Unit Tests | `pytest tests/` |
| Deploy & Create Job | `scripts/deploy_<env>.sh` (Cloud Build to Artifact Registry), then `scripts/create_cloud_run_job_<env>.sh` |
| Smoke Test | `scripts/run_cloud_job_<env>.sh` executes the Cloud Run Job and prints its logs |

Branch to environment mapping:

| Branch | Environment | Deploys? |
|---|---|---|
| `master` / `main` | `production` | Yes |
| `dev`, `hotfix-*`, `feature/*` | `develop` | Yes |
| anything else | `develop` | No (tests only) |

> **Warning:** a build on `master` deploys to production and executes the production Cloud Run Job. Always validate on `dev` first.

## 1. Start Jenkins

Jenkins runs in Docker with `docker`, `gcloud` and `python` preinstalled ([jenkins/Jenkins.Dockerfile](../jenkins/Jenkins.Dockerfile)).

```bash
cd jenkins
docker compose up -d --build
```

Open http://localhost:8080. On first start, unlock it with:

```bash
docker exec jenkins cat /var/jenkins_home/secrets/initialAdminPassword
```

Then choose **Install suggested plugins** (this includes AnsiColor, which the Jenkinsfile needs) and create an admin user.

The `jenkins_jenkins_home` Docker volume holds jobs and credentials, so they survive container restarts. Do not run `docker compose down -v` unless you want to start over.

## 2. Create the GCP service account key (`gcp-service-account-key`)

Jenkins should authenticate with a dedicated service account, not your user account and not the Cloud Run runtime account. Run these once, as a user with IAM admin rights on the project:

```bash
PROJECT_ID=ml-nba-project            # value of PROJECT_ID in gcp_config.sh
SA_NAME=jenkins-ci
SA_EMAIL=${SA_NAME}@${PROJECT_ID}.iam.gserviceaccount.com
RUNTIME_SA=<SERVICE_ACCOUNT from gcp_config.sh>   # the account the Cloud Run Job runs as
BUCKET=<BUCKET_NAME from gcp_config.sh>           # Cloud Build source bucket

# 1. Create the service account
gcloud iam service-accounts create $SA_NAME \
  --project=$PROJECT_ID --display-name="Jenkins CI/CD"

# 2. Grant the project-level roles the scripts need
for ROLE in \
  roles/cloudbuild.builds.editor \
  roles/artifactregistry.writer \
  roles/run.developer \
  roles/logging.viewer \
  roles/serviceusage.serviceUsageConsumer; do
  gcloud projects add-iam-policy-binding $PROJECT_ID \
    --member="serviceAccount:$SA_EMAIL" --role="$ROLE" --condition=None
done

# 3. Allow uploading the build source to the Cloud Build bucket
gcloud storage buckets add-iam-policy-binding gs://$BUCKET \
  --member="serviceAccount:$SA_EMAIL" --role=roles/storage.objectAdmin

# 4. Allow Jenkins to deploy Cloud Run Jobs that run as the runtime account
gcloud iam service-accounts add-iam-policy-binding $RUNTIME_SA \
  --project=$PROJECT_ID \
  --member="serviceAccount:$SA_EMAIL" --role=roles/iam.serviceAccountUser

# 5. Create the key file
gcloud iam service-accounts keys create jenkins-ci-key.json \
  --iam-account=$SA_EMAIL --project=$PROJECT_ID
```

Why each role is needed:

| Role | Used by |
|---|---|
| `cloudbuild.builds.editor` | `gcloud builds submit` in `deploy_*.sh` |
| `artifactregistry.writer` | pushing the image to Artifact Registry |
| `run.developer` | creating, updating and executing Cloud Run Jobs |
| `logging.viewer` | `gcloud logging read` in `run_cloud_job_*.sh` |
| `serviceusage.serviceUsageConsumer` | calling GCP APIs on the project |
| `storage.objectAdmin` on the bucket | uploading the source tarball for Cloud Build |
| `iam.serviceAccountUser` on the runtime account | `--service-account` in `create_cloud_run_job_*.sh` |

If a stage fails with `PERMISSION_DENIED`, the error names the missing permission. Add the matching role.

**Handle the key like a password.** `jenkins-ci-key.json` is a long-lived credential. Upload it to Jenkins (step 3), then delete the local copy. Never commit it. You can list or revoke keys later with `gcloud iam service-accounts keys list|delete`.

## 3. Add credentials in Jenkins

**Manage Jenkins -> Credentials -> System -> Global credentials -> Add Credentials.** The IDs must match the Jenkinsfile exactly.

| Kind | ID | Content |
|---|---|---|
| Secret file | `gcp-service-account-key` | `jenkins-ci-key.json` from step 2 |
| Secret file | `gcp-config-sh` | your local `scripts/gcp_config.sh` (gitignored, copy from `gcp_config.sh.example` if needed) |
| Username with password | `github-token` | GitHub username and a PAT with `repo` scope. Only needed if the repo is private |

Re-upload `gcp-config-sh` every time you change `gcp_config.sh` (for example when bumping `SEASON`). Jenkins uses its stored copy, not the file on your disk.

## 4. Create the pipeline job

Use a **Multibranch Pipeline**. A plain Pipeline job also works, but it will not map branches to environments as cleanly.

1. **New Item**, name `NBA-ML-Pipeline`, type **Multibranch Pipeline**, OK.
2. **Branch Sources -> Add source -> Git**
   - Project Repository: `https://github.com/aurelpow/nba-ml-pipeline.git`
   - Credentials: `github-token` (leave empty for a public repo)
3. **Behaviours:** keep **Discover branches**, then add **Filter by name (with regular expression)** with `(dev|master|feature/.*)`. `feature/*` branches are treated as `dev` (develop environment).
4. **Build Configuration:** Mode `by Jenkinsfile`, Script Path `Jenkinsfile`.
5. **Scan Multibranch Pipeline Triggers:** tick *Periodically if not otherwise run*, interval 5 minutes.
6. **Save.** Jenkins scans the repository and creates one job per matching branch.

## 5. Run it

1. Open `NBA-ML-Pipeline -> dev -> Build Now`.
2. Open the build, then **Console Output**, and watch the stages.
3. When `dev` is green, merge to `master`. Jenkins picks it up on the next scan and deploys to production.

After the first successful build, every push to `dev` or `master` is built automatically (within 5 minutes).

## Troubleshooting

| Symptom | Fix |
|---|---|
| `Invalid option type "ansiColor"` | Install the **AnsiColor** plugin (Manage Jenkins -> Plugins) |
| `Could not find credentials entry with ID ...` | A credential ID is misspelled or missing. Compare with step 3 |
| `PERMISSION_DENIED` in a deploy stage | Add the role named in the error to `jenkins-ci` (step 2) |
| `iam.serviceaccounts.actAs` denied | Missing `roles/iam.serviceAccountUser` on the runtime account (step 2, point 4) |
| Unit Tests fail only in Jenkins | Jenkins runs on a clean checkout. Tests must not depend on local `databases/*.csv` |
| Job deployed but no predictions | Check `SEASON` in `gcp_config.sh` and the deployed job's env vars. A stale season makes the games gate report "no games" |
| Docker permission denied | The Jenkins container needs `/var/run/docker.sock` mounted (already set in [docker-compose.yml](../jenkins/docker-compose.yml)) |

Useful commands:

```bash
docker logs -f jenkins        # Jenkins server log
docker compose -f jenkins/docker-compose.yml restart
docker compose -f jenkins/docker-compose.yml down   # stop, keep data
```
