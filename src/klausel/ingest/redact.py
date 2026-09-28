"""Rule-based pseudonymisation applied before text is embedded or stored.

This is a data-minimisation safeguard (GDPR Art. 5(1)(c), Art. 25), not a
complete anonymiser: it catches structured identifiers (e-mail, IBAN, phone,
German tax/social-security style numbers, dates of birth). Names and addresses
need an NER model; see README "Next steps".
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field

_PATTERNS: dict[str, re.Pattern[str]] = {
    "EMAIL": re.compile(r"\b[\w.+-]+@[\w-]+(?:\.[\w-]+)+\b"),
    "IBAN": re.compile(r"\b[A-Z]{2}\d{2}(?:\s?[A-Z0-9]{4}){3,7}(?:\s?[A-Z0-9]{1,4})?\b"),
    # Steuer-ID: 11 digits, optionally grouped 2-3-3-3.
    "TAX_ID": re.compile(r"\b\d{2}\s?\d{3}\s?\d{3}\s?\d{3}\b"),
    # Sozialversicherungsnummer: 2 digits, 6 digits (DOB), letter, 3 digits.
    "SVNR": re.compile(r"\b\d{2}\s?\d{6}\s?[A-Z]\s?\d{3}\b"),
    "PHONE": re.compile(r"(?<![\w/])(?:\+49|0049|0)[\s/-]?\(?\d{2,5}\)?(?:[\s/-]?\d{2,}){1,4}\b"),
    "BIRTHDATE": re.compile(
        r"(?i)\b(?:geb(?:oren)?\.?\s*(?:am\s*)?)\d{1,2}\.\s?\d{1,2}\.\s?\d{2,4}\b"
    ),
}


@dataclass
class RedactionResult:
    text: str
    counts: Counter[str] = field(default_factory=Counter)


def redact(text: str) -> RedactionResult:
    counts: Counter[str] = Counter()
    for label, pattern in _PATTERNS.items():
        text, n = pattern.subn(f"[{label}]", text)
        if n:
            counts[label] += n
    return RedactionResult(text=text, counts=counts)
