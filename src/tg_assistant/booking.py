"""Booking / lead-capture dialog as a plain state machine (no Telegram imports)."""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from enum import StrEnum

from .config import BusinessConfig, Service
from .db import Booking, Database, SlotTakenError
from .i18n import is_no, is_yes, t
from .reminders import passed_offsets

_PHONE_CHARS = re.compile(r"^\+?[\d\s\-().]+$")


class Step(StrEnum):
    SERVICE = "service"
    DATE = "date"
    TIME = "time"
    NAME = "name"
    PHONE = "phone"
    CONFIRM = "confirm"
    DONE = "done"
    CANCELLED = "cancelled"


@dataclass
class Card:
    """A message with inline buttons: ``buttons`` are ``(label, callback_data)`` pairs."""

    text: str
    buttons: list[tuple[str, str]] = field(default_factory=list)


@dataclass
class Reply:
    text: str
    options: list[str] = field(default_factory=list)
    admin_notice: str | None = None
    cards: list[Card] = field(default_factory=list)


@dataclass
class Flow:
    """State of one user's dialog. ``kind`` is ``booking``, ``reschedule`` or ``lead``."""

    kind: str
    lang: str
    user_id: int
    username: str = ""
    step: Step = Step.SERVICE
    service: Service | None = None
    date: str = ""
    time: str = ""
    name: str = ""
    phone: str = ""
    booking_id: int = 0  # reschedule only: the booking being moved
    old_slot: str = ""  # reschedule only: "<date> <time>" before the move

    @property
    def active(self) -> bool:
        return self.step not in (Step.DONE, Step.CANCELLED)


def normalize_phone(raw: str) -> str | None:
    """Return a cleaned phone number or None when it is not plausible."""
    text = raw.strip()
    if not _PHONE_CHARS.match(text):
        return None
    digits = re.sub(r"\D", "", text)
    if not 7 <= len(digits) <= 15:
        return None
    return ("+" if text.startswith("+") else "") + digits


def _hhmm(dt: datetime) -> str:
    return dt.strftime("%H:%M")


