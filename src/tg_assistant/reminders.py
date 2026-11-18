"""Pure reminder logic: which reminders are due at time ``now`` (no I/O, no Telegram)."""

from __future__ import annotations

from collections.abc import Collection, Iterable, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta

from .db import Booking


@dataclass(frozen=True)
class DueReminder:
    booking: Booking
    offset_minutes: int
    confirm: bool  # True: this is the last reminder, so it carries Confirm / Cancel buttons


def passed_offsets(start: datetime, now: datetime, offsets: Iterable[int]) -> list[int]:
    """Offsets whose reminder moment is already behind us (used for last-minute bookings)."""
    return sorted((o for o in offsets if start - timedelta(minutes=o) <= now), reverse=True)


def due_reminders(
    bookings: Iterable[Booking],
    sent: Collection[tuple[int, int]],
    now: datetime,
    offsets: Sequence[int],
) -> list[DueReminder]:
    """Reminders to send at ``now``, ordered by visit time.

    ``sent`` holds ``(booking_id, offset_minutes)`` pairs that went out already. At most one
    reminder per booking is returned: when several offsets have been reached (for example after
    downtime) only the most recent one is still useful. The smallest offset carries the
    Confirm / Cancel buttons unless the customer has already confirmed.
    """
    if not offsets:
        return []
    last = min(offsets)
    due: list[DueReminder] = []
    for booking in sorted(bookings, key=lambda b: (b.start, b.id)):
        if booking.start <= now:
            continue
        reached = passed_offsets(booking.start, now, offsets)
        if not reached:
            continue
        latest = reached[-1]  # smallest offset reached
        if (booking.id, latest) in sent:
            continue
        due.append(DueReminder(booking, latest, latest == last and not booking.confirmed))
    return due
