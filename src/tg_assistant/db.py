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
    confirmed: bool = False
    lang: str = "en"

    @property
    def start(self) -> datetime:
        """Local (naive) start of the visit."""
        return datetime.strptime(f"{self.date} {self.time}", "%Y-%m-%d %H:%M")


@dataclass(frozen=True)
class Lead:
    id: int
    user_id: int
    username: str
    name: str
    phone: str
    source: str
    note: str
    created_at: str
    resolved: bool = False


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
    confirmed INTEGER NOT NULL DEFAULT 0,
    lang TEXT NOT NULL DEFAULT 'en',
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
    created_at TEXT NOT NULL,
    resolved INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS reminders (
    booking_id INTEGER NOT NULL,
    offset_minutes INTEGER NOT NULL,
    sent_at TEXT NOT NULL,
    PRIMARY KEY (booking_id, offset_minutes)
);
CREATE TABLE IF NOT EXISTS meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""

# Columns added after 1.0.0; applied to databases created by older versions.
_MIGRATIONS = (
    ("bookings", "confirmed", "INTEGER NOT NULL DEFAULT 0"),
    ("bookings", "lang", "TEXT NOT NULL DEFAULT 'en'"),
    ("leads", "resolved", "INTEGER NOT NULL DEFAULT 0"),
)


def _booking(r: sqlite3.Row) -> Booking:
    return Booking(
        r["id"],
        r["user_id"],
        r["service"],
        r["date"],
        r["time"],
        r["name"],
        r["phone"],
        bool(r["confirmed"]),
        r["lang"],
    )


def _lead(r: sqlite3.Row) -> Lead:
    return Lead(
        r["id"],
        r["user_id"],
        r["username"],
        r["name"],
        r["phone"],
        r["source"],
        r["note"],
        r["created_at"],
        bool(r["resolved"]),
    )


def _now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S")