class BookingEngine:
    def __init__(
        self,
        config: BusinessConfig,
        db: Database,
        now: Callable[[], datetime] = datetime.now,
    ) -> None:
        self.config = config
        self.db = db
        self._now = now

    # ---- availability --------------------------------------------------
    def day_slots(self, day: date) -> list[str]:
        """All bookable times of a day, ignoring existing bookings."""
        s = self.config.schedule
        if day.weekday() not in s.open_weekdays:
            return []
        cursor = datetime.combine(day, s.open)
        end = datetime.combine(day, s.close)
        step = timedelta(minutes=s.slot_minutes)
        slots: list[str] = []
        while cursor + step <= end:
            finish = cursor + step
            in_break = any(
                cursor.time() < b_end and finish.time() > b_start for b_start, b_end in s.breaks
            )
            if not in_break:
                slots.append(_hhmm(cursor))
            cursor += step
        return slots

    def free_slots(self, day: date) -> list[str]:
        taken = self.db.booked_times(day.isoformat())
        now = self._now()
        out = []
        for slot in self.day_slots(day):
            if slot in taken:
                continue
            if datetime.combine(day, datetime.strptime(slot, "%H:%M").time()) <= now:
                continue
            out.append(slot)
        return out

    def open_dates(self) -> list[str]:
        today = self._now().date()
        days = (today + timedelta(days=i) for i in range(self.config.schedule.horizon_days + 1))
        return [d.isoformat() for d in days if self.free_slots(d)]

    # ---- dialog --------------------------------------------------------
    def start(self, kind: str, lang: str, user_id: int, username: str = "") -> tuple[Flow, Reply]:
        flow = Flow(kind=kind, lang=lang, user_id=user_id, username=username)
        if kind == "lead":
            flow.step = Step.NAME
        return flow, self.prompt(flow)

    def prompt(self, flow: Flow) -> Reply:
        lang = flow.lang
        if flow.step is Step.SERVICE:
            return Reply(t(lang, "ask_service"), [s.name(lang) for s in self.config.services])
        if flow.step is Step.DATE:
            dates = self.open_dates()
            if not dates:
                flow.step = Step.CANCELLED
                return Reply(t(lang, "no_dates"))
            return Reply(t(lang, "ask_date"), dates)
        if flow.step is Step.TIME:
            slots = self.free_slots(date.fromisoformat(flow.date))
            if not slots:
                flow.step = Step.DATE
                return Reply(t(lang, "no_slots"), self.open_dates())
            return Reply(t(lang, "ask_time", date=flow.date), slots)
        if flow.step is Step.NAME:
            return Reply(t(lang, "ask_name"))
        if flow.step is Step.PHONE:
            return Reply(t(lang, "ask_phone"))
        if flow.step is Step.CONFIRM:
            summary = t(
                lang,
                "confirm_summary",
                service=flow.service.name(lang) if flow.service else "",
                date=flow.date,
                time=flow.time,
                name=flow.name,
                phone=flow.phone,
            )
            return Reply(summary, [t(lang, "confirm_yes"), t(lang, "confirm_no")])
        return Reply("")

    def submit(self, flow: Flow, text: str) -> Reply:
        """Feed one user message into the flow and return the next reply."""
        lang, step, value = flow.lang, flow.step, text.strip()

        if step is Step.SERVICE:
            service = self._match_service(value, lang)
            if service is None:
                return self._retry(flow, "bad_service")
            flow.service, flow.step = service, Step.DATE
        elif step is Step.DATE:
            day = self._parse_date(value)
            if day is None or day.isoformat() not in self.open_dates():
                return self._retry(flow, "bad_date")
            flow.date, flow.step = day.isoformat(), Step.TIME
        elif step is Step.TIME:
            if value not in self.free_slots(date.fromisoformat(flow.date)):
                return self._retry(flow, "bad_time")
            flow.time = value
            if flow.kind == "reschedule":
                return self._finish_reschedule(flow)
            flow.step = Step.NAME
        elif step is Step.NAME:
            if len(re.sub(r"[^\w]", "", value)) < 2 or len(value) > 60:
                return self._retry(flow, "bad_name")
            flow.name, flow.step = value, Step.PHONE
        elif step is Step.PHONE:
            phone = normalize_phone(value)
            if phone is None:
                return self._retry(flow, "bad_phone")
            flow.phone = phone
            if flow.kind == "lead":
                return self._finish_lead(flow)
            flow.step = Step.CONFIRM
        elif step is Step.CONFIRM:
            if is_yes(value):
                return self._finish_booking(flow)
            if is_no(value):
                flow.step = Step.CANCELLED
                return Reply(t(lang, "cancelled"))
            return self._retry(flow, "confirm_summary")
        return self.prompt(flow)

    # ---- helpers -------------------------------------------------------
    def _retry(self, flow: Flow, error_key: str) -> Reply:
        if error_key == "confirm_summary":
            return self.prompt(flow)
        reply = self.prompt(flow)
        reply.text = f"{t(flow.lang, error_key)}\n{reply.text}".strip()
        return reply

    def _finish_booking(self, flow: Flow) -> Reply:
        assert flow.service is not None
        try:
            booking = self.db.add_booking(
                flow.user_id,
                flow.service.id,
                flow.date,
                flow.time,
                flow.name,
                flow.phone,
                lang=flow.lang,
            )
        except SlotTakenError:
            flow.step = Step.TIME
            reply = self.prompt(flow)
            reply.text = f"{t(flow.lang, 'slot_taken')}\n{reply.text}"
            return reply
        self._skip_past_reminders(booking)
        flow.step = Step.DONE
        return Reply(
            t(
                flow.lang,
                "booked",
                service=flow.service.name(flow.lang),
                date=flow.date,
                time=flow.time,
                business=self.config.name,
            ),
            admin_notice=self._booking_notice(booking, flow),
        )

    def _skip_past_reminders(self, booking: Booking) -> None:
        """A reminder whose moment has already passed is recorded as sent, never delivered."""
        offsets = self.config.reminder_offsets_minutes
        for offset in passed_offsets(booking.start, self._now(), offsets):
            self.db.mark_reminder(booking.id, offset)

    def _finish_reschedule(self, flow: Flow) -> Reply:
        try:
            moved = self.db.move_booking(flow.booking_id, flow.date, flow.time)
        except SlotTakenError:
            flow.step = Step.TIME
            reply = self.prompt(flow)
            reply.text = f"{t(flow.lang, 'slot_taken')}\n{reply.text}"
            return reply
        flow.step = Step.DONE
        if moved is None:
            return Reply(t(flow.lang, "booking_not_found"))
        self._skip_past_reminders(moved)
        who = f"@{flow.username}" if flow.username else str(flow.user_id)
        notice = (
            f"Booking #{moved.id} rescheduled: {flow.old_slot} -> {moved.date} {moved.time}\n"
            f"{moved.service}, {moved.name}, {moved.phone} ({who})"
        )
        service = self.service_name(moved.service, flow.lang)
        text = t(
            flow.lang, "booking_rescheduled", service=service, date=moved.date, time=moved.time
        )
        return Reply(text, admin_notice=notice)

    # ---- manage existing bookings --------------------------------------
    def service_name(self, service_id: str, lang: str) -> str:
        for s in self.config.services:
            if s.id == service_id:
                return s.name(lang)
        return service_id

    def user_bookings(self, user_id: int) -> list[Booking]:
        """The customer's upcoming (not yet started) bookings."""
        now = self._now()
        found = self.db.bookings_from(now.date().isoformat(), user_id)
        return [b for b in found if b.start > now]

    def _own(self, booking_id: int, user_id: int) -> Booking | None:
        booking = self.db.get_booking(booking_id)
        return booking if booking and booking.user_id == user_id else None

    def cancel_booking(self, booking_id: int, user_id: int, lang: str = "en") -> Reply | None:
        """Cancel the customer's own booking and free its slot; None when not theirs."""
        booking = self._own(booking_id, user_id)
        if booking is None or not self.db.cancel_booking(booking_id):
            return None
        service = self.service_name(booking.service, lang)
        return Reply(
            t(lang, "booking_cancelled", service=service, date=booking.date, time=booking.time),
            admin_notice=(
                f"Booking #{booking.id} cancelled by customer: {booking.date} {booking.time}\n"
                f"{booking.service}, {booking.name}, {booking.phone} (id {booking.user_id})"
            ),
        )

    def confirm_booking(self, booking_id: int, user_id: int, lang: str = "en") -> Reply | None:
        booking = self._own(booking_id, user_id)
        if booking is None or not self.db.confirm_booking(booking_id):
            return None
        return Reply(t(lang, "visit_confirmed", date=booking.date, time=booking.time))

    def start_reschedule(
        self, booking_id: int, user_id: int, lang: str, username: str = ""
    ) -> tuple[Flow, Reply] | None:
        """Begin the date/time flow for an existing booking (service, name, phone are kept)."""
        booking = self._own(booking_id, user_id)
        if booking is None:
            return None
        service = next((s for s in self.config.services if s.id == booking.service), None)
        flow = Flow(
            kind="reschedule",
            lang=lang,
            user_id=user_id,
            username=username,
            step=Step.DATE,
            service=service,
            name=booking.name,
            phone=booking.phone,
            booking_id=booking.id,
            old_slot=f"{booking.date} {booking.time}",
        )
        reply = self.prompt(flow)
        intro = t(
            lang,
            "reschedule_start",
            service=self.service_name(booking.service, lang),
            date=booking.date,
            time=booking.time,
        )
        reply.text = f"{intro}\n{reply.text}"
        return flow, reply

    def _finish_lead(self, flow: Flow) -> Reply:
        self.db.add_lead(flow.user_id, flow.username, flow.name, flow.phone, source="lead")
        flow.step = Step.DONE
        who = f"@{flow.username}" if flow.username else str(flow.user_id)
        return Reply(
            t(flow.lang, "lead_saved", name=flow.name),
            admin_notice=f"New lead: {flow.name}, {flow.phone} ({who})",
        )

    def _booking_notice(self, booking: Booking, flow: Flow) -> str:
        who = f"@{flow.username}" if flow.username else str(flow.user_id)
        return (
            f"New booking #{booking.id}: {booking.service}, {booking.date} {booking.time}\n"
            f"{booking.name}, {booking.phone} ({who})"
        )

    def _match_service(self, value: str, lang: str) -> Service | None:
        services = self.config.services
        if value.isdigit() and 1 <= int(value) <= len(services):
            return services[int(value) - 1]
        low = value.lower()
        for s in services:
            if low in {n.lower() for n in s.names.values()} or low == s.id:
                return s
        for s in services:
            if len(low) >= 3 and any(low in n.lower() for n in s.names.values()):
                return s
        return None

    def _parse_date(self, value: str) -> date | None:
        try:
            return date.fromisoformat(value)
        except ValueError:
            pass
        m = re.fullmatch(r"(\d{1,2})[./](\d{1,2})(?:[./](\d{4}))?", value)
        if not m:
            return None
        today = self._now().date()
        year = int(m.group(3)) if m.group(3) else today.year
        try:
            parsed = date(year, int(m.group(2)), int(m.group(1)))
        except ValueError:
            return None
        if not m.group(3) and parsed < today:
            parsed = parsed.replace(year=year + 1)
        return parsed
