"""Wykrywanie języka odpowiedzi i angielskich wtrąceń w polskich zdaniach."""

from __future__ import annotations

import re
from functools import lru_cache

PL_CHARS = re.compile(r"[ąćęłńóśźż]", re.I)
# Krótkie polskie słowa, które przypadkiem są też angielskie albo mylą detektor
PL_FUNCTION_WORDS = set(
    "a i w z o u na do po od za ze we to ta te ten tak nie czy jest są być był była było ale bo że "
    "już też jak co gdy przez dla pod nad przy przed albo lub oraz więc no on ona ono my wy oni one "
    "go mu jej ich mi ci się sie tu tam raz".split()
)
EN_IN_DICT_MIN = 0.65  # słowo ze słownika angielskiego
EN_NOT_IN_DICT_MIN = 0.9  # słowo spoza słownika (np. „endpoint”) — musi być pewniejsze
WORD = re.compile(r"[A-Za-zĄĆĘŁŃÓŚŹŻąćęłńóśźż0-9']+(?:-[A-Za-zĄĆĘŁŃÓŚŹŻąćęłńóśźż0-9']+)*")


@lru_cache(maxsize=1)
def _detector():
    from lingua import Language, LanguageDetectorBuilder

    return (
        LanguageDetectorBuilder.from_languages(Language.POLISH, Language.ENGLISH)
        .with_preloaded_language_models()
        .build()
    )


@lru_cache(maxsize=1)
def _english_words() -> frozenset[str]:
    try:
        with open("/usr/share/dict/words") as f:
            return frozenset(w.strip().lower() for w in f)
    except OSError:
        return frozenset()


def detect_language(text: str) -> str:
    """'pl' albo 'en' dla całej odpowiedzi. Przy wątpliwościach — polski
    (polskie odpowiedzi pełne angielskich terminów nie mogą przełączyć się na angielski)."""
    from lingua import Language

    if len(PL_CHARS.findall(text)) >= 3:
        return "pl"
    conf = _detector().compute_language_confidence(text, Language.ENGLISH)
    return "en" if conf >= 0.8 else "pl"


@lru_cache(maxsize=4096)
def is_english_word(word: str) -> bool:
    from lingua import Language

    w = word.lower()
    if PL_CHARS.search(w) or w in PL_FUNCTION_WORDS or w.isdigit() or len(w) < 2:
        return False
    if word.isupper() and len(word) <= 5:  # skróty (CI, TTS, OK) czytamy po polsku
        return False
    conf = _detector().compute_language_confidence(w, Language.ENGLISH)
    words = _english_words()
    in_dict = w in words or all(p in words for p in w.split("-"))
    return conf >= (EN_IN_DICT_MIN if in_dict else EN_NOT_IN_DICT_MIN)


def split_mixed(sentence: str) -> list[tuple[str, str]]:
    """Polskie zdanie -> [(lang, fragment), ...] z angielskimi wtrąceniami jako osobne fragmenty.

    Kolejne angielskie słowa (rozdzielone tylko spacjami) łączą się w jedną frazę.
    """
    spans: list[tuple[str, int, int]] = []  # (lang, start, end)
    for m in WORD.finditer(sentence):
        lang = "en" if is_english_word(m.group(0)) else "pl"
        if spans and spans[-1][0] == lang and (
            lang == "pl" or sentence[spans[-1][2] : m.start()].strip() == ""
        ):
            spans[-1] = (lang, spans[-1][1], m.end())
        else:
            spans.append((lang, m.start(), m.end()))

    if not any(lang == "en" for lang, _, _ in spans):
        return [("pl", sentence)]

    # Fragmenty pokrywają całe zdanie: interpunkcja zostaje przy poprzednim fragmencie
    out: list[tuple[str, str]] = []
    for i, (lang, start, _) in enumerate(spans):
        begin = 0 if i == 0 else start
        end = spans[i + 1][1] if i + 1 < len(spans) else len(sentence)
        text = sentence[begin:end].strip()
        if not text:
            continue
        if out and out[-1][0] == lang:
            out[-1] = (lang, f"{out[-1][1]} {text}")
        else:
            out.append((lang, text))
    return out


# --- Wariant „po polsku z angielską wymową”: zapis fonetyczny angielskich słów polskimi literami ---

_VOWELS = {
    "AA": "a", "AE": "e", "AH": "a", "AO": "o", "AW": "ał", "AY": "aj", "EH": "e",
    "ER": "er", "EY": "ej", "IH": "i", "IY": "i", "OW": "oł", "OY": "oj", "UH": "u", "UW": "u",
}
_CONSONANTS = {
    "B": "b", "CH": "cz", "D": "d", "DH": "d", "F": "f", "G": "g", "HH": "h", "JH": "dż",
    "K": "k", "L": "l", "M": "m", "N": "n", "NG": "ng", "P": "p", "R": "r", "S": "s",
    "SH": "sz", "T": "t", "TH": "t", "V": "w", "W": "ł", "Y": "j", "Z": "z", "ZH": "ż",
}
_HARD_BEFORE_I = {"s", "z", "c", "n", "d", "t", "r", "dz"}  # tu „i” zmiękczałoby (si = „śi”)


@lru_cache(maxsize=1)
def _cmu():
    import cmudict

    return cmudict.dict()


def _respell_one(word: str) -> str | None:
    prons = _cmu().get(word.lower())
    if not prons:
        return None
    out = ""
    for ph in prons[0]:
        base, stress = ph.rstrip("012"), ph[-1] if ph[-1].isdigit() else ""
        if base in _VOWELS:
            v = _VOWELS[base]
            if base == "AH" and stress == "0":
                v = "e"  # nieakcentowane szwa: the -> „de”
            if v == "i" and out[-2:] in _HARD_BEFORE_I | {o[-1:] for o in _HARD_BEFORE_I}:
                v = "y" if base == "IH" else "i"
            out += v
        else:
            out += _CONSONANTS.get(base, "")
    return out


# Słowa, których nie ma w CMU albo które Polacy wymawiają po swojemu
RESPELL_OVERRIDES = {
    "async": "ejsynk", "sync": "synk", "commit": "komit", "commits": "komity", "true": "tru",
    "false": "fols", "deploy": "diploj", "deployment": "diplojment", "frontend": "frontend",
    "backend": "bekend", "endpoint": "endpojnt", "framework": "frejmłork", "workflow": "łorkfloł",
    "feedback": "fidbek", "the": "de", "debug": "dibag", "debugger": "dibager",
}


def respell_english(word: str) -> str:
    """'pull' -> 'pul', 'end-to-end' -> 'end-tu-end'; nieznane słowa bez zmian."""
    if word.lower() in RESPELL_OVERRIDES:
        return RESPELL_OVERRIDES[word.lower()]
    parts = word.split("-")
    spelled = [RESPELL_OVERRIDES.get(p.lower()) or _respell_one(p) for p in parts]
    if all(spelled):
        return "-".join(spelled)  # type: ignore[arg-type]
    return word


def polonize(sentence: str) -> str:
    """Zdanie z angielskimi wtrąceniami -> to samo zdanie, wtrącenia zapisane fonetycznie po polsku."""
    def repl(m: re.Match) -> str:
        w = m.group(0)
        return respell_english(w) if w.lower() in RESPELL_OVERRIDES or is_english_word(w) else w

    return WORD.sub(repl, sentence)
