# Jenkins CI/CD Setup for NBA ML Project

To run Jenkins locally with all the tools required by the pipeline (`docker`, `gcloud`, `python`), use the following setup. 

All Jenkins configuration files are located in the `jenkins/` directory to keep the root clean.

## 1. Jenkins Files Location
- `jenkins/Jenkins.Dockerfile`: Custom image with GCP and Docker tools.
- `jenkins/docker-compose.yml`: Standard compose to launch Jenkins.

## 2. Running Jenkins

1.  Navigate to the jenkins directory:
    ```bash
    cd jenkins
    ```
2.  Start the container:
    ```bash
    docker-compose up -d --build
    ```
3.  Access Jenkins at `http://localhost:8080`.

## 3. Pipeline Configuration
- Keep the `Jenkinsfile` at the **root** of the project (Jenkins expects this by default).
- Create a new 'Pipeline' job in Jenkins.
- Use 'Pipeline script from SCM'.
- Add your **GCP Service Account Key** as a 'Secret File' credential named `gcp-service-account-key`.

