---
name: lektor
description: Sterowanie i konfiguracja czytania odpowiedzi Claude Code na głos (plugin lektor, Chatterbox PL/EN). Używaj, gdy użytkownik chce włączyć/wyłączyć czytanie, przerwać je, zmienić głos lub język („czytaj po angielsku”, „zmień głos na męski”, „użyj mojego głosu”), skarży się, że nic nie słychać, że czyta za wolno, przekręca słowa, albo pyta, jak działa czytanie na głos.
---

# lektor — czytanie odpowiedzi na głos

Plugin czyta na głos każdą końcową odpowiedź Claude Code (hook `Stop`), a przerywa, gdy użytkownik wysyła kolejny prompt (hook `UserPromptSubmit`). Synteza jest lokalna: lokalny serwer `127.0.0.1:7862` z modelem Chatterbox Multilingual v3 (MLX). Działa tylko na macOS z Apple Silicon.

## Sterowanie
CLI: `~/.lektor/bin/lektor <komenda>` (także `/czytaj <komenda>`):
- `status` — czy czytanie włączone, język, stan serwera
- `on` / `off` — włącz / wyłącz czytanie odpowiedzi
- `stop` — przerwij bieżące czytanie
- `lang auto|pl|en` — język: `auto` wykrywa z odpowiedzi (przy wątpliwościach polski)
- `say "tekst"` — przeczytaj dowolny tekst
- `start` / `kill` — uruchom / zatrzymaj serwer (po zmianie configu: `kill`; wystartuje sam przy następnej odpowiedzi)

## Konfiguracja — `~/.lektor/config.json`
Edytuj, zachowując istniejące klucze (plik może nie istnieć — wtedy utwórz). Po zmianie: `lektor kill`.
- `voice` — nagranie referencyjne do sklonowania głosu: czyste, 5–15 s, jeden mówca, bez muzyki (wav/mp3/m4a). Wbudowane: `<plugin>/voices/fleurs_kobieta.wav` (domyślny), `<plugin>/voices/fleurs_mezczyzna.wav`. Ścieżkę katalogu pluginu znajdziesz w wrapperze `~/.lektor/bin/lektor`.
  Własny głos: poproś użytkownika o nagranie (np. `rec`/QuickTime) i wskaż plik.
- `exaggeration` (0–1.5, domyślnie 0.5) — ekspresja; `cfg_weight` (0–1, domyślnie 0.5) — niżej = spokojniej.
- `language` — `auto` | `pl` | `en` (to samo co `lang`).
- `english_in_polish` — `phonetic` (domyślnie: angielskie wtrącenia w polskich zdaniach zapisywane fonetycznie po polsku, np. „pull request” → „pul rykłest”) | `off`.
- `max_chars` (domyślnie 1500) — dłuższe odpowiedzi są ucinane na granicy zdania.
- `engine` — `chatterbox` | `piper` (szybki, syntetyczny; wymaga `piper_voice` = ścieżka do `pl_PL-*.onnx` z `rhasspy/piper-voices`).

Źle wymawiane angielskie słowo w polskim zdaniu: dopisz jego polski zapis fonetyczny do `RESPELL_OVERRIDES` w `<plugin>/lang.py` (zmiana przepadnie przy aktualizacji pluginu — zaproponuj też zgłoszenie do repo).

## Diagnostyka
1. `lektor status`. Brak wrappera → instalacja jeszcze trwa albo się nie udała: `~/.lektor/setup.log` (najczęściej brak `uv` → `brew install uv`, potem nowa sesja).
2. Log serwera: `~/.lektor/server.log` — linie `czytam [pl|en] …` (hook dotarł), `… s → … s audio` (synteza), `BŁĄD …`.
3. Pierwsze uruchomienie pobiera model (~2.7 GB) — przez kilka minut status pokazuje „ładuje model…”.
4. Przerwy między zdaniami: Chatterbox na M1/M2 generuje mniej więcej w tempie mowy; szybciej będzie z `engine: piper`.
5. Odtwarzanie idzie przez `afplay` na bieżące urządzenie wyjściowe macOS.
