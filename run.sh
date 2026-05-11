#!/bin/bash
cd "$(dirname "$0")"

if ! command -v python3 &>/dev/null; then
  echo "Python 3 is required. Install it from https://python.org"
  exit 1
fi

if [ ! -d ".venv" ]; then
  echo "Setting up virtual environment..."
  python3 -m venv .venv
  .venv/bin/pip install -q -r requirements.txt
fi

echo "Starting Chiro Dashboard at http://localhost:5050"
open http://localhost:5050 2>/dev/null || true
.venv/bin/python server.py
