from __future__ import annotations

import re
import unicodedata


SMALL_KANA_MAP = str.maketrans(
    {
        "ぁ": "あ",
        "ぃ": "い",
        "ぅ": "う",
        "ぇ": "え",
        "ぉ": "お",
        "ゃ": "や",
        "ゅ": "ゆ",
        "ょ": "よ",
        "っ": "つ",
        "ゎ": "わ",
    }
)

KANA_PATTERN = re.compile(r"[ぁ-ゖー]+")


def katakana_to_hiragana(text: str) -> str:
    converted: list[str] = []
    for char in text:
        code = ord(char)
        if 0x30A1 <= code <= 0x30F6:
            converted.append(chr(code - 0x60))
        else:
            converted.append(char)
    return "".join(converted)


def normalize_shiritori_word(text: str) -> str:
    normalized = unicodedata.normalize("NFKC", text.strip())
    normalized = katakana_to_hiragana(normalized)
    pieces = KANA_PATTERN.findall(normalized)
    joined = "".join(pieces).translate(SMALL_KANA_MAP)
    return joined.rstrip("ー")


def first_kana(word: str) -> str | None:
    normalized = normalize_shiritori_word(word)
    return normalized[0] if normalized else None


def last_kana(word: str) -> str | None:
    normalized = normalize_shiritori_word(word)
    return normalized[-1] if normalized else None
