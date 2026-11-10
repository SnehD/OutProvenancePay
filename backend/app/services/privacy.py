"""Regex-based redaction of emails, phone numbers and card-like numbers.

LIMITATION: pattern matching is best-effort. It misses names, addresses, unusual number
formats and anything written in a way the patterns do not anticipate. It does NOT guarantee
that all personal data is removed.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

LIMITATION_NOTE = (
    "Regex-based filtering is limited: it can miss names, addresses and unusual formats, and may "
    "occasionally redact harmless text. It does not guarantee complete PII removal."
)

_EMAIL = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9\-]+(?:\.[A-Za-z0-9\-]+)*\.[A-Za-z]{2,}")
_CARD = re.compile(r"(?<![\d])(?:\d[ \-]?){13,19}(?![\d])")
_PHONE = re.compile(r"(?<![\w])\+?\(?\d[\d\s().\-]{7,}\d(?![\w])")


@dataclass(frozen=True)
class RedactionResult:
    redacted_text: str
    counts: dict[str, int]

    @property
    def total(self) -> int:
        return sum(self.counts.values())


def _digits(s: str) -> int:
    return sum(ch.isdigit() for ch in s)


def redact(text: str) -> RedactionResult:
    """Return text with sensitive-looking values replaced by placeholders. Values are never logged."""
    counts = {"email": 0, "card": 0, "phone": 0}

    def sub_email(_m: re.Match) -> str:
        counts["email"] += 1
        return "[REDACTED_EMAIL]"

    def sub_card(m: re.Match) -> str:
        if 13 <= _digits(m.group()) <= 19:
            counts["card"] += 1
            return "[REDACTED_CARD]"
        return m.group()

    def sub_phone(m: re.Match) -> str:
        if 9 <= _digits(m.group()) <= 15:
            counts["phone"] += 1
            return "[REDACTED_PHONE]"
        return m.group()

    out = _EMAIL.sub(sub_email, text)
    out = _CARD.sub(sub_card, out)
    out = _PHONE.sub(sub_phone, out)
    return RedactionResult(redacted_text=out, counts=counts)
