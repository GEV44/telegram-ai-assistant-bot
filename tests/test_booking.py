from datetime import date, datetime

from tg_assistant.booking import BookingEngine, Flow, Reply, Step, normalize_phone
from tg_assistant.config import BusinessConfig
from tg_assistant.db import Database

TOMORROW = "2026-11-12"  # Thursday


def drive(engine: BookingEngine, flow: Flow, *inputs: str) -> Reply:
    reply = Reply("")
    for text in inputs:
        reply = engine.submit(flow, text)
    return reply


def new_flow(engine: BookingEngine) -> Flow:
    flow, _ = engine.start("booking", "en", user_id=1, username="anna")
    return flow


def test_start_offers_services(engine: BookingEngine) -> None:
    _, reply = engine.start("booking", "en", 1)
    assert len(reply.options) == 4


def test_slots_skip_break_and_close(engine: BookingEngine) -> None:
    slots = engine.day_slots(date(2026, 11, 12))
    assert slots[0] == "09:00" and slots[-1] == "17:00"
    assert "13:00" not in slots and len(slots) == 8


def test_sunday_is_closed(engine: BookingEngine) -> None:
    assert engine.day_slots(date(2026, 11, 15)) == []
    assert "2026-11-15" not in engine.open_dates()


def test_past_slots_are_hidden(config: BusinessConfig, db: Database) -> None:
    late = BookingEngine(config, db, now=lambda: datetime(2026, 11, 11, 15, 30))
    assert late.free_slots(date(2026, 11, 11)) == ["16:00", "17:00"]


def test_full_happy_path(engine: BookingEngine, db: Database) -> None:
    flow = new_flow(engine)
    reply = drive(
        engine, flow, "Professional cleaning", TOMORROW, "10:00", "Anna", "+374 77 123456"
    )
    assert flow.step is Step.CONFIRM
    assert "10:00" in reply.text
    done = engine.submit(flow, "Confirm")
    assert flow.step is Step.DONE
    assert "Done" in done.text
    assert done.admin_notice and "Anna" in done.admin_notice
    assert db.list_bookings()[0].phone == "+37477123456"


def test_service_by_number_and_other_language(engine: BookingEngine) -> None:
    flow = new_flow(engine)
    engine.submit(flow, "2")
    assert flow.service and flow.service.id == "cleaning"
    flow2 = new_flow(engine)
    engine.submit(flow2, "Отбеливание зубов")
    assert flow2.service and flow2.service.id == "whitening"


def test_invalid_service_repeats_step(engine: BookingEngine) -> None:
    flow = new_flow(engine)
    reply = engine.submit(flow, "haircut")
    assert flow.step is Step.SERVICE
    assert "pick one" in reply.text


def test_date_formats(engine: BookingEngine) -> None:
    flow = new_flow(engine)
    drive(engine, flow, "1", "12.11")
    assert flow.step is Step.TIME and flow.date == TOMORROW


def test_closed_or_garbage_date_rejected(engine: BookingEngine) -> None:
    flow = new_flow(engine)
    engine.submit(flow, "1")
    engine.submit(flow, "2026-11-15")  # Sunday
    assert flow.step is Step.DATE
    engine.submit(flow, "someday")
    assert flow.step is Step.DATE


def test_invalid_time_rejected(engine: BookingEngine) -> None:
    flow = new_flow(engine)
    drive(engine, flow, "1", TOMORROW, "13:00")  # lunch break
    assert flow.step is Step.TIME


def test_bad_name_and_phone(engine: BookingEngine) -> None:
    flow = new_flow(engine)
    drive(engine, flow, "1", TOMORROW, "09:00", "A")
    assert flow.step is Step.NAME
    drive(engine, flow, "Anna", "call me maybe")
    assert flow.step is Step.PHONE


def test_decline_confirmation_cancels(engine: BookingEngine, db: Database) -> None:
    flow = new_flow(engine)
    drive(engine, flow, "1", TOMORROW, "09:00", "Anna", "077123456", "no")
    assert flow.step is Step.CANCELLED
    assert db.list_bookings() == []


def test_unclear_confirmation_reprompts(engine: BookingEngine) -> None:
    flow = new_flow(engine)
    reply = drive(engine, flow, "1", TOMORROW, "09:00", "Anna", "077123456", "hmm")
    assert flow.step is Step.CONFIRM and reply.options


def test_russian_confirmation(engine: BookingEngine) -> None:
    flow, _ = engine.start("booking", "ru", 7)
    drive(engine, flow, "1", TOMORROW, "09:00", "Анна", "077123456")
    done = engine.submit(flow, "Подтвердить")
    assert flow.step is Step.DONE and "Готово" in done.text


def test_slot_conflict_between_two_users(engine: BookingEngine, db: Database) -> None:
    a, b = new_flow(engine), new_flow(engine)
    b.user_id = 2
    drive(engine, a, "1", TOMORROW, "11:00", "Anna", "077123456")
    drive(engine, b, "1", TOMORROW, "11:00", "Boris", "077654321")
    engine.submit(a, "yes")
    reply = engine.submit(b, "yes")
    assert b.step is Step.TIME
    assert "just taken" in reply.text and "11:00" not in reply.options
    assert len(db.list_bookings()) == 1


def test_booked_slot_disappears_from_free_slots(engine: BookingEngine) -> None:
    flow = new_flow(engine)
    drive(engine, flow, "1", TOMORROW, "10:00", "Anna", "077123456", "yes")
    assert "10:00" not in engine.free_slots(date(2026, 11, 12))


def test_fully_booked_day_not_offered(engine: BookingEngine, db: Database) -> None:
    for slot in engine.day_slots(date(2026, 11, 12)):
        db.add_booking(9, "checkup", TOMORROW, slot, "X", "1234567")
    assert TOMORROW not in engine.open_dates()


def test_lead_flow(engine: BookingEngine, db: Database) -> None:
    flow, first = engine.start("lead", "en", 5, "boris")
    assert flow.step is Step.NAME and "name" in first.text.lower()
    reply = drive(engine, flow, "Boris", "+7 999 123-45-67")
    assert flow.step is Step.DONE
    assert reply.admin_notice and "Boris" in reply.admin_notice
    assert db.count_leads() == 1


def test_phone_normalisation() -> None:
    assert normalize_phone("+374 (77) 123-456") == "+37477123456"
    assert normalize_phone("077123456") == "077123456"
    assert normalize_phone("12") is None
    assert normalize_phone("abc") is None
