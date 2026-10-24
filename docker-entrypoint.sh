#!/bin/sh
# Start the chatbot in production mode, frontend and backend on one port.
# The frontend is (re)built at start-up, so REFLEX_API_URL and the like can be
# changed at run time without rebuilding the image.
set -eu

PORT="${PORT:-3000}"

# Empty/unset OLLAMA_BASE_URL: use the compose `ollama` service when it exists
# (profiles `ollama` / `ollama-gpu`), otherwise Ollama on the Docker host.
if [ -z "${OLLAMA_BASE_URL:-}" ]; then
    if getent hosts ollama >/dev/null 2>&1; then
        OLLAMA_BASE_URL="http://ollama:11434/v1"
    else
        OLLAMA_BASE_URL="http://host.docker.internal:11434/v1"
    fi
    export OLLAMA_BASE_URL
fi

echo "Reflex chatbot · port ${PORT} · provider ${LLM_PROVIDER:-ollama} · ollama ${OLLAMA_BASE_URL}"
exec reflex run --env prod --single-port --backend-port "${PORT}" \
    --loglevel "${REFLEX_LOGLEVEL:-info}"
