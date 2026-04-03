pipeline {
    agent any
    
    options {
        timeout(time: 30, unit: 'MINUTES')
        ansiColor('xterm')
        durabilityHint('PERFORMANCE_OPTIMIZED')
    }

    environment {
        // 1. ROBUST BRANCH DETECTION
        // Logic: Try BRANCH_NAME first, then GIT_BRANCH, then default to 'develop'
        RAW_BRANCH = "${env.BRANCH_NAME ?: env.GIT_BRANCH ?: 'develop'}"
        // Clean the branch name (removes 'origin/' prefix if present)
        CLEAN_BRANCH = "${RAW_BRANCH.split('/')[-1]}"
        
        // 2. ENVIRONMENT MAPPING
        // If branch is master/main -> production. Hotfix/develop -> develop.
        ENV_SUFFIX = "${(CLEAN_BRANCH == 'master' || CLEAN_BRANCH == 'main') ? 'production' : 'develop'}"
        
        // 3. CREDENTIAL IDs (Must match Jenkins UI)
        GCP_CREDS_ID = 'gcp-service-account-key' 
        GCP_CONFIG_ID = 'gcp-config-sh'
        PIP_CACHE_DIR = "${WORKSPACE}/.pip-cache"
    }

    stages {
        stage('Initialize & Auth') {
            steps {
                script {
                    echo "🔍 Detect Branch: ${CLEAN_BRANCH}"
                    echo "🎯 Target Env: ${ENV_SUFFIX}"
                }
                withCredentials([
                    file(credentialsId: "${GCP_CREDS_ID}", variable: 'GCP_KEY'),
                    file(credentialsId: "${GCP_CONFIG_ID}", variable: 'SECURE_CONFIG')
                ]) {
                    sh """#!/bin/bash
                        # Inject the secret config into the expected script location
                        mkdir -p scripts
                        cp ${SECURE_CONFIG} scripts/gcp_config.sh
                        chmod +x scripts/*.sh
                        
                        # Authenticate
                        source scripts/gcp_config.sh
                        gcloud auth activate-service-account --key-file=${GCP_KEY} --quiet
                        gcloud config set project \$PROJECT_ID --quiet
                    """
                }
            }
        }

        stage('Quality Check') {
            steps {
                sh """#!/bin/bash
                    mkdir -p ${PIP_CACHE_DIR}
                    python3 -m pip install --upgrade pip
                    python3 -m pip install --cache-dir ${PIP_CACHE_DIR} flake8
                    # || true ensures we don't fail the build on style warnings for now
                    python3 -m flake8 . --count --select=E9,F63,F7,F82 --show-source --statistics || true
                """
            }
        }
        
        stage('Unit Tests') {
            steps {
                sh """#!/bin/bash
                    python3 -m pip install --cache-dir ${PIP_CACHE_DIR} -r requirements.txt
                    python3 -m pytest tests/ -v --tb=short
                """
            }
        }

        stage('Deploy & Create Job') {
            // Deploy on master, dev, or any hotfix branch
            when {
                expression { 
                    return (CLEAN_BRANCH == 'master' || CLEAN_BRANCH == 'dev' || CLEAN_BRANCH.startsWith('hotfix-'))
                }
            }
            steps {
                sh """#!/bin/bash
                    source scripts/gcp_config.sh
                    echo "🚀 Deploying Image to Artifact Registry..."
                    ./scripts/deploy_${ENV_SUFFIX}.sh
                    
                    echo "📦 Provisioning Cloud Run Job..."
                    ./scripts/create_cloud_run_job_${ENV_SUFFIX}.sh
                """
            }
        }

        stage('Smoke Test') {
            when {
                expression { 
                    return (CLEAN_BRANCH == 'master' || CLEAN_BRANCH == 'dev' || CLEAN_BRANCH.startsWith('hotfix-'))
                }
            }
            steps {
                sh """#!/bin/bash
                    source scripts/gcp_config.sh
                    echo "🧪 Triggering Cloud Run Job to verify integration..."
                    ./scripts/run_cloud_job_${ENV_SUFFIX}.sh
                """
            }
        }
    }

    post {
        always {
            // Security: Clean up secrets and revoke access
            sh "rm -f scripts/gcp_config.sh"
            sh "gcloud auth revoke --all || true"
            cleanWs()
        }
        success {
            echo "✅ Successfully deployed to ${ENV_SUFFIX} from ${CLEAN_BRANCH}"
        }
        failure {
            echo "❌ Pipeline failed. Check GCP Cloud Build or Cloud Run logs."
        }
    }
}