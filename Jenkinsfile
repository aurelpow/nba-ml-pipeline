pipeline {
    agent any
    
    options {
        timeout(time: 30, unit: 'MINUTES')
        ansiColor('xterm')
    }

    environment {
        // CI/CD Detection (prevents interactive prompts in scripts)
        CI = 'true'
        
        // Map branch to script suffix: master -> production, dev -> develop
        ENV_SUFFIX = "${env.BRANCH_NAME == 'master' ? 'production' : 'develop'}"
        GCP_CREDS_ID = 'gcp-service-account-key' 
        
        // GCP Project Settings (replaces gcp_config.sh for CI/CD)
        PROJECT_ID = 'ml-nba-project'
        REGION = 'us-central1'
        BUCKET_NAME = 'ml-nba-project_cloudbuild'
        MODELS_FOLDER = 'models_trained'
        SERVICE_ACCOUNT = '1098744148287-compute@developer.gserviceaccount.com'
        
        // Artifact Registry
        REPO_NAME = 'nba-docker-repo'
        IMAGE_NAME = 'nba_project'
        PROD_IMAGE_TAG = 'latest'   
        DEV_IMAGE_TAG = 'develop'
        
        // Training Settings
        TARGETS = 'points fantasy_points'
        TUNE_PARAMS = 'false'
        
        // NBA Data Settings
        SEASON = '2025-26'
        SEASON_TYPE = 'Regular Season'
        
        // Secret Manager (secrets are mounted at runtime by Cloud Run)
        NBA_PROXY_USER_SECRET = 'nba-proxy-user'
        NBA_PROXY_PASS_SECRET = 'nba-proxy-pass'
        
        // Compute Resources
        MEMORY = '4Gi'
        CPU = '2'
        TIMEOUT = '3600s'
        MAX_RETRIES = '1'
        
        // Git Branches
        DEV_BRANCH = 'feature/fantsay-points-prediction'
        PROD_BRANCH = 'master'
        
        // Derived Variables
        PROD_IMAGE_URI = "${REGION}-docker.pkg.dev/${PROJECT_ID}/${REPO_NAME}/${IMAGE_NAME}:${PROD_IMAGE_TAG}"
        DEV_IMAGE_URI = "${REGION}-docker.pkg.dev/${PROJECT_ID}/${REPO_NAME}/${IMAGE_NAME}:${DEV_IMAGE_TAG}"
    }

    stages {
        stage('Initialize & Auth') {
            steps {
                // We fetch the Secret File (the config) and the Secret File (the GCP JSON Key)
                withCredentials([
                    file(credentialsId: 'gcp-service-account-key', variable: 'GCP_KEY'),
                    file(credentialsId: 'gcp-config-sh', variable: 'SECURE_CONFIG')
                ]) {
                    script {
                        // 1. Copy the secret file into the location your scripts expect
                        sh "cp \"${SECURE_CONFIG}\" scripts/gcp_config.sh"
                        sh 'chmod +x scripts/*.sh'
                        
                        // 2. Authenticate using the injected config (use bash explicitly)
                        sh '''
                            #!/bin/bash
                            set -e
                            . scripts/gcp_config.sh
                            gcloud auth activate-service-account --key-file="${GCP_KEY}" --quiet
                            gcloud config set project "${PROJECT_ID}" --quiet
                        '''.stripIndent()
                    }
                }
            }
        }

        stage('Quality Check') {
            steps {
                sh """#!/bin/bash
                    python3 -m venv venv
                    source venv/bin/activate
                    pip install pytest flake8
                    # Allowing the pipeline to continue even if linting fails
                    flake8 . --count --select=E9,F63,F7,F82 --show-source --statistics || true
                """
            }
        }

        stage('Deploy & Create Job') {
            when { 
                anyOf { branch 'master'; branch 'dev'; branch 'feature/jenkins-integration' } 
            }
            steps {
                script {
                    echo "🚀 Executing deployment for ${ENV_SUFFIX} environment"
                    sh "./scripts/deploy_${ENV_SUFFIX}.sh"
                    sh "./scripts/create_cloud_run_job_${ENV_SUFFIX}.sh"
                }
            }
        }

        stage('Smoke Test') {
            when { 
                anyOf { branch 'master'; branch 'dev'; branch 'feature/jenkins-integration' } 
            }
            steps {
                echo "🧪 Triggering Cloud Run Job to verify integration..."
                sh "./scripts/run_cloud_job_${ENV_SUFFIX}.sh"
            }
        }
    }

    post {
        success {
            echo "✅ Pipeline completed successfully for ${env.BRANCH_NAME}"
        }
        failure {
            echo "❌ Pipeline failed. Check Cloud Run logs or Jenkins console output."
        }
        always {
            sh "gcloud auth revoke --all || true"
            cleanWs()
        }
    }
}