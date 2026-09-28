"""Turn raw object bytes into plain text. All parsing is local."""

from __future__ import annotations

import io
import unicodedata
from pathlib import PurePosixPath

SUPPORTED_SUFFIXES = (".txt", ".md", ".pdf", ".docx")


class UnsupportedDocumentError(ValueError):
    pass


def _decode_text(data: bytes) -> str:
    # German public-sector texts are still often cp1252 / latin-1 encoded.
    for enc in ("utf-8-sig", "cp1252", "latin-1"):
        try:
            return data.decode(enc)
        except UnicodeDecodeError:
            continue
    raise UnsupportedDocumentError("could not decode text")


def _pdf_to_text(data: bytes) -> str:
    from pypdf import PdfReader

    reader = PdfReader(io.BytesIO(data))
    return "\n\n".join(page.extract_text() or "" for page in reader.pages)


def _docx_to_text(data: bytes) -> str:
    from docx import Document

    doc = Document(io.BytesIO(data))
    return "\n\n".join(p.text for p in doc.paragraphs if p.text.strip())


def normalize(text: str) -> str:
    """NFC-normalise (umlauts), unify line endings, re-join hyphenated breaks."""
    text = unicodedata.normalize("NFC", text).replace("\r\n", "\n").replace("\r", "\n")
    text = text.replace("­", "")  # soft hyphen
    lines = [ln.rstrip() for ln in text.split("\n")]
    return "\n".join(lines).strip()


def extract_text(key: str, data: bytes) -> str:
    suffix = PurePosixPath(key).suffix.lower()
    if suffix in (".txt", ".md"):
        raw = _decode_text(data)
    elif suffix == ".pdf":
        raw = _pdf_to_text(data)
    elif suffix == ".docx":
        raw = _docx_to_text(data)
    else:
        raise UnsupportedDocumentError(f"unsupported file type: {key}")
    return normalize(raw)
