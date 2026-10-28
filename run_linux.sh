#!/usr/bin/env bash
cd "$(dirname "$0")"
PY=python3
if ! $PY -c "import PySide6, spellchecker" 2>/dev/null; then
  if [ -d .venv ] || ! $PY -m pip install --user -r requirements.txt 2>/dev/null; then
    [ -d .venv ] || $PY -m venv .venv
    PY=.venv/bin/python
    $PY -c "import PySide6, spellchecker" 2>/dev/null || $PY -m pip install -r requirements.txt
  fi
fi
[ -x .venv/bin/python ] && PY=.venv/bin/python
exec $PY run.py "$@"
