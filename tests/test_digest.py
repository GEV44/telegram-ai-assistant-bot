from datetime import date, datetime, time

from tg_assistant.db import Booking, Lead
from tg_assistant.digest import build_digest, digest_due


def bk(id: int, d: str, tm: str, name: str, confirmed: bool = False) -> Booking:
    return Booking(id, 7, "cleaning", d, tm, name, "+37477123456", confirmed, "en")


def lead(id: int, name: str, source: str = "lead", note: str = "") -> Lead:
    return Lead(id, 7, "anna", name, "+37477000000", source, note, "2026-11-11 10:00:00", False)


def service_name(service_id: str) -> str:
    return {"cleaning": "Cleaning"}.get(service_id, service_id)


def digest(lang: str = "en", **kw: object) -> str:
    args: dict[str, object] = {
        "lang": lang,
        "business": "Smile Studio",
        "today": date(2026, 11, 11),
        "today_bookings": [],
        "tomorrow_bookings": [],
        "new_leads": [],
        "open_handoffs": [],
        "service_name": service_name,
    }
    args.update(kw)
    return build_digest(**args)  # type: ignore[arg-type]


def test_digest_due_only_after_time_and_once_per_day() -> None:
    at = time(20, 0)
    assert not digest_due(datetime(2026, 11, 11, 19, 59), at, None)
    assert digest_due(datetime(2026, 11, 11, 20, 0), at, None)
    assert digest_due(datetime(2026, 11, 11, 20, 0), at, "2026-11-10")
    assert not digest_due(datetime(2026, 11, 11, 23, 0), at, "2026-11-11")


def test_digest_disabled_without_time() -> None:
    assert not digest_due(datetime(2026, 11, 11, 23, 0), None, None)


def test_digest_lists_everything() -> None:
    text = digest(
        today_bookings=[
            bk(2, "2026-11-11", "11:00", "Boris"),
            bk(1, "2026-11-11", "09:00", "Anna"),
        ],
        tomorrow_bookings=[
            bk(3, "2026-11-12", "10:00", "Carl", confirmed=True),
            bk(4, "2026-11-12", "12:00", "Dana"),
        ],
        new_leads=[lead(5, "Eve")],
        open_handoffs=[lead(6, "Fay", source="handoff", note="price?")],
    )
    assert "Smile Studio" in text and "2026-11-11" in text
    assert text.index("Anna") < text.index("Boris")  # sorted by time
    assert "Carl" in text and "Dana" in text
    assert "Eve" in text and "Fay" in text and "price?" in text


def test_digest_unconfirmed_section_lists_only_unconfirmed() -> None:
    text = digest(
        tomorrow_bookings=[
            bk(3, "2026-11-12", "10:00", "Carl", confirmed=True),
            bk(4, "2026-11-12", "12:00", "Dana"),
        ]
    )
    head, _, unconfirmed = text.partition("Not confirmed")
    assert unconfirmed and "Dana" in unconfirmed and "Carl" not in unconfirmed
    assert "Carl" in head


def test_digest_empty_day_still_renders() -> None:
    text = digest()
    assert text.count("\n-") == 4 and "Not confirmed" not in text


def test_digest_is_translated() -> None:
    ru = digest("ru", tomorrow_bookings=[bk(4, "2026-11-12", "12:00", "Dana")])
    hy = digest("hy", tomorrow_bookings=[bk(4, "2026-11-12", "12:00", "Dana")])
    assert "Сегодня" in ru and "Завтра" in ru and "Не подтверждены" in ru
    assert "Այսօր" in hy and "Վաղը" in hy and "Dana" in hy