class Database:
    """Thin synchronous wrapper; queries are tiny so they are fine inside handlers."""

    def __init__(self, path: str = ":memory:") -> None:
        self.conn = sqlite3.connect(path)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(_SCHEMA)
        self._migrate()

    def _migrate(self) -> None:
        for table, column, ddl in _MIGRATIONS:
            cols = {r["name"] for r in self.conn.execute(f"PRAGMA table_info({table})")}
            if column not in cols:
                with self.conn:
                    self.conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {ddl}")

    def close(self) -> None:
        self.conn.close()

    # ---- bookings ------------------------------------------------------
    def booked_times(self, date: str) -> set[str]:
        rows = self.conn.execute("SELECT time FROM bookings WHERE date = ?", (date,)).fetchall()
        return {r["time"] for r in rows}

    def add_booking(
        self,
        user_id: int,
        service: str,
        date: str,
        time: str,
        name: str,
        phone: str,
        lang: str = "en",
    ) -> Booking:
        """Insert atomically; the UNIQUE(date, time) index makes double-booking impossible."""
        try:
            with self.conn:
                cur = self.conn.execute(
                    "INSERT INTO bookings "
                    "(user_id, service, date, time, name, phone, created_at, lang) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (user_id, service, date, time, name, phone, _now(), lang),
                )
        except sqlite3.IntegrityError as exc:
            raise SlotTakenError(f"{date} {time} is already booked") from exc
        return Booking(
            int(cur.lastrowid or 0), user_id, service, date, time, name, phone, False, lang
        )

    def list_bookings(self) -> list[Booking]:
        rows = self.conn.execute("SELECT * FROM bookings ORDER BY date, time").fetchall()
        return [_booking(r) for r in rows]

    def get_booking(self, booking_id: int) -> Booking | None:
        row = self.conn.execute("SELECT * FROM bookings WHERE id = ?", (booking_id,)).fetchone()
        return _booking(row) if row else None

    def bookings_from(self, date: str, user_id: int | None = None) -> list[Booking]:
        """Bookings on or after ``date`` (ISO), optionally of one customer."""
        query = "SELECT * FROM bookings WHERE date >= ?"
        args: tuple[object, ...] = (date,)
        if user_id is not None:
            query, args = query + " AND user_id = ?", (date, user_id)
        rows = self.conn.execute(query + " ORDER BY date, time", args).fetchall()
        return [_booking(r) for r in rows]

    def bookings_on(self, date: str) -> list[Booking]:
        rows = self.conn.execute(
            "SELECT * FROM bookings WHERE date = ? ORDER BY time", (date,)
        ).fetchall()
        return [_booking(r) for r in rows]

    def cancel_booking(self, booking_id: int) -> bool:
        """Delete a booking (its slot becomes free again) together with its reminder state."""
        with self.conn:
            self.conn.execute("DELETE FROM reminders WHERE booking_id = ?", (booking_id,))
            cur = self.conn.execute("DELETE FROM bookings WHERE id = ?", (booking_id,))
        return cur.rowcount > 0

    def move_booking(self, booking_id: int, date: str, time: str) -> Booking | None:
        """Move to a new slot in one statement: the old slot is freed only if the new one is won."""
        try:
            with self.conn:
                cur = self.conn.execute(
                    "UPDATE bookings SET date = ?, time = ?, confirmed = 0 WHERE id = ?",
                    (date, time, booking_id),
                )
                if cur.rowcount:
                    self.conn.execute("DELETE FROM reminders WHERE booking_id = ?", (booking_id,))
        except sqlite3.IntegrityError as exc:
            raise SlotTakenError(f"{date} {time} is already booked") from exc
        return self.get_booking(booking_id)

    def confirm_booking(self, booking_id: int) -> bool:
        with self.conn:
            cur = self.conn.execute("UPDATE bookings SET confirmed = 1 WHERE id = ?", (booking_id,))
        return cur.rowcount > 0

    # ---- reminders / meta ----------------------------------------------
    def sent_reminders(self) -> set[tuple[int, int]]:
        rows = self.conn.execute("SELECT booking_id, offset_minutes FROM reminders").fetchall()
        return {(r["booking_id"], r["offset_minutes"]) for r in rows}

    def mark_reminder(self, booking_id: int, offset_minutes: int) -> None:
        with self.conn:
            self.conn.execute(
                "INSERT OR IGNORE INTO reminders (booking_id, offset_minutes, sent_at) "
                "VALUES (?, ?, ?)",
                (booking_id, offset_minutes, _now()),
            )

    def get_meta(self, key: str) -> str | None:
        row = self.conn.execute("SELECT value FROM meta WHERE key = ?", (key,)).fetchone()
        return str(row["value"]) if row else None

    def set_meta(self, key: str, value: str) -> None:
        with self.conn:
            self.conn.execute(
                "INSERT INTO meta (key, value) VALUES (?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                (key, value),
            )

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

    def leads_since(self, last_id: int, sources: tuple[str, ...] = ("lead",)) -> list[Lead]:
        marks = ",".join("?" * len(sources))
        rows = self.conn.execute(
            f"SELECT * FROM leads WHERE id > ? AND source IN ({marks}) ORDER BY id",
            (last_id, *sources),
        ).fetchall()
        return [_lead(r) for r in rows]

    def max_lead_id(self) -> int:
        return int(self.conn.execute("SELECT COALESCE(MAX(id), 0) FROM leads").fetchone()[0])

    def open_handoffs(self) -> list[Lead]:
        rows = self.conn.execute(
            "SELECT * FROM leads WHERE source = 'handoff' AND resolved = 0 ORDER BY id"
        ).fetchall()
        return [_lead(r) for r in rows]

    def resolve_handoffs(self, user_id: int) -> int:
        with self.conn:
            cur = self.conn.execute(
                "UPDATE leads SET resolved = 1 WHERE source = 'handoff' AND user_id = ?",
                (user_id,),
            )
        return cur.rowcount

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
