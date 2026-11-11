"""Transport-independent assistant brain: routing, language, FAQ, flows, handoff."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime

from .booking import BookingEngine, Flow, Reply
from .config import BusinessConfig
from .db import Database
from .i18n import t
from .knowledge import KnowledgeBase
from .lang import detect_language
from .llm import LLM, build_prompt
from .ratelimit import RateLimiter

_GREETINGS = {"hi", "hello", "hey", "привет", "здравствуйте", "добрый", "բարև", "ողջույն", "/start"}
_BOOK_STEMS = ("book", "appoint", "reserv", "запис", "бронир", "ամրագր", "գրանցվ", "գրանցում")
_MAX_INTENT_WORDS = 6


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

    # ---- internals -----------------------------------------------------
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
