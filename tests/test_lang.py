import pytest

from tg_assistant.lang import detect_language


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("What are your opening hours?", "en"),
        ("Какие у вас часы работы?", "ru"),
        ("Ինչ աշխատանքային ժամեր ունեք", "hy"),
        ("Hello, привет, как дела", "ru"),
    ],
)
def test_detects_by_script(text: str, expected: str) -> None:
    assert detect_language(text) == expected


def test_no_letters_keeps_default() -> None:
    assert detect_language("+374 77 123456", default="ru") == "ru"
    assert detect_language("", default="hy") == "hy"


def test_mixed_text_uses_majority() -> None:
    assert detect_language("book запись запись запись") == "ru"
