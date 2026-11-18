"""Cancel / reschedule / confirm, reminder state, digest wiring and config."""

import asyncio
import sqlite3
from datetime import datetime, time
from pathlib import Path

import pytest

from tg_assistant.assistant import Assistant
from tg_assistant.booking import BookingEngine, Step
from tg_assistant.config import BusinessConfig, load_business
from tg_assistant.db import Booking, Database, SlotTakenError

TOMORROW = "2026-11-12"  # Thursday; conftest NOW is Wed 2026-11-11 08:00


def add(
    db: Database, d: str = TOMORROW, tm: str = "10:00", user: int = 1, lang: str = "en"
) -> Booking:
    return db.add_booking(user, "cleaning", d, tm, "Anna", "+37477123456", lang=lang)


# ---- database ---------------------------------------------------------
def test_cancel_frees_the_slot(db: Database) -> None:
    b = add(db)
    assert db.cancel_booking(b.id) is True
    assert db.cancel_booking(b.id) is False
    add(db, user=2)  # same slot is bookable again


def test_move_frees_old_slot_and_resets_confirmation(db: Database) -> None:
    b = add(db)
    db.confirm_booking(b.id)
    db.mark_reminder(b.id, 1440)
    moved = db.move_booking(b.id, TOMORROW, "11:00")
    assert moved and moved.time == "11:00" and moved.confirmed is False
    assert db.sent_reminders() == set()
    assert db.booked_times(TOMORROW) == {"11:00"}


def test_move_to_taken_slot_is_atomic(db: Database) -> None:
    b = add(db)
    add(db, tm="11:00", user=2)
    with pytest.raises(SlotTakenError):
        db.move_booking(b.id, TOMORROW, "11:00")
    assert db.get_booking(b.id) == b


def test_confirm_booking_is_recorded(db: Database) -> None:
    b = add(db)
    assert db.get_booking(b.id).confirmed is False  # type: ignore[union-attr]
    assert db.confirm_booking(b.id) is True
    assert db.get_booking(b.id).confirmed is True  # type: ignore[union-attr]
    assert db.confirm_booking(999) is False


def test_reminder_state_survives_restart(tmp_path: Path) -> None:
    path = str(tmp_path / "a.db")
    first = Database(path)
    b = add(first)
    first.mark_reminder(b.id, 1440)
    first.mark_reminder(b.id, 1440)  # idempotent
    first.close()
    second = Database(path)
    assert second.sent_reminders() == {(b.id, 1440)}
    second.close()


def test_cancel_removes_reminder_rows(db: Database) -> None:
    b = add(db)
    db.mark_reminder(b.id, 120)
    db.cancel_booking(b.id)
    assert db.sent_reminders() == set()


def test_old_database_is_migrated(tmp_path: Path) -> None:
    path = tmp_path / "old.db"
    conn = sqlite3.connect(path)
    conn.executescript(
        "CREATE TABLE bookings (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL,"
        " service TEXT NOT NULL, date TEXT NOT NULL, time TEXT NOT NULL, name TEXT NOT NULL,"
        " phone TEXT NOT NULL, created_at TEXT NOT NULL, UNIQUE (date, time));"
        "CREATE TABLE leads (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL,"
        " username TEXT NOT NULL DEFAULT '', name TEXT NOT NULL, phone TEXT NOT NULL,"
        " source TEXT NOT NULL, note TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL);"
        "INSERT INTO bookings VALUES (1, 5, 'cleaning', '2026-11-12', '10:00', 'Old', '+1', 'x');"
    )
    conn.commit()
    conn.close()
    db = Database(str(path))
    old = db.get_booking(1)
    assert old and old.confirmed is False and old.lang == "en"
    assert db.confirm_booking(1)
    db.close()


def test_meta_roundtrip(db: Database) -> None:
    assert db.get_meta("k") is None
    db.set_meta("k", "v1")
    db.set_meta("k", "v2")
    assert db.get_meta("k") == "v2"


def test_handoffs_open_until_resolved(db: Database) -> None:
    db.add_lead(5, "bob", "Bob", "", source="handoff", note="help")
    db.add_lead(6, "eve", "Eve", "+3", source="lead")
    assert [h.name for h in db.open_handoffs()] == ["Bob"]
    assert [x.name for x in db.leads_since(0, sources=("lead",))] == ["Eve"]
    db.resolve_handoffs(5)
    assert db.open_handoffs() == []


