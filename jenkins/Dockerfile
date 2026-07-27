ARG JENKINS_BASE_IMAGE=jenkins/jenkins:2.568.1-jdk21
FROM ${JENKINS_BASE_IMAGE}

USER root

RUN apt-get update \
    && apt-get install --no-install-recommends -y \
        ca-certificates \
        curl \
        git \
        lsb-release \
        python3 \
        python3-pip \
        python3-venv \
        python-is-python3 \
    && install -m 0755 -d /etc/apt/keyrings \
    && curl -fsSL https://download.docker.com/linux/debian/gpg \
        -o /etc/apt/keyrings/docker.asc \
    && chmod a+r /etc/apt/keyrings/docker.asc \
    && echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/debian $(. /etc/os-release && echo "$VERSION_CODENAME") stable" \
        > /etc/apt/sources.list.d/docker.list \
    && apt-get update \
    && apt-get install --no-install-recommends -y docker-ce-cli \
    && rm -rf /var/lib/apt/lists/*

COPY --chown=jenkins:jenkins jenkins/plugins.txt /usr/share/jenkins/ref/plugins.txt

USER jenkins

RUN jenkins-plugin-cli --plugin-file /usr/share/jenkins/ref/plugins.txt
