"""Script-based language detection (EN / RU / HY)."""

from __future__ import annotations

SUPPORTED = ("en", "ru", "hy")


def detect_language(text: str, default: str = "en") -> str:
    """Return ``en``, ``ru`` or ``hy`` by counting letters per script.

    Text without any letters (digits, emoji, punctuation) returns ``default`` so a
    conversation keeps its language when the user sends e.g. a phone number.
    """
    counts = {"en": 0, "ru": 0, "hy": 0}
    for ch in text:
        code = ord(ch)
        if 0x0530 <= code <= 0x058F:
            counts["hy"] += 1
        elif 0x0400 <= code <= 0x04FF:
            counts["ru"] += 1
        elif ch.isalpha() and code < 0x0250:
            counts["en"] += 1
    best = max(counts, key=lambda k: counts[k])
    return best if counts[best] > 0 else default
