from __future__ import annotations

from collections.abc import Iterator
from datetime import datetime
from pathlib import Path

import pytest

from tg_assistant.assistant import Assistant
from tg_assistant.booking import BookingEngine
from tg_assistant.config import BusinessConfig, load_business
from tg_assistant.db import Database
from tg_assistant.knowledge import KnowledgeBase
from tg_assistant.ratelimit import RateLimiter

ROOT = Path(__file__).resolve().parents[1]
# Wednesday 2026-11-11, 08:00 - all of today's slots are still in the future.
NOW = datetime(2026, 11, 11, 8, 0)


@pytest.fixture
def config() -> BusinessConfig:
    return load_business(ROOT / "config" / "smile_studio.yaml")


@pytest.fixture
def kb() -> KnowledgeBase:
    return KnowledgeBase.from_file(ROOT / "config" / "smile_studio_faq.yaml")


@pytest.fixture
def db() -> Iterator[Database]:
    database = Database(":memory:")
    yield database
    database.close()


@pytest.fixture
def engine(config: BusinessConfig, db: Database) -> BookingEngine:
    return BookingEngine(config, db, now=lambda: NOW)


@pytest.fixture
def assistant(config: BusinessConfig, kb: KnowledgeBase, db: Database) -> Assistant:
    return Assistant(
        config, kb, db, limiter=RateLimiter(50, 60, clock=lambda: 0.0), now=lambda: NOW
    )
