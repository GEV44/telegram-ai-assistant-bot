"""Knowledge base with a tiny dependency-free BM25 retriever."""

from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from .lang import detect_language

_WORD = re.compile(r"\w+", re.UNICODE)
_STOP = frozenset(
    [
        "a",
        "an",
        "the",
        "is",
        "are",
        "do",
        "does",
        "i",
        "you",
        "we",
        "of",
        "to",
        "for",
        "in",
        "on",
        "at",
        "and",
        "or",
        "my",
        "me",
        "it",
        "your",
        "и",
        "в",
        "во",
        "не",
        "на",
        "я",
        "с",
        "со",
        "как",
        "что",
        "это",
        "у",
        "по",
        "а",
        "но",
        "или",
        "мне",
        "вы",
        "ли",
        "же",
        "бы",
        "для",
        "от",
        "до",
        "եմ",
        "է",
        "և",
        "ու",
        "որ",
        "ի",
        "մի",
        "թե",
    ]
)
_STEM_LEN = 6


def tokenize(text: str) -> list[str]:
    """Lowercase, split on word characters, drop stop words, crude-stem by prefix.

    Prefix truncation is language-agnostic, which is good enough to match
    "appointments"/"appointment" and Russian/Armenian inflections without models.
    """
    out: list[str] = []
    for word in _WORD.findall(text.lower()):
        if word in _STOP or (word.isdigit() and len(word) < 2):
            continue
        out.append(word[:_STEM_LEN])
    return out


@dataclass(frozen=True)
class Entry:
    question: str
    answer: str
    lang: str


@dataclass(frozen=True)
class Hit:
    entry: Entry
    score: float


class BM25:
    """Okapi BM25 over pre-tokenised documents."""

    def __init__(self, docs: list[list[str]], k1: float = 1.5, b: float = 0.75) -> None:
        self.docs = docs
        self.k1 = k1
        self.b = b
        self.n = len(docs)
        self.avgdl = (sum(len(d) for d in docs) / self.n) if self.n else 0.0
        self.tf = [Counter(d) for d in docs]
        df: Counter[str] = Counter()
        for d in docs:
            df.update(set(d))
        self.idf = {t: math.log(1 + (self.n - c + 0.5) / (c + 0.5)) for t, c in df.items()}

    def scores(self, query: list[str]) -> list[float]:
        result = [0.0] * self.n
        for i, tf in enumerate(self.tf):
            dl = len(self.docs[i])
            norm = self.k1 * (1 - self.b + self.b * dl / self.avgdl) if self.avgdl else self.k1
            for term in set(query):
                f = tf.get(term, 0)
                if f:
                    result[i] += self.idf[term] * f * (self.k1 + 1) / (f + norm)
        return result


class KnowledgeBase:
    def __init__(self, entries: list[Entry]) -> None:
        self.entries = entries
        # The question is repeated so it outweighs the answer body.
        self._docs = [tokenize(f"{e.question} {e.question} {e.answer}") for e in entries]
        self._bm25 = BM25(self._docs)

    def search(
        self, query: str, lang: str | None = None, top_k: int = 3, min_score: float = 0.3
    ) -> list[Hit]:
        """Return the best matches, preferring entries written in ``lang``."""
        q = tokenize(query)
        if not q or not self.entries:
            return []
        raw = self._bm25.scores(q)
        pool = [i for i, e in enumerate(self.entries) if lang is None or e.lang == lang]
        if not pool or all(raw[i] < min_score for i in pool):
            pool = list(range(len(self.entries)))
        ranked = sorted(pool, key=lambda i: raw[i], reverse=True)
        return [Hit(self.entries[i], raw[i]) for i in ranked[:top_k] if raw[i] >= min_score]

    # ---- loading -------------------------------------------------------
    @classmethod
    def from_entries(cls, items: list[dict[str, Any]]) -> KnowledgeBase:
        entries = []
        for item in items:
            q, a = str(item["q"]).strip(), str(item["a"]).strip()
            entries.append(Entry(q, a, str(item.get("lang") or detect_language(q))))
        return cls(entries)

    @classmethod
    def from_markdown(cls, text: str) -> KnowledgeBase:
        """Parse ``## Question`` headings followed by answer paragraphs."""
        items: list[dict[str, Any]] = []
        question: str | None = None
        body: list[str] = []
        for line in text.splitlines():
            if line.startswith("## "):
                if question and "".join(body).strip():
                    items.append({"q": question, "a": "\n".join(body).strip()})
                question, body = line[3:].strip(), []
            elif question is not None:
                body.append(line)
        if question and "".join(body).strip():
            items.append({"q": question, "a": "\n".join(body).strip()})
        return cls.from_entries(items)

    @classmethod
    def from_file(cls, path: str | Path) -> KnowledgeBase:
        p = Path(path)
        text = p.read_text(encoding="utf-8")
        if p.suffix.lower() in {".md", ".markdown"}:
            return cls.from_markdown(text)
        data = yaml.safe_load(text)
        items = data["faq"] if isinstance(data, dict) else data
        return cls.from_entries(items)
