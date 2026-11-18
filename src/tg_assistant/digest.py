"""Owner's daily digest: pure functions (no I/O, no Telegram)."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from datetime import date, datetime, time

from .db import Booking, Lead
from .i18n import t

_NONE = "-"


def digest_due(now: datetime, digest_time: time | None, last_sent: str | None) -> bool:
    """True once per day, from ``digest_time`` onwards; ``last_sent`` is an ISO date or None."""
    if digest_time is None:
        return False
    return now.time() >= digest_time and last_sent != now.date().isoformat()


def _booking_line(b: Booking, service_name: Callable[[str], str], lang: str) -> str:
    mark = f" ({t(lang, 'digest_confirmed')})" if b.confirmed else ""
    return f"• {b.time} {service_name(b.service)}, {b.name}, {b.phone}{mark}"


def _lead_line(lead: Lead) -> str:
    who = f"@{lead.username}" if lead.username else str(lead.user_id)
    extra = f": {lead.note}" if lead.note else ""
    phone = f", {lead.phone}" if lead.phone else ""
    return f"• {lead.name}{phone} ({who}){extra}"


def _section(title: str, lines: Sequence[str]) -> str:
    return "\n".join([f"{title}:", *(lines or [_NONE])])


def build_digest(
    *,
    lang: str,
    business: str,
    today: date,
    today_bookings: Sequence[Booking],
    tomorrow_bookings: Sequence[Booking],
    new_leads: Sequence[Lead],
    open_handoffs: Sequence[Lead],
    service_name: Callable[[str], str],
) -> str:
    """Plain-text digest for the owner's admin chat."""

    def lines(items: Sequence[Booking]) -> list[str]:
        return [_booking_line(b, service_name, lang) for b in sorted(items, key=lambda b: b.time)]

    unconfirmed = [b for b in tomorrow_bookings if not b.confirmed]
    parts = [
        t(lang, "digest_title", business=business, date=today.isoformat()),
        _section(t(lang, "digest_today"), lines(today_bookings)),
        _section(t(lang, "digest_tomorrow"), lines(tomorrow_bookings)),
    ]
    if unconfirmed:
        parts.append(_section(t(lang, "digest_unconfirmed"), lines(unconfirmed)))
    parts.append(_section(t(lang, "digest_leads"), [_lead_line(x) for x in new_leads]))
    parts.append(_section(t(lang, "digest_handoffs"), [_lead_line(x) for x in open_handoffs]))
    return "\n\n".join(parts)
