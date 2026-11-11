import asyncio
from collections.abc import Coroutine
from typing import Any

from tg_assistant.assistant import Assistant
from tg_assistant.booking import Reply
from tg_assistant.knowledge import Hit, KnowledgeBase
from tg_assistant.llm import build_prompt
from tg_assistant.ratelimit import RateLimiter


def run(coro: Coroutine[Any, Any, Reply]) -> Reply:
    return asyncio.run(coro)


def say(a: Assistant, text: str, uid: int = 1) -> Reply:
    return run(a.on_message(uid, text, "anna", "Anna"))


def cmd(a: Assistant, name: str, uid: int = 1) -> Reply:
    return run(a.on_command(uid, name, "anna", "Anna"))


def test_faq_answer_english(assistant: Assistant) -> None:
    assert "09:00" in say(assistant, "What are your opening hours?").text


def test_reply_follows_user_language(assistant: Assistant) -> None:
    assert "Детский" in say(assistant, "Вы лечите детей?").text
    assert assistant.lang_of(1) == "ru"


def test_unknown_question_offers_human(assistant: Assistant) -> None:
    assert "/human" in say(assistant, "qwerty zxcvb").text


def test_greeting_returns_welcome(assistant: Assistant) -> None:
    assert "Smile Studio" in say(assistant, "Hello").text


def test_booking_intent_starts_flow(assistant: Assistant) -> None:
    reply = say(assistant, "I want to book an appointment")
    assert reply.options and "service" in reply.text.lower()


def test_long_question_with_book_word_is_faq(assistant: Assistant) -> None:
    text = "Can I cancel or reschedule my appointment if something comes up suddenly?"
    assert "24 hours" in say(assistant, text).text


def test_full_booking_via_assistant_notifies_admin(assistant: Assistant) -> None:
    cmd(assistant, "book")
    for step in ("1", "2026-11-12", "09:00", "Anna", "077123456"):
        say(assistant, step)
    done = say(assistant, "yes")
    assert done.admin_notice and "New booking" in done.admin_notice
    assert "Anna" in assistant.export_csv("bookings")


def test_cancel_command_aborts_flow(assistant: Assistant) -> None:
    cmd(assistant, "book")
    cmd(assistant, "cancel")
    assert "09:00" in say(assistant, "opening hours?").text


def test_handoff_saves_lead_and_notifies(assistant: Assistant) -> None:
    say(assistant, "my crown fell off, help")
    reply = cmd(assistant, "human")
    assert reply.admin_notice and "crown" in reply.admin_notice and "/reply 1" in reply.admin_notice
    assert "handoff" in assistant.export_csv("leads")


def test_lead_command_collects_contact(assistant: Assistant) -> None:
    cmd(assistant, "lead")
    say(assistant, "Anna")
    done = say(assistant, "+374 77 123456")
    assert done.admin_notice and "New lead" in done.admin_notice


def test_services_and_hours_commands(assistant: Assistant) -> None:
    assert "1. Check-up" in cmd(assistant, "services").text
    assert "09:00 - 18:00" in cmd(assistant, "hours").text


def test_rate_limit_blocks_spam(assistant: Assistant) -> None:
    assistant.limiter = RateLimiter(5, 60, clock=lambda: 0.0)
    replies = [say(assistant, "opening hours?", uid=9).text for _ in range(7)]
    assert "too fast" in replies[-1]
    assert "too fast" not in replies[0]


def test_rate_limiter_window_expires() -> None:
    now = [0.0]
    rl = RateLimiter(2, 10, clock=lambda: now[0])
    assert rl.allow(1) and rl.allow(1) and not rl.allow(1)
    assert rl.allow(2)
    now[0] = 11.0
    assert rl.allow(1)


class FakeLLM:
    def __init__(self, answer: str | None) -> None:
        self.answer = answer
        self.prompts: list[tuple[str, str]] = []

    async def complete(self, system: str, user: str) -> str | None:
        self.prompts.append((system, user))
        return self.answer


def test_llm_polishes_grounded_answer(assistant: Assistant) -> None:
    llm = FakeLLM("We open at nine.")
    assistant.llm = llm
    assert say(assistant, "opening hours?").text == "We open at nine."
    assert "09:00" in llm.prompts[0][0]  # retrieved facts are in the prompt


def test_llm_failure_falls_back_to_kb(assistant: Assistant) -> None:
    assistant.llm = FakeLLM(None)
    assert "09:00" in say(assistant, "opening hours?").text


def test_llm_not_called_without_kb_hit(assistant: Assistant) -> None:
    llm = FakeLLM("hallucination")
    assistant.llm = llm
    assert "hallucination" not in say(assistant, "qwerty zxcvb").text
    assert llm.prompts == []


def test_prompt_is_grounded(kb: KnowledgeBase) -> None:
    hits: list[Hit] = kb.search("opening hours", lang="en")
    system, user = build_prompt("Smile Studio", "opening hours", hits, "ru")
    assert "Russian" in system and "ONLY" in system and user == "opening hours"
