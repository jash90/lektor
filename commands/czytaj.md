---
description: Czytanie odpowiedzi na głos — on | off | stop | status | lang auto|pl|en
argument-hint: on|off|stop|status|lang auto|pl|en
allowed-tools: Bash(~/.lektor/bin/lektor:*)
---
!`~/.lektor/bin/lektor ${ARGUMENTS:-status} 2>&1 || echo "lektor nie jest jeszcze zainstalowany — instalacja trwa w tle po starcie sesji (log: ~/.lektor/setup.log)."`

Pokaż użytkownikowi wynik powyższej komendy jednym krótkim zdaniem, bez dodatkowych działań.
