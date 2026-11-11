"""Optional answer polishing through any OpenAI-compatible chat endpoint."""

from __future__ import annotations

import logging
from typing import Protocol

import aiohttp

from .knowledge import Hit

log = logging.getLogger(__name__)

LANG_NAMES = {"en": "English", "ru": "Russian", "hy": "Armenian"}


class LLM(Protocol):
    async def complete(self, system: str, user: str) -> str | None: ...


def build_prompt(business: str, question: str, hits: list[Hit], lang: str) -> tuple[str, str]:
    """Build a grounded prompt: the model may only use the retrieved facts."""
    context = "\n\n".join(f"Q: {h.entry.question}\nA: {h.entry.answer}" for h in hits)
    system = (
        f"You are the customer assistant of {business}. Answer ONLY from the facts below. "
        "If they do not contain the answer, say you are not sure and suggest /human. "
        f"Reply in {LANG_NAMES.get(lang, 'English')}, in at most 3 short sentences. "
        "Never invent prices, times or policies.\n\nFacts:\n" + context
    )
    return system, question


class OpenAICompatibleClient:
    """Minimal chat-completions client. Works with OpenAI, OpenRouter, Ollama, vLLM, ..."""

    def __init__(self, base_url: str, api_key: str, model: str, timeout_s: float = 20.0) -> None:
        self.url = base_url.rstrip("/") + "/chat/completions"
        self.api_key = api_key
        self.model = model
        self.timeout = aiohttp.ClientTimeout(total=timeout_s)

    async def complete(self, system: str, user: str) -> str | None:
        payload = {
            "model": self.model,
            "temperature": 0.2,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        }
        headers = {"Authorization": f"Bearer {self.api_key}"} if self.api_key else {}
        try:
            async with (
                aiohttp.ClientSession(timeout=self.timeout) as session,
                session.post(self.url, json=payload, headers=headers) as resp,
            ):
                resp.raise_for_status()
                data = await resp.json()
            text = data["choices"][0]["message"]["content"]
            return str(text).strip() or None
        except (aiohttp.ClientError, TimeoutError, KeyError, IndexError, ValueError):
            log.warning("LLM call failed; falling back to the knowledge-base answer")
            return None
