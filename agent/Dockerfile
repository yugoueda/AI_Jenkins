FROM node:22-bookworm-slim

ARG CLAUDE_CODE_VERSION=2.1.220

ENV PATH="/opt/venv/bin:${PATH}" \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DISABLE_AUTOUPDATER=1

USER root

RUN apt-get update \
    && apt-get install --no-install-recommends -y \
        ca-certificates \
        curl \
        git \
        python3 \
        python3-venv \
        tini \
    && npm install --global "@anthropic-ai/claude-code@${CLAUDE_CODE_VERSION}" \
    && python3 -m venv /opt/venv \
    && rm -rf /var/lib/apt/lists/* /root/.npm

WORKDIR /app

COPY requirements.txt /app/requirements.txt
RUN /opt/venv/bin/pip install --no-cache-dir --upgrade pip \
    && /opt/venv/bin/pip install --no-cache-dir -r /app/requirements.txt

COPY --chown=node:node Src /app/Src
COPY --chown=node:node alembic /app/alembic
COPY --chown=node:node alembic.ini /app/alembic.ini
COPY --chown=node:node .claude /app/.claude

RUN mkdir -p /data /workspace \
    && chown -R node:node /app /data /workspace

ENV PYTHONPATH="/app"

USER node

ENTRYPOINT ["/usr/bin/tini", "--"]
CMD ["python", "-m", "Src.worker"]
