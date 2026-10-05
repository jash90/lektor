"""Zamiana markdownu z odpowiedzi Claude Code na tekst do przeczytania na głos (PL lub EN)."""

from __future__ import annotations

import re

from num2words import num2words

PHRASES = {
    "pl": {
        "code": "Pomijam blok kodu.",
        "rest": "Resztę odpowiedzi pomijam.",
        "link": "link",
        "about": "około ",
        "range": " do ",
        "percent": " procent",
        "point": "przecinek",
    },
    "en": {
        "code": "Skipping a code block.",
        "rest": "I'm skipping the rest of the answer.",
        "link": "a link",
        "about": "about ",
        "range": " to ",
        "percent": " percent",
        "point": "point",
    },
}

_EMOJI = re.compile(
    "[\U0001f000-\U0001faff\U00002600-\U000027bf\U0001f900-\U0001f9ff⭐⭕✅❌⚠️]"
)


UNITS = {
    "pl": {
        "ms": "milisekund", "s": "sekund", "min": "minut", "h": "godzin",
        "GB": "gigabajtów", "MB": "megabajtów", "KB": "kilobajtów", "px": "pikseli",
    },
    "en": {
        "ms": "milliseconds", "s": "seconds", "min": "minutes", "h": "hours",
        "GB": "gigabytes", "MB": "megabytes", "KB": "kilobytes", "px": "pixels",
    },
}


def _number(m: re.Match, lang: str) -> str:
    s = m.group(0)
    try:
        if "," in s or "." in s:
            whole, frac = re.split(r"[.,]", s, maxsplit=1)
            point = PHRASES[lang]["point"]
            return f"{num2words(int(whole), lang=lang)} {point} {num2words(int(frac), lang=lang)}"
        n = int(s)
        return s if n > 10**9 else num2words(n, lang=lang)
    except (ValueError, NotImplementedError):
        return s


def _path(m: re.Match) -> str:
    """`src/app/very/long/file.py:42` -> `file.py` — ścieżek nie czytamy w całości."""
    last = m.group(0).rstrip("/").split("/")[-1]
    return re.sub(r":\d+(-\d+)?$", "", last)


def _table_row(line: str) -> str | None:
    cells = [c.strip() for c in line.strip().strip("|").split("|")]
    if all(re.fullmatch(r":?-{2,}:?", c) or not c for c in cells):
        return None  # wiersz separatora |---|---|
    cells = [c for c in cells if c]
    return ", ".join(cells) + "." if cells else None


