"""Text normalization and error metrics for Chinese/English ASR experiments."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass


_LATIN_WORD = re.compile(r"[a-z0-9]+(?:'[a-z0-9]+)*", re.IGNORECASE)


@dataclass(frozen=True)
class ErrorScore:
    edits: int
    reference_units: int

    @property
    def rate(self) -> float:
        return self.edits / self.reference_units if self.reference_units else 0.0


def _is_cjk(ch: str) -> bool:
    code = ord(ch)
    return (
        0x3400 <= code <= 0x4DBF
        or 0x4E00 <= code <= 0x9FFF
        or 0xF900 <= code <= 0xFAFF
    )


def normalize_text(text: str) -> str:
    """Normalize width/case and turn punctuation into token boundaries."""
    normalized = unicodedata.normalize("NFKC", text).lower().replace("’", "'")
    out: list[str] = []
    for ch in normalized:
        category = unicodedata.category(ch)
        if ch.isspace() or (category[0] in {"P", "S"} and ch != "'"):
            out.append(" ")
        else:
            out.append(ch)
    return " ".join("".join(out).split())


def chinese_characters(text: str) -> list[str]:
    """CER units: all normalized non-space characters."""
    return [ch for ch in normalize_text(text) if not ch.isspace()]


def english_words(text: str) -> list[str]:
    """WER units, including non-Latin alphanumerics as insertion candidates."""
    normalized = normalize_text(text)
    units: list[str] = []
    cursor = 0
    for match in _LATIN_WORD.finditer(normalized):
        units.extend(ch for ch in normalized[cursor : match.start()] if ch.isalnum())
        units.append(match.group())
        cursor = match.end()
    units.extend(ch for ch in normalized[cursor:] if ch.isalnum())
    return units


def mixed_tokens(text: str) -> list[str]:
    """MER units: one token per CJK character and one per Latin word."""
    normalized = normalize_text(text)
    tokens: list[str] = []
    latin: list[str] = []

    def flush_latin() -> None:
        if latin:
            tokens.extend(_LATIN_WORD.findall("".join(latin)))
            latin.clear()

    for ch in normalized:
        if _is_cjk(ch):
            flush_latin()
            tokens.append(ch)
        elif ch.isascii() and (ch.isalnum() or ch == "'"):
            latin.append(ch)
        else:
            flush_latin()
    flush_latin()
    return tokens


def edit_distance(reference: list[str], hypothesis: list[str]) -> int:
    """Memory-efficient Levenshtein distance."""
    if len(reference) < len(hypothesis):
        reference, hypothesis = hypothesis, reference
    previous = list(range(len(hypothesis) + 1))
    for row, ref_unit in enumerate(reference, start=1):
        current = [row]
        for col, hyp_unit in enumerate(hypothesis, start=1):
            current.append(
                min(
                    current[-1] + 1,
                    previous[col] + 1,
                    previous[col - 1] + (ref_unit != hyp_unit),
                )
            )
        previous = current
    return previous[-1]


def score(reference: str, hypothesis: str, category: str) -> ErrorScore:
    tokenizers = {
        "zh": chinese_characters,
        "en": english_words,
        "mixed": mixed_tokens,
    }
    try:
        tokenize = tokenizers[category]
    except KeyError as exc:
        raise ValueError(f"Unsupported category: {category}") from exc
    ref_units = tokenize(reference)
    hyp_units = tokenize(hypothesis)
    return ErrorScore(edit_distance(ref_units, hyp_units), len(ref_units))
