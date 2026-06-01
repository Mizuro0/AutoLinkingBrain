#!/usr/bin/env sh
cd "$(dirname "$0")"
export PYTHONIOENCODING=utf-8

if [ -x ".venv/bin/python" ]; then
  PY=".venv/bin/python"
else
  PY="python3"
fi

if [ $# -eq 0 ]; then
  exec "$PY" brain.py start
fi

exec "$PY" brain.py "$@"
