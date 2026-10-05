#!/usr/bin/env python3
"""Czytanie odpowiedzi Claude Code na głos — hook + sterowanie.

  lektor on | off | status     włącz / wyłącz czytanie (domyślnie włączone)
  lektor stop                  przerwij to, co teraz czyta
  lektor lang auto | pl | en   język czytania (auto = wykryj z odpowiedzi)
  lektor say "tekst"           przeczytaj dowolny tekst
  lektor start | kill          uruchom / zatrzymaj serwer TTS
  lektor hook                  (wywoływane przez Claude Code: Stop / UserPromptSubmit)

Tylko biblioteka standardowa — hook musi startować w milisekundach.
"""

from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent
STATE_DIR = Path.home() / ".lektor"
DISABLED_FLAG = STATE_DIR / "disabled"
PENDING_PATH = STATE_DIR / "pending.txt"
CONFIG_PATH = STATE_DIR / "config.json"
LOG_PATH = STATE_DIR / "server.log"
# Serwer startuje tym samym Pythonem co hook/CLI (venv pluginu albo .venv przy pracy lokalnej)
PYTHON = Path(sys.executable)


def port() -> int:
    try:
        return int(json.loads(CONFIG_PATH.read_text()).get("port", 7862))
    except (OSError, ValueError):
        return 7862


def call(path: str, body: dict | None = None, timeout: float = 0.5) -> dict | None:
    url = f"http://127.0.0.1:{port()}{path}"
    data = json.dumps(body or {}).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read() or b"{}")
    except OSError:
        return None


def start_server() -> None:
    STATE_DIR.mkdir(exist_ok=True)
    with LOG_PATH.open("a") as log:
        subprocess.Popen(
            [str(PYTHON), str(ROOT / "server.py")],
            cwd=ROOT,
            stdout=log,
            stderr=log,
            stdin=subprocess.DEVNULL,
            start_new_session=True,  # przeżyje zamknięcie sesji Claude Code
        )


def speak(text: str, markdown: bool = True) -> None:
    if call("/speak", {"text": text, "markdown": markdown}) is None:
        # Serwer nie działa: zostaw tekst do przeczytania zaraz po starcie
        STATE_DIR.mkdir(exist_ok=True)
        PENDING_PATH.write_text(text)
        start_server()


def hook() -> None:
    try:
        event = json.load(sys.stdin)
    except ValueError:
        return
    name = event.get("hook_event_name")
    if name == "UserPromptSubmit":
        call("/stop", {}, timeout=0.3)  # piszesz dalej — przestań czytać
        return
    if name == "Stop" and not DISABLED_FLAG.exists():
        text = (event.get("last_assistant_message") or "").strip()
        if text:
            speak(text)


def main(argv: list[str]) -> int:
    cmd = argv[1] if len(argv) > 1 else "status"
    if cmd == "hook":
        try:
            hook()
        except Exception:  # noqa: BLE001 — hook nigdy nie może psuć sesji
            pass
        return 0
    if cmd == "on":
        DISABLED_FLAG.unlink(missing_ok=True)
        print("Czytanie odpowiedzi: WŁĄCZONE")
        if call("/health") is None:
            start_server()
            print("Uruchamiam serwer TTS (pierwsze ładowanie modelu ~10–30 s).")
        return 0
    if cmd == "off":
        STATE_DIR.mkdir(exist_ok=True)
        DISABLED_FLAG.touch()
        call("/stop", {})
        print("Czytanie odpowiedzi: WYŁĄCZONE")
        return 0
    if cmd == "lang":
        value = argv[2] if len(argv) > 2 else ""
        if value not in ("auto", "pl", "en"):
            print("Użycie: lektor lang auto | pl | en")
            return 1
        STATE_DIR.mkdir(exist_ok=True)
        try:
            cfg = json.loads(CONFIG_PATH.read_text())
        except (OSError, ValueError):
            cfg = {}
        cfg["language"] = value
        CONFIG_PATH.write_text(json.dumps(cfg, indent=2, ensure_ascii=False) + "\n")
        names = {"auto": "automatycznie (PL/EN)", "pl": "zawsze po polsku", "en": "zawsze po angielsku"}
        print(f"Język czytania: {names[value]}")
        return 0
    if cmd == "stop":
        call("/stop", {})
        return 0
    if cmd == "say":
        text = " ".join(argv[2:]) or sys.stdin.read()
        speak(text)
        return 0
    if cmd == "start":
        if call("/health") is None:
            start_server()
            print("Serwer TTS startuje — postęp: ~/.lektor/server.log")
        else:
            print("Serwer TTS już działa.")
        return 0
    if cmd == "kill":
        h = call("/health")
        if h and h.get("pid"):
            os.kill(int(h["pid"]), signal.SIGTERM)
            print(f"Zatrzymano serwer (pid {h['pid']}).")
        else:
            print("Serwer nie działa.")
        return 0
    if cmd == "status":
        enabled = not DISABLED_FLAG.exists()
        h = call("/health")
        print(f"Czytanie odpowiedzi: {'WŁĄCZONE' if enabled else 'WYŁĄCZONE'}")
        try:
            lang = json.loads(CONFIG_PATH.read_text()).get("language", "auto")
        except (OSError, ValueError):
            lang = "auto"
        print(f"Język: {lang}")
        if h is None:
            print("Serwer TTS: nie działa (wystartuje sam przy pierwszej odpowiedzi)")
        else:
            state = "gotowy" if h.get("ready") else "ładuje model…"
            print(f"Serwer TTS: {state}, silnik {h.get('engine')}, pid {h.get('pid')}"
                  + (", czyta" if h.get("speaking") else ""))
        return 0
    print(__doc__)
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
