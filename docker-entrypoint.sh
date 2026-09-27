#!/bin/sh
# Start the chatbot in production mode, frontend and backend on one port.
# The frontend is (re)built at start-up, so REFLEX_API_URL and the like can be
# changed at run time without rebuilding the image.
set -eu

PORT="${PORT:-3000}"

echo "Reflex chatbot · port ${PORT} · provider ${LLM_PROVIDER:-ollama}"
exec reflex run --env prod --single-port --backend-port "${PORT}" \
    --loglevel "${REFLEX_LOGLEVEL:-info}"
