"""Transport-independent assistant brain: routing, language, FAQ, flows, handoff."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from .booking import BookingEngine, Card, Flow, Reply
from .config import BusinessConfig
from .db import Booking, Database
from .digest import build_digest, digest_due
from .i18n import t
from .knowledge import KnowledgeBase
from .lang import detect_language
from .llm import LLM, build_prompt
from .ratelimit import RateLimiter
from .reminders import due_reminders

_GREETINGS = {"hi", "hello", "hey", "привет", "здравствуйте", "добрый", "բարև", "ողջույն", "/start"}
_BOOK_STEMS = ("book", "appoint", "reserv", "запис", "бронир", "ամրագր", "գրանցվ", "գրանցում")
_MAX_INTENT_WORDS = 6
_DIGEST_DATE_KEY = "digest_last_date"
_DIGEST_LEAD_KEY = "digest_last_lead_id"


@dataclass(frozen=True)
class ReminderMessage:
    """A reminder ready to be sent; ``buttons`` are ``(label, callback_data)`` pairs."""

    user_id: int
    text: str
    booking_id: int
    offset_minutes: int
    buttons: list[tuple[str, str]] = field(default_factory=list)


@dataclass(frozen=True)
class DigestJob:
    text: str
    date: str
    last_lead_id: int


class Assistant:
    def __init__(
        self,
        config: BusinessConfig,
        kb: KnowledgeBase,
        db: Database,
        limiter: RateLimiter | None = None,
        llm: LLM | None = None,
        now: Callable[[], datetime] = datetime.now,
    ) -> None:
        self.config = config
        self.kb = kb
        self.db = db
        self.limiter = limiter
        self.llm = llm
        self.engine = BookingEngine(config, db, now)
        self._now = now
        self._lang: dict[int, str] = {}
        self._flows: dict[int, Flow] = {}
        self._last_text: dict[int, str] = {}

    # ---- helpers -------------------------------------------------------
    def lang_of(self, user_id: int) -> str:
        return self._lang.get(user_id, self.config.default_lang)

    def _start_flow(self, kind: str, user_id: int, username: str) -> Reply:
        flow, reply = self.engine.start(kind, self.lang_of(user_id), user_id, username)
        if flow.active:
            self._flows[user_id] = flow
        return reply

    def _wants_booking(self, text: str) -> bool:
        words = text.lower().split()
        return len(words) <= _MAX_INTENT_WORDS and any(
            w.startswith(stem) for w in words for stem in _BOOK_STEMS
        )

    # ---- entry points --------------------------------------------------
    async def on_message(
        self, user_id: int, text: str, username: str = "", full_name: str = ""
    ) -> Reply:
        """Handle a free-text message (commands go through :meth:`on_command`)."""
        if self.limiter and not self.limiter.allow(user_id):
            return Reply(t(self.lang_of(user_id), "rate_limited"))

        flow = self._flows.get(user_id)
        if flow and flow.active:
            reply = self.engine.submit(flow, text)
            if not flow.active:
                self._flows.pop(user_id, None)
            return reply

        lang = detect_language(text, default=self.lang_of(user_id))
        self._lang[user_id] = lang
        self._last_text[user_id] = text

        if text.strip().lower().rstrip("!.") in _GREETINGS:
            return Reply(t(lang, "welcome", business=self.config.name))
        if self._wants_booking(text):
            return self._start_flow("booking", user_id, username)
        return await self._answer(text, lang)

    async def on_command(
        self, user_id: int, command: str, username: str = "", full_name: str = ""
    ) -> Reply:
        """Handle ``/command`` (without the slash)."""
        lang = self.lang_of(user_id)
        if self.limiter and not self.limiter.allow(user_id):
            return Reply(t(lang, "rate_limited"))

        if command == "cancel":
            self._flows.pop(user_id, None)
            return Reply(t(lang, "cancelled"))
        if command in {"start", "help"}:
            self._flows.pop(user_id, None)
            key = "welcome" if command == "start" else "help"
            return Reply(t(lang, key, business=self.config.name))
        if command == "book":
            return self._start_flow("booking", user_id, username)
        if command == "mybookings":
            return self._my_bookings(user_id)
        if command in {"lead", "contact"}:
            return self._start_flow("lead", user_id, username)
        if command == "human":
            return self._handoff(user_id, username, full_name)
        if command == "services":
            lines = [t(lang, "services_title")] + [
                f"{i}. {s.name(lang)}" for i, s in enumerate(self.config.services, 1)
            ]
            return Reply("\n".join(lines))
        if command == "hours":
            sch = self.config.schedule
            days = t(lang, "days").split(",")
            span = ",".join(days[d] for d in sch.open_weekdays)
            return Reply(
                t(
                    lang,
                    "hours_text",
                    open=sch.open.strftime("%H:%M"),
                    close=sch.close.strftime("%H:%M"),
                    days=span,
                )
            )
        return Reply(t(lang, "help", business=self.config.name))

    async def on_callback(self, user_id: int, data: str, username: str = "") -> Reply:
        """Handle an inline button: ``bk:<cancel|resched|ok>:<booking id>``."""
        parts = data.split(":")
        if len(parts) != 3 or parts[0] != "bk" or not parts[2].isdigit():
            return Reply("")
        action, booking_id = parts[1], int(parts[2])
        booking = self.db.get_booking(booking_id)
        lang = self._lang_for(user_id, booking)
        missing = Reply(t(lang, "booking_not_found"))
        if booking is None or booking.user_id != user_id:
            return missing
        if action == "cancel":
            self._flows.pop(user_id, None)
            return self.engine.cancel_booking(booking_id, user_id, lang) or missing
        if action == "ok":
            return self.engine.confirm_booking(booking_id, user_id, lang) or missing
        if action == "resched":
            started = self.engine.start_reschedule(booking_id, user_id, lang, username)
            if started is None:
                return missing
            flow, reply = started
            if flow.active:
                self._flows[user_id] = flow
            return reply
        return Reply("")

    # ---- scheduler entry points (the aiogram loop only calls these) ------
    def due_reminders(self, now: datetime | None = None) -> list[ReminderMessage]:
        now = now or self._now()
        today = now.date().isoformat()
        offsets = self.config.reminder_offsets_minutes
        upcoming = self.db.bookings_from(today)
        out: list[ReminderMessage] = []
        for due in due_reminders(upcoming, self.db.sent_reminders(), now, offsets):
            b = due.booking
            lang = b.lang
            key = "reminder_confirm" if due.confirm else "reminder"
            text = t(
                lang,
                key,
                service=self.engine.service_name(b.service, lang),
                business=self.config.name,
                date=b.date,
                time=b.time,
            )
            buttons = (
                [
                    (t(lang, "btn_confirm"), f"bk:ok:{b.id}"),
                    (t(lang, "btn_cancel"), f"bk:cancel:{b.id}"),
                ]
                if due.confirm
                else []
            )
            out.append(ReminderMessage(b.user_id, text, b.id, due.offset_minutes, buttons))
        return out

    def mark_reminder_sent(self, booking_id: int, offset_minutes: int) -> None:
        self.db.mark_reminder(booking_id, offset_minutes)

    def digest_job(self, now: datetime | None = None) -> DigestJob | None:
        """The owner digest when it is due (configured time reached, not yet sent today)."""
        now = now or self._now()
        if not digest_due(now, self.config.digest_time, self.db.get_meta(_DIGEST_DATE_KEY)):
            return None
        today = now.date()
        last_lead = int(self.db.get_meta(_DIGEST_LEAD_KEY) or 0)
        lang = self.config.default_lang
        text = build_digest(
            lang=lang,
            business=self.config.name,
            today=today,
            today_bookings=self.db.bookings_on(today.isoformat()),
            tomorrow_bookings=self.db.bookings_on((today + timedelta(days=1)).isoformat()),
            new_leads=self.db.leads_since(last_lead),
            open_handoffs=self.db.open_handoffs(),
            service_name=lambda sid: self.engine.service_name(sid, lang),
        )
        return DigestJob(text, today.isoformat(), self.db.max_lead_id())

    def mark_digest_sent(self, job: DigestJob) -> None:
        self.db.set_meta(_DIGEST_DATE_KEY, job.date)
        self.db.set_meta(_DIGEST_LEAD_KEY, str(job.last_lead_id))

    def resolve_handoff(self, user_id: int) -> None:
        """Called when the owner answers a customer with /reply."""
        self.db.resolve_handoffs(user_id)

    # ---- internals -----------------------------------------------------
    def _lang_for(self, user_id: int, booking: Booking | None) -> str:
        if user_id in self._lang:
            return self._lang[user_id]
        return booking.lang if booking else self.config.default_lang

    def _my_bookings(self, user_id: int) -> Reply:
        lang = self.lang_of(user_id)
        bookings = self.engine.user_bookings(user_id)
        if not bookings:
            return Reply(t(lang, "no_bookings"))
        cards = []
        for b in bookings:
            lines = [self.engine.service_name(b.service, lang), f"{b.date} {b.time}"]
            if b.confirmed:
                lines.append(t(lang, "status_confirmed"))
            buttons = [
                (t(lang, "btn_cancel"), f"bk:cancel:{b.id}"),
                (t(lang, "btn_reschedule"), f"bk:resched:{b.id}"),
            ]
            cards.append(Card("\n".join(lines), buttons))
        return Reply(t(lang, "mybookings_title"), cards=cards)

    def _handoff(self, user_id: int, username: str, full_name: str) -> Reply:
        lang = self.lang_of(user_id)
        self._flows.pop(user_id, None)
        last = self._last_text.get(user_id, "")
        name = full_name or username or str(user_id)
        self.db.add_lead(user_id, username, name, "", source="handoff", note=last)
        who = f"@{username}" if username else name
        notice = (
            f"Human requested by {who} (id {user_id}).\n"
            f"Last message: {last or '-'}\nReply with: /reply {user_id} <text>"
        )
        return Reply(t(lang, "handoff_ok"), admin_notice=notice)

    async def _answer(self, text: str, lang: str) -> Reply:
        hits = self.kb.search(text, lang=lang)
        if not hits:
            return Reply(t(lang, "no_answer"))
        answer = hits[0].entry.answer
        if self.llm is not None:
            system, user = build_prompt(self.config.name, text, hits, lang)
            polished = await self.llm.complete(system, user)
            if polished:
                answer = polished
        return Reply(answer)

    def export_csv(self, kind: str) -> str:
        """CSV text for the owner: ``leads`` or ``bookings``."""
        return self.db.export_bookings_csv() if kind == "bookings" else self.db.export_leads_csv()
