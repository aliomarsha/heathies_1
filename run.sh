#!/usr/bin/env bash
# Start Healthies at http://localhost:8000  (Linux / macOS)
set -e
cd "$(dirname "$0")"
if [ ! -d .venv ]; then python3 -m venv .venv; fi
source .venv/bin/activate
pip install -q -r backend/requirements-dev.txt
if [ ! -f frontend/dist/index.html ]; then
  echo "Building the frontend (needs Node.js 18+)..."
  (cd frontend && npm install && npm run build)
fi
cd backend
echo "Healthies running at http://localhost:8000   (model backend: ${HEALTHIES_MODEL_BACKEND:-fixture})"
exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}"
