"""Serwer czytania na głos dla Claude Code (Chatterbox Multilingual v3 / Piper, lokalnie).

  uv run server.py            # nasłuch na 127.0.0.1:7862

POST /speak  {"text": "...", "markdown": true}  — przeczytaj (przerywa to, co aktualnie czyta)
POST /stop                                      — przerwij czytanie
GET  /health                                    — stan serwera
"""

from __future__ import annotations

import json
import os
import queue
import subprocess
import tempfile
import subprocess
import tempfile
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import numpy as np
import soundfile as sf

import re

from lang import detect_language, polonize
from speech_text import split_for_tts, to_speech

ROOT = Path(__file__).parent
STATE_DIR = Path.home() / ".lektor"
CONFIG_PATH = STATE_DIR / "config.json"
PENDING_PATH = STATE_DIR / "pending.txt"
LOG_PATH = STATE_DIR / "server.log"

DEFAULT_CONFIG = {
    "port": 7862,
    "engine": "chatterbox",  # chatterbox | piper
    "voice": str(ROOT / "voices" / "fleurs_kobieta.wav"),
    "piper_voice": "",  # ścieżka do głosu .onnx, np. pl_PL-gosia-medium.onnx (rhasspy/piper-voices)
    "exaggeration": 0.5,
    "cfg_weight": 0.5,
    "max_chars": 1500,
    "speed": 1.0,  # tylko Piper (Chatterbox nie obsługuje zmiany tempa)
    "language": "auto",  # auto | pl | en
    "english_in_polish": "phonetic",  # phonetic (angielskie wtrącenia zapisane po polsku) | off
}


def prepare(md: str, cfg: dict) -> tuple[str, str]:
    """Markdown -> (tekst do przeczytania, język)."""
    lang = cfg["language"]
    if lang not in ("pl", "en"):
        prose = re.sub(r"```.*?(```|$)", " ", md, flags=re.S)
        lang = detect_language(prose) if prose.strip() else "pl"
    return to_speech(md, cfg["max_chars"], lang), lang


def load_config() -> dict:
    cfg = dict(DEFAULT_CONFIG)
    try:
        cfg.update(json.loads(CONFIG_PATH.read_text()))
    except (OSError, ValueError):
        pass
    for key in ("voice", "piper_voice"):
        cfg[key] = os.path.expanduser(cfg[key])
    return cfg


def log(msg: str) -> None:
    STATE_DIR.mkdir(exist_ok=True)
    with LOG_PATH.open("a") as f:
        f.write(f"{time.strftime('%H:%M:%S')} {msg}\n")


