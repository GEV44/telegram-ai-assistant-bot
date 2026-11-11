"""SQLite storage: bookings (unique slots) and captured leads."""

from __future__ import annotations

import csv
import io
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime


class SlotTakenError(Exception):
    """Raised when the requested date/time is already booked."""


@dataclass(frozen=True)
class Booking:
    id: int
    user_id: int
    service: str
    date: str
    time: str
    name: str
    phone: str


_SCHEMA = """
CREATE TABLE IF NOT EXISTS bookings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    service TEXT NOT NULL,
    date TEXT NOT NULL,
    time TEXT NOT NULL,
    name TEXT NOT NULL,
    phone TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE (date, time)
);
CREATE TABLE IF NOT EXISTS leads (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    username TEXT NOT NULL DEFAULT '',
    name TEXT NOT NULL,
    phone TEXT NOT NULL,
    source TEXT NOT NULL,
    note TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL
);
"""


def _now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S")


class Database:
    """Thin synchronous wrapper; queries are tiny so they are fine inside handlers."""

    def __init__(self, path: str = ":memory:") -> None:
        self.conn = sqlite3.connect(path)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(_SCHEMA)

    def close(self) -> None:
        self.conn.close()

    # ---- bookings ------------------------------------------------------
    def booked_times(self, date: str) -> set[str]:
        rows = self.conn.execute("SELECT time FROM bookings WHERE date = ?", (date,)).fetchall()
        return {r["time"] for r in rows}

    def add_booking(
        self, user_id: int, service: str, date: str, time: str, name: str, phone: str
    ) -> Booking:
        """Insert atomically; the UNIQUE(date, time) index makes double-booking impossible."""
        try:
            with self.conn:
                cur = self.conn.execute(
                    "INSERT INTO bookings (user_id, service, date, time, name, phone, created_at) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (user_id, service, date, time, name, phone, _now()),
                )
        except sqlite3.IntegrityError as exc:
            raise SlotTakenError(f"{date} {time} is already booked") from exc
        return Booking(int(cur.lastrowid or 0), user_id, service, date, time, name, phone)

    def list_bookings(self) -> list[Booking]:
        rows = self.conn.execute("SELECT * FROM bookings ORDER BY date, time").fetchall()
        return [
            Booking(
                r["id"], r["user_id"], r["service"], r["date"], r["time"], r["name"], r["phone"]
            )
            for r in rows
        ]

    # ---- leads ---------------------------------------------------------
    def add_lead(
        self, user_id: int, username: str, name: str, phone: str, source: str, note: str = ""
    ) -> int:
        with self.conn:
            cur = self.conn.execute(
                "INSERT INTO leads (user_id, username, name, phone, source, note, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (user_id, username, name, phone, source, note, _now()),
            )
        return int(cur.lastrowid or 0)

    def count_leads(self) -> int:
        return int(self.conn.execute("SELECT COUNT(*) FROM leads").fetchone()[0])

    # ---- export --------------------------------------------------------
    def export_leads_csv(self) -> str:
        return self._csv(
            "SELECT id, created_at, name, phone, username, source, note FROM leads ORDER BY id"
        )

    def export_bookings_csv(self) -> str:
        return self._csv(
            "SELECT id, created_at, date, time, service, name, phone FROM bookings "
            "ORDER BY date, time"
        )

    def _csv(self, query: str) -> str:
        cur = self.conn.execute(query)
        buf = io.StringIO()
        writer = csv.writer(buf, lineterminator="\n")
        writer.writerow([d[0] for d in cur.description])
        for row in cur.fetchall():
            writer.writerow([_safe_cell(v) for v in tuple(row)])
        return buf.getvalue()


def _safe_cell(value: object) -> object:
    """Neutralise spreadsheet formula injection in user-supplied text."""
    if isinstance(value, str) and value[:1] in ("=", "+", "-", "@"):
        return "'" + value
    return value
