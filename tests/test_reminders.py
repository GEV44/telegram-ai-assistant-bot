from datetime import datetime

from tg_assistant.db import Booking
from tg_assistant.reminders import due_reminders, passed_offsets

OFFSETS = (1440, 120)


def bk(
    id: int = 1, date: str = "2026-11-12", time: str = "10:00", confirmed: bool = False
) -> Booking:
    return Booking(id, 7, "cleaning", date, time, "Anna", "+37477123456", confirmed, "en")


def test_nothing_due_more_than_24h_before() -> None:
    assert due_reminders([bk()], set(), datetime(2026, 11, 11, 9, 59), OFFSETS) == []


def test_24h_reminder_due_exactly_on_time() -> None:
    (due,) = due_reminders([bk()], set(), datetime(2026, 11, 11, 10, 0), OFFSETS)
    assert due.offset_minutes == 1440 and due.confirm is False and due.booking.id == 1


def test_already_sent_is_not_repeated() -> None:
    now = datetime(2026, 11, 11, 12, 0)
    assert due_reminders([bk()], {(1, 1440)}, now, OFFSETS) == []


def test_2h_reminder_carries_confirm_buttons() -> None:
    (due,) = due_reminders([bk()], {(1, 1440)}, datetime(2026, 11, 12, 8, 0), OFFSETS)
    assert due.offset_minutes == 120 and due.confirm is True


def test_confirmed_booking_gets_no_confirm_buttons() -> None:
    (due,) = due_reminders([bk(confirmed=True)], set(), datetime(2026, 11, 12, 8, 0), OFFSETS)
    assert due.offset_minutes == 120 and due.confirm is False


def test_stale_24h_reminder_is_skipped_after_downtime() -> None:
    dues = due_reminders([bk()], set(), datetime(2026, 11, 12, 8, 30), OFFSETS)
    assert [d.offset_minutes for d in dues] == [120]


def test_nothing_after_the_visit_started() -> None:
    assert due_reminders([bk()], set(), datetime(2026, 11, 12, 10, 0), OFFSETS) == []


def test_several_bookings_sorted_by_start() -> None:
    later, sooner = bk(1, time="12:00"), bk(2, time="10:00")
    dues = due_reminders([later, sooner], set(), datetime(2026, 11, 12, 9, 0), OFFSETS)
    assert [d.booking.id for d in dues] == [2, 1]


def test_custom_offsets_single_offset_is_the_confirm_one() -> None:
    (due,) = due_reminders([bk()], set(), datetime(2026, 11, 12, 9, 0), (60,))
    assert due.offset_minutes == 60 and due.confirm is True


def test_no_offsets_means_no_reminders() -> None:
    assert due_reminders([bk()], set(), datetime(2026, 11, 12, 9, 0), ()) == []


def test_passed_offsets_for_a_last_minute_booking() -> None:
    start = datetime(2026, 11, 12, 10, 0)
    assert passed_offsets(start, datetime(2026, 11, 12, 9, 0), OFFSETS) == [1440, 120]
    assert passed_offsets(start, datetime(2026, 11, 11, 20, 0), OFFSETS) == [1440]
    assert passed_offsets(start, datetime(2026, 11, 11, 8, 0), OFFSETS) == []
