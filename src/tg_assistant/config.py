"""Business configuration (YAML) and runtime settings (environment)."""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import time
from pathlib import Path
from typing import Any

import yaml

DEFAULT_REMINDER_OFFSETS = (1440, 120)  # 24 h and 2 h before the visit


@dataclass(frozen=True)
class Service:
    id: str
    names: Mapping[str, str]

    def name(self, lang: str) -> str:
        return self.names.get(lang) or self.names.get("en") or self.id


@dataclass(frozen=True)
class Schedule:
    open: time = time(9, 0)
    close: time = time(18, 0)
    slot_minutes: int = 60
    open_weekdays: tuple[int, ...] = (0, 1, 2, 3, 4)  # Monday=0
    horizon_days: int = 14
    breaks: tuple[tuple[time, time], ...] = ()


@dataclass(frozen=True)
class BusinessConfig:
    name: str
    services: tuple[Service, ...]
    schedule: Schedule = field(default_factory=Schedule)
    default_lang: str = "en"
    reminder_offsets_minutes: tuple[int, ...] = DEFAULT_REMINDER_OFFSETS
    digest_time: time | None = None  # owner digest; None = off


def _t(value: str) -> time:
    hh, mm = str(value).split(":")
    return time(int(hh), int(mm))


def load_business(path: str | Path) -> BusinessConfig:
    data: dict[str, Any] = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    sched = data.get("schedule", {})
    schedule = Schedule(
        open=_t(sched.get("open", "09:00")),
        close=_t(sched.get("close", "18:00")),
        slot_minutes=int(sched.get("slot_minutes", 60)),
        open_weekdays=tuple(sched.get("open_weekdays", [0, 1, 2, 3, 4])),
        horizon_days=int(sched.get("horizon_days", 14)),
        breaks=tuple((_t(a), _t(b)) for a, b in sched.get("breaks", [])),
    )
    services = tuple(Service(s["id"], dict(s["names"])) for s in data["services"])
    biz = data["business"]
    reminders = data.get("reminders") or {}
    hours = reminders.get("offsets_hours")
    offsets = (
        tuple(sorted({round(float(h) * 60) for h in hours if float(h) > 0}, reverse=True))
        if hours is not None
        else DEFAULT_REMINDER_OFFSETS
    )
    digest = (data.get("digest") or {}).get("time")
    return BusinessConfig(
        name=biz["name"],
        services=services,
        schedule=schedule,
        default_lang=biz.get("default_lang", "en"),
        reminder_offsets_minutes=offsets,
        digest_time=_t(digest) if digest else None,
    )


@dataclass(frozen=True)
class Settings:
    bot_token: str
    admin_chat_id: int | None
    db_path: str
    business_path: str
    knowledge_path: str
    rate_limit: int
    rate_window_s: int
    llm_enabled: bool
    llm_base_url: str
    llm_api_key: str
    llm_model: str

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> Settings:
        e = os.environ if env is None else env
        admin = e.get("ADMIN_CHAT_ID", "").strip()
        return cls(
            bot_token=e.get("BOT_TOKEN", ""),
            admin_chat_id=int(admin) if admin else None,
            db_path=e.get("DB_PATH", "data/assistant.db"),
            business_path=e.get("BUSINESS_CONFIG", "config/smile_studio.yaml"),
            knowledge_path=e.get("KNOWLEDGE_FILE", "config/smile_studio_faq.yaml"),
            rate_limit=int(e.get("RATE_LIMIT_MESSAGES", "12")),
            rate_window_s=int(e.get("RATE_LIMIT_WINDOW_S", "60")),
            llm_enabled=e.get("LLM_ENABLED", "false").strip().lower() in {"1", "true", "yes"},
            llm_base_url=e.get("LLM_BASE_URL", "https://api.openai.com/v1"),
            llm_api_key=e.get("LLM_API_KEY", ""),
            llm_model=e.get("LLM_MODEL", "gpt-4o-mini"),
        )
