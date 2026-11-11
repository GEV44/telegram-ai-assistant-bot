from datetime import time

from tg_assistant.config import BusinessConfig, Settings


def test_business_config_loads(config: BusinessConfig) -> None:
    assert config.name == "Smile Studio"
    assert len(config.services) == 4
    assert config.schedule.open == time(9, 0)
    assert config.services[0].name("hy") != config.services[0].name("en")


def test_settings_defaults_have_llm_off() -> None:
    s = Settings.from_env({})
    assert s.llm_enabled is False and s.admin_chat_id is None


def test_settings_from_env() -> None:
    s = Settings.from_env({"ADMIN_CHAT_ID": "-100123", "LLM_ENABLED": "true", "BOT_TOKEN": "x"})
    assert s.admin_chat_id == -100123 and s.llm_enabled and s.bot_token == "x"