def to_speech(md: str, max_chars: int = 1500, lang: str = "pl") -> str:
    ph, units = PHRASES[lang], UNITS[lang]
    CODE_BLOCK = ph["code"]  # noqa: N806
    text = md.replace("\r\n", "\n")

    # Bloki kodu i diagramy -> krótka informacja
    text = re.sub(r"```.*?(```|$)", f"\n{CODE_BLOCK}\n", text, flags=re.S)
    # HTML/komentarze
    text = re.sub(r"<!--.*?-->", " ", text, flags=re.S)
    text = re.sub(r"</?[a-zA-Z][^>]*>", " ", text)

    lines = []
    for line in text.split("\n"):
        s = line.strip()
        if not s:
            lines.append("")
            continue
        if s.startswith("|"):
            row = _table_row(s)
            if row:
                lines.append(row)
            continue
        if re.fullmatch(r"[-*_]{3,}", s):  # linia pozioma
            continue
        s = re.sub(r"^#{1,6}\s*", "", s)  # nagłówki
        s = re.sub(r"^>\s?", "", s)  # cytaty
        s = re.sub(r"^([-*+]|\d+[.)])\s+", "", s)  # punkty list
        s = re.sub(r"^\[[ xX]\]\s*", "", s)  # checkboxy
        # Każdy punkt/nagłówek kończymy kropką, żeby TTS zrobił pauzę
        if s and s[-1] not in ".!?:;…,":
            s += "."
        lines.append(s)
    text = "\n".join(lines)

    text = re.sub(r"!\[[^\]]*\]\([^)]*\)", " ", text)  # obrazki
    text = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", text)  # linki -> tekst linku
    text = re.sub(r"https?://\S+?(?=[.,;:!?)]*(\s|$))", ph["link"], text)
    # inline code -> treść; snake_case czytamy jako osobne słowa
    text = re.sub(r"`([^`]*)`", lambda m: m.group(1).replace("_", " "), text)
    text = re.sub(r"(\*\*|~~|\*)(?=\S)(.+?)(?<=\S)\1", r"\2", text)  # pogrubienia/kursywa
    text = re.sub(r"(?<!\w)(__|_)(?=\S)(.+?)(?<=\S)\1(?!\w)", r"\2", text)
    text = re.sub(r"(?<=[a-z])_(?=[a-z])", " ", text)
    text = re.sub(r"(?<![\w.])(~|\.{1,2})?/?[\w.-]+(/[\w.@-]+)+/?(:\d+(-\d+)?)?", _path, text)
    text = re.sub(r"\b[\w-]+\.(py|ts|tsx|js|jsx|json|md|yml|yaml|toml|swift|sh)(:\d+)", lambda m: m.group(0).split(":")[0], text)
    text = _EMOJI.sub("", text)
    text = re.sub(r"~\s*(?=\d)", ph["about"], text)
    text = re.sub(r"(?<=\d)\s*[–-]\s*(?=\d)", ph["range"], text)  # zakresy 12–16
    text = re.sub(r"(?<=\d)\s*(" + "|".join(units) + r")\b", lambda m: " " + units[m.group(1)], text)
    text = re.sub(r"(?<![\w.,])\d+(?:[.,]\d+)?(?![\w.,]?\d)", lambda m: _number(m, lang), text)
    text = re.sub(r"%", ph["percent"], text)
    text = text.replace("→", ", ").replace("—", ", ").replace("–", ", ").replace("…", ".")
    text = re.sub(r"[*#`|<>{}\[\]\\]", " ", text)

    # Akapity -> jedna linia, porządek ze spacjami/interpunkcją
    text = re.sub(r"\s*\n\s*", " ", text)
    text = re.sub(r"\s+([.,!?;:])", r"\1", text)
    text = re.sub(r"([.!?])(\s*[.,])+", r"\1", text)
    text = re.sub(r"(\b" + re.escape(CODE_BLOCK) + r"\s*){2,}", CODE_BLOCK + " ", text)
    text = re.sub(r"\s{2,}", " ", text).strip()

    if len(text) > max_chars:
        cut = text[:max_chars]
        end = max(cut.rfind(". "), cut.rfind("! "), cut.rfind("? "))
        text = (cut[: end + 1] if end > max_chars // 3 else cut) + " " + ph["rest"]
    return text


def split_for_tts(text: str, first_max: int = 90, max_chars: int = 240) -> list[str]:
    """Zdania łączone w kawałki; pierwszy krótki, żeby szybko usłyszeć początek."""
    sentences = [s for s in re.split(r"(?<=[.!?])\s+", text) if s.strip()]
    chunks: list[str] = []
    cur = ""
    for s in sentences:
        limit = first_max if not chunks else max_chars
        if cur and len(cur) + len(s) + 1 > limit:
            chunks.append(cur)
            cur = s
        else:
            cur = f"{cur} {s}".strip()
    if cur:
        chunks.append(cur)
    # Bardzo długie zdania tniemy po przecinkach
    out = []
    for c in chunks:
        while len(c) > max_chars:
            cut = c.rfind(", ", 0, max_chars)
            if cut < max_chars // 3:
                cut = c.rfind(" ", 0, max_chars)
            out.append(c[: cut + 1].strip())
            c = c[cut + 1 :].strip()
        out.append(c)
    return [c for c in out if c]