# ---- engine: cancel / reschedule -------------------------------------
def test_user_bookings_only_upcoming_and_own(engine: BookingEngine, db: Database) -> None:
    add(db, "2026-11-10", "10:00")  # past
    mine = add(db, TOMORROW, "12:00")
    add(db, TOMORROW, "14:00", user=2)
    assert [b.id for b in engine.user_bookings(1)] == [mine.id]


def test_cancel_checks_ownership(engine: BookingEngine, db: Database) -> None:
    b = add(db)
    assert engine.cancel_booking(b.id, user_id=99) is None
    reply = engine.cancel_booking(b.id, user_id=1)
    assert reply and "cancelled" in reply.text and "Anna" in (reply.admin_notice or "")
    assert db.booked_times(TOMORROW) == set()


def test_reschedule_flow_reuses_date_time_steps(engine: BookingEngine, db: Database) -> None:
    b = add(db)
    started = engine.start_reschedule(b.id, 1, "en")
    assert started is not None
    flow, reply = started
    assert flow.step is Step.DATE and reply.options  # date picker
    engine.submit(flow, "2026-11-13")
    assert flow.step is Step.TIME
    done = engine.submit(flow, "15:00")
    assert flow.step is Step.DONE
    assert "15:00" in done.text
    notice = done.admin_notice or ""
    assert "2026-11-12 10:00" in notice and "2026-11-13 15:00" in notice
    assert db.booked_times(TOMORROW) == set() and db.booked_times("2026-11-13") == {"15:00"}


def test_reschedule_slot_race_keeps_old_booking(engine: BookingEngine, db: Database) -> None:
    b = add(db)
    flow, _ = engine.start_reschedule(b.id, 1, "en")  # type: ignore[misc]
    engine.submit(flow, "2026-11-13")
    add(db, "2026-11-13", "15:00", user=2)  # someone else takes it meanwhile
    reply = engine.submit(flow, "15:00")
    assert flow.step is Step.TIME and "15:00" not in reply.options
    assert db.get_booking(b.id) == b


def test_reschedule_of_foreign_booking_refused(engine: BookingEngine, db: Database) -> None:
    b = add(db)
    assert engine.start_reschedule(b.id, 2, "en") is None


def test_new_booking_skips_reminders_already_in_the_past(
    config: BusinessConfig, db: Database
) -> None:
    late = BookingEngine(config, db, now=lambda: datetime(2026, 11, 11, 15, 0))
    flow, _ = late.start("booking", "en", 1)
    for text in ("Professional cleaning", "2026-11-12", "10:00", "Anna", "+37477123456", "Confirm"):
        late.submit(flow, text)
    (b,) = db.list_bookings()
    assert db.sent_reminders() == {(b.id, 1440)}  # 24h point already passed, 2h still ahead


# ---- assistant --------------------------------------------------------
def _run(coro):  # type: ignore[no-untyped-def]
    return asyncio.run(coro)


def test_mybookings_cards_have_cancel_and_reschedule(assistant: Assistant, db: Database) -> None:
    b = add(db)
    reply = _run(assistant.on_command(1, "mybookings"))
    assert len(reply.cards) == 1
    labels = {data for _, data in reply.cards[0].buttons}
    assert labels == {f"bk:cancel:{b.id}", f"bk:resched:{b.id}"}


def test_mybookings_empty(assistant: Assistant) -> None:
    assert "/book" in _run(assistant.on_command(1, "mybookings")).text


def test_cancel_callback_notifies_owner(assistant: Assistant, db: Database) -> None:
    b = add(db)
    reply = _run(assistant.on_callback(1, f"bk:cancel:{b.id}", "anna"))
    assert reply.admin_notice and "cancel" in reply.admin_notice.lower()
    assert db.get_booking(b.id) is None


def test_callback_for_someone_elses_booking_is_ignored(assistant: Assistant, db: Database) -> None:
    b = add(db)
    reply = _run(assistant.on_callback(2, f"bk:cancel:{b.id}"))
    assert reply.admin_notice is None and db.get_booking(b.id) is not None


def test_garbage_callback_is_harmless(assistant: Assistant) -> None:
    assert _run(assistant.on_callback(1, "bk:cancel:abc")).text == ""
    assert _run(assistant.on_callback(1, "zzz")).text == ""


def test_reschedule_callback_then_text_flow(assistant: Assistant, db: Database) -> None:
    b = add(db)
    first = _run(assistant.on_callback(1, f"bk:resched:{b.id}"))
    assert first.options
    _run(assistant.on_message(1, "2026-11-13"))
    done = _run(assistant.on_message(1, "15:00"))
    assert done.admin_notice and db.get_booking(b.id).time == "15:00"  # type: ignore[union-attr]


