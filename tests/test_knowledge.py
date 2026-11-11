from pathlib import Path

from tg_assistant.knowledge import BM25, KnowledgeBase, tokenize


def test_tokenize_drops_stopwords_and_stems() -> None:
    assert tokenize("The appointments are great") == ["appoin", "great"]


def test_bm25_ranks_matching_doc_first() -> None:
    docs = [tokenize("cats and dogs"), tokenize("opening hours monday"), tokenize("parking")]
    scores = BM25(docs).scores(tokenize("opening hours"))
    assert scores.index(max(scores)) == 1


def test_bm25_unknown_terms_score_zero() -> None:
    assert BM25([tokenize("hello world")]).scores(["zzzz"]) == [0.0]


def test_retrieval_english(kb: KnowledgeBase) -> None:
    hits = kb.search("when are you open?", lang="en")
    assert hits and "09:00" in hits[0].entry.answer


def test_retrieval_russian(kb: KnowledgeBase) -> None:
    hits = kb.search("вы лечите детей?", lang="ru")
    assert hits and "Детский" in hits[0].entry.answer


def test_retrieval_armenian(kb: KnowledgeBase) -> None:
    hits = kb.search("Երեխաներին բուժում եք", lang="hy")
    assert hits and hits[0].entry.lang == "hy"


def test_inflected_query_matches(kb: KnowledgeBase) -> None:
    hits = kb.search("whitening safe?", lang="en")
    assert hits and "whitening" in hits[0].entry.question.lower()


def test_gibberish_returns_nothing(kb: KnowledgeBase) -> None:
    assert kb.search("qwertyuiop zxcvbnm") == []


def test_empty_query(kb: KnowledgeBase) -> None:
    assert kb.search("   ") == []


def test_language_fallback_when_no_entries_in_lang() -> None:
    kb = KnowledgeBase.from_entries([{"q": "Where is parking?", "a": "In the yard.", "lang": "en"}])
    assert kb.search("parking", lang="ru")[0].entry.answer == "In the yard."


def test_markdown_loader() -> None:
    md = "# Title\n\n## Do you deliver?\nYes, within the city.\n\n## Opening hours\n9 to 6.\n"
    kb = KnowledgeBase.from_markdown(md)
    assert len(kb.entries) == 2
    assert kb.search("deliver")[0].entry.answer == "Yes, within the city."


def test_from_file_markdown(tmp_path: Path) -> None:
    f = tmp_path / "kb.md"
    f.write_text("## Warranty\nTwo years.\n", encoding="utf-8")
    assert KnowledgeBase.from_file(f).search("warranty")[0].entry.answer == "Two years."
