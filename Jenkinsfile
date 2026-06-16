pipeline {
    agent any

    environment {
        PYTHONDONTWRITEBYTECODE = '1'
        VENV = '.venv'
    }

    stages {
        stage('Setup') {
            steps {
                sh 'python -m venv ${VENV}'
                sh '${VENV}/bin/python -m pip install --upgrade pip'
                sh '${VENV}/bin/pip install -r requirements.txt'
            }
        }

        stage('Test') {
            steps {
                sh '${VENV}/bin/python -m pytest --junitxml=junit.xml'
            }
        }
    }

    post {
        always {
            junit allowEmptyResults: true, testResults: 'junit.xml'
            archiveArtifacts allowEmptyArchive: true, artifacts: 'coverage.xml,junit.xml'
        }
    }
}