def test_confirm_callback_marks_booking(assistant: Assistant, db: Database) -> None:
    b = add(db)
    reply = _run(assistant.on_callback(1, f"bk:ok:{b.id}"))
    assert reply.text and db.get_booking(b.id).confirmed is True  # type: ignore[union-attr]


def test_due_reminders_are_translated_and_persisted(assistant: Assistant, db: Database) -> None:
    b = add(db, lang="ru")
    now = datetime(2026, 11, 12, 8, 0)  # 2h before
    (msg,) = assistant.due_reminders(now)
    assert (
        msg.user_id == 1
        and "10:00" in msg.text
        and assistant.config.services[1].name("ru") in msg.text
    )
    assert {d for _, d in msg.buttons} == {f"bk:ok:{b.id}", f"bk:cancel:{b.id}"}
    assistant.mark_reminder_sent(msg.booking_id, msg.offset_minutes)
    assert assistant.due_reminders(now) == []  # nothing twice


def test_24h_reminder_has_no_buttons(assistant: Assistant, db: Database) -> None:
    add(db)
    (msg,) = assistant.due_reminders(datetime(2026, 11, 11, 10, 0))
    assert msg.buttons == [] and msg.offset_minutes == 1440


def test_cancelled_booking_gets_no_reminder(assistant: Assistant, db: Database) -> None:
    b = add(db)
    db.cancel_booking(b.id)
    assert assistant.due_reminders(datetime(2026, 11, 12, 8, 0)) == []


def test_digest_job_once_per_day(assistant: Assistant, db: Database) -> None:
    add(db)
    db.add_lead(5, "eve", "Eve", "+3", source="lead")
    db.add_lead(6, "bob", "Bob", "", source="handoff", note="help")
    assert assistant.digest_job(datetime(2026, 11, 11, 19, 59)) is None
    job = assistant.digest_job(datetime(2026, 11, 11, 20, 0))
    assert job and "Eve" in job.text and "Bob" in job.text and "Anna" in job.text
    assistant.mark_digest_sent(job)
    assert assistant.digest_job(datetime(2026, 11, 11, 21, 0)) is None
    next_day = assistant.digest_job(datetime(2026, 11, 12, 20, 0))
    assert next_day and "Eve" not in next_day.text  # leads are only listed once
    assert "Bob" in next_day.text  # handoff stays open until resolved


def test_digest_disabled_when_not_configured(config: BusinessConfig, assistant: Assistant) -> None:
    assistant.config = BusinessConfig(config.name, config.services, config.schedule)
    assert assistant.digest_job(datetime(2026, 11, 11, 23, 0)) is None


# ---- config -----------------------------------------------------------
def test_config_defaults_and_example(config: BusinessConfig) -> None:
    assert config.reminder_offsets_minutes == (1440, 120)
    assert config.digest_time == time(20, 0)
    plain = BusinessConfig(config.name, config.services)
    assert plain.reminder_offsets_minutes == (1440, 120) and plain.digest_time is None


def test_config_custom_offsets_sorted_unique(tmp_path: Path) -> None:
    f = tmp_path / "b.yaml"
    f.write_text(
        "business: {name: X}\nservices: [{id: a, names: {en: A}}]\n"
        "reminders: {offsets_hours: [1, 48, 1, 0.5]}\n",
        encoding="utf-8",
    )
    assert load_business(f).reminder_offsets_minutes == (2880, 60, 30)
    assert load_business(f).digest_time is None


# ---- aiogram loop body (fake bot, no network) -------------------------
class FakeBot:
    def __init__(self) -> None:
        self.sent: list[tuple[int, str]] = []

    async def send_message(self, chat_id: int, text: str, **_: object) -> None:
        self.sent.append((chat_id, text))


def test_tick_sends_reminder_and_digest_once(assistant: Assistant, db: Database) -> None:
    from tg_assistant.bot import tick

    add(db)
    bot = FakeBot()
    now = datetime(2026, 11, 11, 20, 0)  # 24h+ before the visit, digest time
    for _ in range(2):  # a second minute must not repeat anything
        asyncio.run(tick(bot, assistant, 555, now))  # type: ignore[arg-type]
    chats = [chat for chat, _ in bot.sent]
    assert chats.count(1) == 1 and chats.count(555) == 1
