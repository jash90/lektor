#!/bin/bash
# Hook Stop / UserPromptSubmit. Dopóki setup.sh nie skończył instalacji — nic nie rób.
PY="$2/venv/bin/python"
[ -x "$PY" ] || exit 0
exec "$PY" "$1/lektor.py" hook
