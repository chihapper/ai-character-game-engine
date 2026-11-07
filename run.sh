#!/usr/bin/env bash
# Launch the AI Character Game Engine (the port 8000 app) on macOS / Linux.
# Usage:  bash run.sh
set -euo pipefail
cd "$(dirname "$0")"

if [ ! -f .env ]; then
  echo "No .env found. Creating one from .env.example — edit it, add your keys, then re-run ./run.sh"
  cp .env.example .env
  exit 1
fi

if [ ! -d .venv ]; then
  echo "Creating virtual environment..."
  python3 -m venv .venv
fi

# shellcheck disable=SC1091
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt

# Optional extras (voice input + semantic recall). Best-effort: if they fail to
# build, the app still runs text + TTS.
echo "Installing optional extras (voice input + memory)..."
pip install -r requirements-optional.txt || \
  echo "Optional extras not installed — running with text + TTS only. See README."

echo "Starting server on http://127.0.0.1:8000 ..."
python -m orchestrator.main
