from __future__ import annotations

import re
import unicodedata

import pandas as pd

_SUFFIXES = frozenset({"jr", "sr", "ii", "iii", "iv", "v"})
_NON_ALNUM = re.compile(r"[^a-z0-9]+")


def player_key(name: object) -> str:
    """Stable join key for Dunkest / NBA names (accents, Jr/II, punctuation).

    Missing pandas/NumPy scalar values map to an empty key. In particular,
    pandas.NA must not be evaluated as a boolean (it raises TypeError).
    """
    if name is None:
        return ""
    try:
        if pd.isna(name):
            return ""
    except (TypeError, ValueError):
        pass
    text = unicodedata.normalize("NFKD", str(name))
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = text.casefold().replace("'", "").replace(".", " ")
    tokens = [tok for tok in _NON_ALNUM.split(text) if tok and tok not in _SUFFIXES]
    return " ".join(tokens)


def player_surname(name: object) -> str:
    tokens = player_key(name).split()
    return tokens[-1] if tokens else ""
