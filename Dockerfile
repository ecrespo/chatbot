# syntax=docker/dockerfile:1.7
# ---------------------------------------------------------------------
#  Reflex chatbot — production image
#  Build:  docker build -t <user>/reflex-chatbot:latest .
#  Run:    docker run --rm -p 3000:3000 --env-file .env \
#            -e OLLAMA_BASE_URL=http://host.docker.internal:11434/v1 \
#            --add-host host.docker.internal:host-gateway \
#            <user>/reflex-chatbot:latest
# ---------------------------------------------------------------------
ARG PYTHON_VERSION=3.13
ARG UV_VERSION=0.12

FROM ghcr.io/astral-sh/uv:${UV_VERSION} AS uv

FROM python:${PYTHON_VERSION}-slim

LABEL org.opencontainers.image.title="reflex-chatbot" \
      org.opencontainers.image.description="Reflex + assistant-ui chatbot for Ollama, LM Studio, llama.cpp, OpenRouter and OmniRoute" \
      org.opencontainers.image.source="https://github.com/ecrespo/chatbot" \
      org.opencontainers.image.licenses="MIT"

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/app/.venv \
    PATH="/app/.venv/bin:${PATH}" \
    REFLEX_TELEMETRY_ENABLED=false \
    PORT=3000

# curl: healthcheck · unzip: Reflex's bun installer
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl unzip ca-certificates \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --create-home --uid 1000 --shell /bin/sh app

COPY --from=uv /uv /uvx /usr/local/bin/

WORKDIR /app
RUN chown app:app /app
USER app

# 1) Python dependencies (cached layer: only changes with the lockfile)
COPY --chown=app:app pyproject.toml uv.lock ./
RUN uv sync --locked --no-dev --no-install-project

# 2) Application code
COPY --chown=app:app . .

# 3) Install bun + frontend packages and run a first production build, so the
#    container starts quickly and does not need npm at runtime.
RUN reflex export --frontend-only --no-zip --loglevel warning \
    && rm -rf .web/build/client/*.zip

EXPOSE 3000

HEALTHCHECK --interval=30s --timeout=5s --start-period=120s --retries=3 \
    CMD curl -fsS "http://127.0.0.1:${PORT}/ping" || exit 1

ENTRYPOINT ["/app/docker-entrypoint.sh"]
