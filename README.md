# lektor

Plugin do Claude Code, który **czyta na głos odpowiedzi** — po polsku i po angielsku, w pełni lokalnie
(Chatterbox Multilingual v3 na MLX, klonowany głos). Wymaga **macOS z Apple Silicon**.

- czyta każdą końcową odpowiedź (hook `Stop`), przerywa, gdy piszesz kolejny prompt;
- markdown → mowa: pomija bloki kodu, linki i długie ścieżki, liczby i jednostki czyta słownie;
- język wykrywany automatycznie (PL/EN); angielskie wtrącenia w polskich zdaniach wymawiane po angielsku
  („pull request” → „pul rykłest”);
- czyta zdanie po zdaniu — kolejne generuje się, gdy poprzednie gra.

## Instalacja

Wymagania: macOS (Apple Silicon), [`uv`](https://docs.astral.sh/uv/) (`brew install uv`), ~4 GB miejsca (model + zależności).

```bash
claude plugin marketplace add jash90/lektor          # albo ścieżka do lokalnego klonu
claude plugin install lektor@lektor
```

Potem uruchom nową sesję Claude Code. Przy pierwszym starcie plugin w tle instaluje zależności
(`~/.lektor/setup.log`, 1–3 min), a przy pierwszej odpowiedzi pobiera model (~2.7 GB) — zanim zacznie czytać,
może minąć kilka minut. Kolejne starty serwera: ~7 s.

## Sterowanie

W Claude Code: `/czytaj status | on | off | stop | lang auto|pl|en`.
W terminalu: `~/.lektor/bin/lektor …` (te same komendy + `say "tekst"`, `start`, `kill`).

## Konfiguracja — `~/.lektor/config.json`

```json
{
  "voice": "/ścieżka/do/nagrania.wav",
  "language": "auto",
  "english_in_polish": "phonetic",
  "exaggeration": 0.5,
  "cfg_weight": 0.5,
  "max_chars": 1500
}
```

`voice` — czyste nagranie 5–15 s jednego mówcy (domyślnie `voices/fleurs_kobieta.wav`; jest też `fleurs_mezczyzna.wav`).
Po zmianie: `lektor kill` (serwer wystartuje sam przy następnej odpowiedzi). Pełny opis opcji: `skills/lektor/SKILL.md`.

## Jak to działa

| Plik | Rola |
|---|---|
| `hooks/hooks.json` | `SessionStart` → `scripts/setup.sh` (instalacja do `${CLAUDE_PLUGIN_DATA}/venv`), `Stop`/`UserPromptSubmit` → `scripts/hook.sh` |
| `lektor.py` | hook + CLI (tylko biblioteka standardowa); sam uruchamia serwer, jeśli nie działa |
| `server.py` | serwer TTS na `127.0.0.1:7862`: model w pamięci, kolejka zdań, odtwarzanie przez `afplay` |
| `speech_text.py` | markdown → tekst mówiony (PL/EN) |
| `lang.py` | wykrywanie języka (lingua) i fonetyczny zapis angielskich wtrąceń (słownik CMU) |

Stan, logi i konfiguracja: `~/.lektor/`.

## Odinstalowanie

```bash
~/.lektor/bin/lektor kill
claude plugin uninstall lektor@lektor
rm -rf ~/.lektor
```

## Licencje

Kod: MIT. Próbki głosów w `voices/` pochodzą z [Google FLEURS](https://huggingface.co/datasets/google/fleurs) (CC BY 4.0).
Model: [Chatterbox Multilingual](https://github.com/resemble-ai/chatterbox) (MIT), port MLX `mlx-community/chatterbox-multilingual-v3`.
