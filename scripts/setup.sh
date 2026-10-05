#!/bin/bash
# Instalacja zależności Pythona do katalogu danych pluginu (SessionStart, w tle).
# Wywołanie: setup.sh <CLAUDE_PLUGIN_ROOT> <CLAUDE_PLUGIN_DATA>
set -u
ROOT="$1"
DATA="$2"
STATE="$HOME/.lektor"
mkdir -p "$DATA" "$STATE/bin"
LOG="$STATE/setup.log"

# Wrapper CLI pod stałą ścieżką — używa go /czytaj i można go dodać do PATH
cat > "$STATE/bin/lektor" <<WRAP
#!/bin/bash
exec "$DATA/venv/bin/python" "$ROOT/lektor.py" "\$@"
WRAP
chmod +x "$STATE/bin/lektor"

# Zależności instalujemy tylko przy pierwszym uruchomieniu i po zmianie uv.lock
if cmp -s "$ROOT/uv.lock" "$DATA/uv.lock" && [ -x "$DATA/venv/bin/python" ]; then
  exit 0
fi

if [ "$(uname -s)-$(uname -m)" != "Darwin-arm64" ]; then
  echo "$(date) lektor wymaga macOS na Apple Silicon (MLX)." >> "$LOG"
  exit 0
fi

UV=""
for c in "$(command -v uv 2>/dev/null)" "$HOME/.local/bin/uv" "$HOME/.cargo/bin/uv" /opt/homebrew/bin/uv /usr/local/bin/uv; do
  if [ -n "$c" ] && [ -x "$c" ]; then UV="$c"; break; fi
done
if [ -z "$UV" ]; then
  echo "$(date) Brak uv. Zainstaluj: brew install uv  (albo https://docs.astral.sh/uv/)" >> "$LOG"
  exit 0
fi

# Jedna instalacja naraz (kilka sesji może wystartować równocześnie)
LOCK="$DATA/.setup.lock"
if ! mkdir "$LOCK" 2>/dev/null; then exit 0; fi
trap 'rmdir "$LOCK"' EXIT

echo "$(date) instaluję zależności (uv sync)…" >> "$LOG"
if UV_PROJECT_ENVIRONMENT="$DATA/venv" "$UV" sync --frozen --no-dev --project "$ROOT" >> "$LOG" 2>&1; then
  cp "$ROOT/uv.lock" "$DATA/uv.lock"
  echo "$(date) gotowe" >> "$LOG"
else
  echo "$(date) BŁĄD uv sync — szczegóły powyżej" >> "$LOG"
fi
exit 0
