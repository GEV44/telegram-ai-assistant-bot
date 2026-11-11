import csv
import io

import pytest

from tg_assistant.db import Database, SlotTakenError


def test_unique_slot_enforced(db: Database) -> None:
    db.add_booking(1, "checkup", "2026-11-12", "10:00", "A", "1234567")
    with pytest.raises(SlotTakenError):
        db.add_booking(2, "cleaning", "2026-11-12", "10:00", "B", "7654321")


def test_same_time_other_day_allowed(db: Database) -> None:
    db.add_booking(1, "checkup", "2026-11-12", "10:00", "A", "1234567")
    db.add_booking(2, "checkup", "2026-11-13", "10:00", "B", "7654321")
    assert len(db.list_bookings()) == 2


def test_leads_export_roundtrip(db: Database) -> None:
    db.add_lead(1, "anna", "Anna", "+37477123456", "lead")
    db.add_lead(2, "", "Борис, Иванов", "", "handoff", note='said "hi"')
    rows = list(csv.DictReader(io.StringIO(db.export_leads_csv())))
    assert [r["name"] for r in rows] == ["Anna", "Борис, Иванов"]
    assert rows[1]["note"] == 'said "hi"' and rows[1]["source"] == "handoff"


def test_export_header_only_when_empty(db: Database) -> None:
    assert db.export_leads_csv().strip() == "id,created_at,name,phone,username,source,note"


def test_bookings_export(db: Database) -> None:
    db.add_booking(1, "cleaning", "2026-11-12", "09:00", "Anna", "+37477123456")
    rows = list(csv.DictReader(io.StringIO(db.export_bookings_csv())))
    assert rows[0]["service"] == "cleaning" and rows[0]["time"] == "09:00"


def test_export_neutralises_formula_injection(db: Database) -> None:
    db.add_lead(1, "x", '=HYPERLINK("http://evil")', "1234567", "lead")
    rows = list(csv.DictReader(io.StringIO(db.export_leads_csv())))
    assert rows[0]["name"].startswith("'=")
