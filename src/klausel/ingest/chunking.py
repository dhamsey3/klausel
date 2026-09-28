"""Structure-aware chunking for German legal text.

Splits on the strongest boundary that fits: section markers (§ / Art. /
Abschnitt) -> paragraphs -> sentences -> words, then greedily packs pieces into
chunks of at most `chunk_size` characters with `overlap` characters carried
over between consecutive chunks.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# Lookahead splits keep the marker at the start of the new piece.
_SECTION_RE = re.compile(r"\n(?=\s*(?:§+\s*\d|Art(?:ikel|\.)\s*\d|Abschnitt\s+\w|Teil\s+\w))")
_PARAGRAPH_RE = re.compile(r"\n\s*\n")
# Sentence end, but not after common German abbreviations or "Abs. 1" style numbering.
_SENTENCE_RE = re.compile(
    r"(?<=[.!?;])"
    r"(?<!\bAbs\.)(?<!\bNr\.)(?<!\bz\.B\.)(?<!\bbzw\.)(?<!\bvgl\.)(?<!\bggf\.)(?<!\busw\.)"
    r"(?<!\bS\.)(?<!\d\.)"
    r"\s+(?=[A-ZÄÖÜ(\"„])"
)
_SEPARATORS = (_SECTION_RE, _PARAGRAPH_RE, _SENTENCE_RE)


@dataclass(frozen=True)
class Chunk:
    index: int
    text: str
    start: int  # char offset in the source text (approximate after whitespace trimming)


def _split(text: str, chunk_size: int, level: int = 0) -> list[str]:
    if len(text) <= chunk_size:
        return [text]
    if level >= len(_SEPARATORS):
        words, out, cur = text.split(), [], ""
        for w in words:
            if cur and len(cur) + 1 + len(w) > chunk_size:
                out.append(cur)
                cur = w
            else:
                cur = f"{cur} {w}" if cur else w
        if cur:
            out.append(cur)
        # A single "word" longer than chunk_size is hard-cut.
        return [p[i : i + chunk_size] for p in out for i in range(0, len(p), chunk_size)]
    parts = [p for p in _SEPARATORS[level].split(text) if p.strip()]
    if len(parts) <= 1:
        return _split(text, chunk_size, level + 1)
    result: list[str] = []
    for p in parts:
        result.extend(
            _split(p.strip(), chunk_size, level + 1) if len(p) > chunk_size else [p.strip()]
        )
    return result


def _tail(text: str, overlap: int) -> str:
    if overlap <= 0 or len(text) <= overlap:
        return text if overlap > 0 else ""
    cut = text[-overlap:]
    space = cut.find(" ")
    return cut[space + 1 :] if 0 <= space < len(cut) - 1 else cut


def chunk_text(text: str, chunk_size: int = 1000, overlap: int = 150) -> list[Chunk]:
    if overlap >= chunk_size:
        raise ValueError("overlap must be smaller than chunk_size")
    text = text.strip()
    if not text:
        return []

    pieces = _split(text, chunk_size)
    chunks: list[str] = []
    cur = ""
    for piece in pieces:
        candidate = f"{cur}\n\n{piece}" if cur else piece
        if len(candidate) <= chunk_size:
            cur = candidate
            continue
        if cur:
            chunks.append(cur)
            carry = _tail(cur, overlap)
            cur = (
                f"{carry}\n\n{piece}"
                if carry and len(carry) + 2 + len(piece) <= chunk_size
                else piece
            )
        else:
            cur = piece
    if cur:
        chunks.append(cur)

    out, search_from = [], 0
    for i, c in enumerate(chunks):
        probe = c[:50]
        pos = text.find(probe, search_from)
        start = pos if pos >= 0 else search_from
        search_from = max(search_from, start)
        out.append(Chunk(index=i, text=c, start=start))
    return out