class Speaker:
    """Dwa wątki: generator (cały MLX w jednym wątku) i odtwarzacz.

    `epoch` rośnie przy każdym przerwaniu — stare fragmenty są wtedy porzucane.
    """

    def __init__(self, cfg: dict):
        self.cfg = cfg
        self.jobs: queue.Queue[tuple[int, str, str]] = queue.Queue()
        self.audio: queue.Queue[tuple[int, np.ndarray, int]] = queue.Queue(maxsize=3)
        self.epoch = 0
        self.lock = threading.Lock()
        self.ready = threading.Event()
        self.speaking = False
        self.player_proc: subprocess.Popen | None = None
        self.model = None
        threading.Thread(target=self._generator, daemon=True, name="tts-gen").start()
        threading.Thread(target=self._player, daemon=True, name="tts-play").start()

    # --- sterowanie ---

    def interrupt(self) -> None:
        with self.lock:
            self.epoch += 1
        for q in (self.jobs, self.audio):
            while True:
                try:
                    q.get_nowait()
                except queue.Empty:
                    break
        proc = self.player_proc
        if proc and proc.poll() is None:
            proc.terminate()

    def say(self, text: str, lang: str = "pl") -> None:
        self.interrupt()
        with self.lock:
            self.jobs.put((self.epoch, text, lang))

    # --- silniki ---

    def _load(self) -> None:
        t = time.time()
        if self.cfg["engine"] == "piper":
            from piper import PiperVoice

            self.model = PiperVoice.load(self.cfg["piper_voice"])
        else:
            from mlx_audio.tts.utils import load_model

            self.model = load_model("mlx-community/chatterbox-multilingual-v3")
            # Głos referencyjny liczymy raz — inaczej każde zdanie płaci ~2–3 s narzutu
            self.conds = self.model.prepare_conditionals(
                self.cfg["voice"], 24_000, self.cfg["exaggeration"]
            )
            self._synth("Gotowe.", "pl")  # rozgrzewka kerneli Metal
        log(f"model {self.cfg['engine']} załadowany w {time.time() - t:.1f} s")
        self.ready.set()

    def _synth(self, text: str, lang: str) -> tuple[np.ndarray, int]:
        if self.cfg["engine"] == "piper":
            import io
            import wave

            from piper import SynthesisConfig

            buf = io.BytesIO()
            with wave.open(buf, "wb") as w:
                self.model.synthesize_wav(
                    text, w, syn_config=SynthesisConfig(length_scale=1 / self.cfg["speed"])
                )
            buf.seek(0)
            with wave.open(buf) as w:
                pcm = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16)
                return pcm.astype(np.float32) / 32768.0, w.getframerate()

        parts = [
            np.array(r.audio, dtype=np.float32).reshape(-1)
            for r in self.model.generate(
                text,
                lang_code=lang,
                conds=self.conds,
                exaggeration=self.cfg["exaggeration"],
                cfg_weight=self.cfg["cfg_weight"],
                verbose=False,
            )
        ]
        audio = np.concatenate(parts) if parts else np.zeros(0, dtype=np.float32)
        return audio, self.model.sample_rate

    # --- wątki ---

    def _generator(self) -> None:
        try:
            self._load()
        except Exception as e:  # noqa: BLE001
            log(f"BŁĄD ładowania modelu: {e!r}")
            return
        while True:
            epoch, text, lang = self.jobs.get()
            chunks = split_for_tts(text)
            phonetic = lang == "pl" and load_config()["english_in_polish"] == "phonetic"
            log(f"czytam [{lang}] {len(text)} znaków w {len(chunks)} kawałkach")
            for chunk in chunks:
                if epoch != self.epoch:
                    break
                t = time.time()
                try:
                    spoken = polonize(chunk) if phonetic else chunk
                    audio, sr = self._synth(spoken, lang)
                except Exception as e:  # noqa: BLE001
                    log(f"BŁĄD syntezy: {e!r} dla: {chunk[:60]}")
                    continue
                log(f"  {time.time() - t:.1f} s → {len(audio) / sr:.1f} s audio: {spoken[:70]}")
                if epoch != self.epoch:
                    break
                self.audio.put((epoch, audio, sr))

    def _player(self) -> None:
        # afplay zamiast PortAudio: zawsze gra na bieżącym urządzeniu wyjściowym
        # (PortAudio zapamiętuje listę urządzeń ze startu i pada po podłączeniu słuchawek).
        while True:
            epoch, audio, sr = self.audio.get()
            if epoch != self.epoch or not len(audio):
                continue
            self.speaking = True
            try:
                with tempfile.NamedTemporaryFile(suffix=".wav") as f:
                    # krótka cisza na końcu fragmentu = naturalna pauza między zdaniami
                    sf.write(f.name, np.concatenate([audio, np.zeros(int(sr * 0.12), np.float32)]), sr)
                    if epoch == self.epoch:
                        self.player_proc = subprocess.Popen(["afplay", f.name])
                        self.player_proc.wait()
            except Exception as e:  # noqa: BLE001 — wątek odtwarzacza nie może umrzeć
                log(f"BŁĄD odtwarzania: {e!r}")
            finally:
                self.speaking = False


def make_handler(speaker: Speaker, cfg: dict):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):  # cisza w stderr
            pass

        def _reply(self, code: int, body: dict) -> None:
            data = json.dumps(body, ensure_ascii=False).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self):
            if self.path == "/health":
                self._reply(
                    200,
                    {
                        "ready": speaker.ready.is_set(),
                        "speaking": speaker.speaking,
                        "engine": cfg["engine"],
                        "pid": os.getpid(),
                    },
                )
            else:
                self._reply(404, {"error": "not found"})

        def do_POST(self):
            length = int(self.headers.get("Content-Length") or 0)
            try:
                body = json.loads(self.rfile.read(length) or b"{}")
            except ValueError:
                return self._reply(400, {"error": "bad json"})
            if self.path == "/stop":
                speaker.interrupt()
                return self._reply(200, {"ok": True})
            if self.path == "/speak":
                live = load_config()  # język/ustawienia zmienione przez CLI działają bez restartu
                text = body.get("text") or ""
                if body.get("markdown", True):
                    text, lang = prepare(text, live)
                else:
                    lang = live["language"] if live["language"] in ("pl", "en") else detect_language(text)
                if text.strip():
                    speaker.say(text, lang)
                return self._reply(200, {"ok": True, "chars": len(text), "lang": lang})
            self._reply(404, {"error": "not found"})

    return Handler


def main() -> None:
    cfg = load_config()
    STATE_DIR.mkdir(exist_ok=True)
    speaker = Speaker(cfg)
    server = ThreadingHTTPServer(("127.0.0.1", cfg["port"]), make_handler(speaker, cfg))
    log(f"start pid={os.getpid()} port={cfg['port']} engine={cfg['engine']}")

    # Tekst zostawiony przez hook, który musiał najpierw uruchomić serwer
    if PENDING_PATH.exists():
        pending = PENDING_PATH.read_text()
        PENDING_PATH.unlink(missing_ok=True)
        speaker.say(*prepare(pending, cfg))

    server.serve_forever()


if __name__ == "__main__":
    main()
