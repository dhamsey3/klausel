"""Tiny German/English detector for questions and documents (no model, no network).

Counts frequent function words; umlauts/ß and "§" tip the balance towards German.
Good enough to pick the answer language and UI strings, not a general detector.
"""

from __future__ import annotations

import re
from typing import Literal

Lang = Literal["de", "en"]
SUPPORTED: tuple[Lang, ...] = ("de", "en")

_DE = frozenset(
    "der die das und ist nicht ein eine einer eines dem den des mit von zu für auf "
    "im in sind wird werden welche welcher welches wie was wer wann warum wo "
    "gilt gelten kann können darf muss müssen oder auch bei nach über gemäß vertrag "
    "klausel haftung kündigung frist".split()
)
_EN = frozenset(
    "the and is are not a an of to for on in with by which what who when why where "
    "how does do can may must shall should will be this that these those or any "
    "contract clause liability termination notice period".split()
)
_WORD_RE = re.compile(r"[a-zäöüß]+")


def detect_language(text: str, default: Lang = "de") -> Lang:
    words = _WORD_RE.findall(text.lower())
    de = sum(w in _DE for w in words) + 2 * len(re.findall(r"[äöüß§]", text.lower()))
    en = sum(w in _EN for w in words)
    if de == en:
        return default
    return "de" if de > en else "en"
