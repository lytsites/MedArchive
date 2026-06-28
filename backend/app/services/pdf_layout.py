from __future__ import annotations

from dataclasses import dataclass
import re
from statistics import median
from typing import Iterable, Sequence


SECTION_HINTS = ("раздел", "блок", "подраздел", "глава", "часть")
PRICE_HINTS = ("стоим", "цена", "price", "cost", "тенге", "kzt", "тг")
CODE_RE = re.compile(r"^[A-ZА-ЯЁ0-9][A-ZА-ЯЁ0-9.\-/]*$", flags=re.IGNORECASE)
MONEY_RE = re.compile(r"^\d{1,3}(?:[ \u00A0]\d{3})*(?:[.,]\d+)?$")
MONEY_RE_PLAIN = re.compile(r"^\d+(?:[.,]\d+)?$")


@dataclass(frozen=True)
class LayoutWord:
    text: str
    x0: float
    y0: float
    x1: float
    y1: float

    @property
    def cx(self) -> float:
        return (self.x0 + self.x1) / 2

    @property
    def cy(self) -> float:
        return (self.y0 + self.y1) / 2


def coerce_layout_word(word: object) -> LayoutWord:
    if isinstance(word, LayoutWord):
        return word
    if isinstance(word, dict):
        text = str(word.get("text", "") or "")
        x0 = float(word.get("x0", 0) or 0)
        x1 = float(word.get("x1", x0) or x0)
        y0 = float(word.get("top", word.get("y0", 0)) or 0)
        y1 = float(word.get("bottom", word.get("y1", y0)) or y0)
        return LayoutWord(text=text, x0=x0, y0=y0, x1=x1, y1=y1)

    text = str(getattr(word, "text", "") or "")
    x0 = float(getattr(word, "x0", 0) or 0)
    x1 = float(getattr(word, "x1", x0) or x0)
    y0 = float(getattr(word, "y0", getattr(word, "top", 0)) or 0)
    y1 = float(getattr(word, "y1", getattr(word, "bottom", y0)) or y0)
    return LayoutWord(text=text, x0=x0, y0=y0, x1=x1, y1=y1)


def _clean_text(value: object | None) -> str:
    if value is None:
        return ""
    return re.sub(r"\s+", " ", str(value)).strip()


def _median_or_default(values: Sequence[float], default: float) -> float:
    filtered = [value for value in values if value > 0]
    if not filtered:
        return default
    return float(median(filtered))


def is_section_row(text: str) -> bool:
    lowered = _clean_text(text).lower()
    if not lowered:
        return False
    if any(hint in lowered for hint in SECTION_HINTS):
        return True
    return bool(re.match(r"^\d+(?:\.\d+)*[.)]?\s+", lowered))


def is_code_like(text: str) -> bool:
    cleaned = _clean_text(text).replace(" ", "")
    if not cleaned or len(cleaned) > 24:
        return False
    if not any(char.isdigit() for char in cleaned):
        return False
    if re.search(r"[а-яё]", cleaned, flags=re.IGNORECASE):
        return False
    return bool(CODE_RE.match(cleaned))


def is_price_like(text: str) -> bool:
    cleaned = _clean_text(text).lower()
    if not cleaned:
        return False
    cleaned = cleaned.replace("тенге", "").replace("kzt", "").replace("тг", "")
    cleaned = cleaned.replace("\xa0", " ").strip()
    if re.search(r"[a-zа-я]", cleaned, flags=re.IGNORECASE):
        return False
    cleaned = cleaned.replace(" ", "")
    if not cleaned:
        return False
    if MONEY_RE.match(cleaned):
        return True
    if MONEY_RE_PLAIN.match(cleaned):
        return True
    return False


def group_words_into_rows(words: Iterable[object], y_tolerance: float = 4.0) -> list[list[LayoutWord]]:
    normalized = sorted((coerce_layout_word(word) for word in words), key=lambda item: (item.y0, item.x0))
    rows: list[list[LayoutWord]] = []
    row_anchor: float | None = None
    for word in normalized:
        if not word.text.strip():
            continue
        if not rows:
            rows.append([word])
            row_anchor = word.y0
            continue
        assert row_anchor is not None
        if abs(word.y0 - row_anchor) <= y_tolerance:
            rows[-1].append(word)
            row_anchor = (row_anchor * (len(rows[-1]) - 1) + word.y0) / len(rows[-1])
        else:
            rows.append([word])
            row_anchor = word.y0
    return rows


def split_row_into_segments(words: Sequence[LayoutWord], gap_threshold: float | None = None) -> list[list[LayoutWord]]:
    ordered = sorted(words, key=lambda item: (item.x0, item.y0))
    if not ordered:
        return []
    if len(ordered) == 1:
        return [list(ordered)]

    widths = [max(item.x1 - item.x0, 1.0) for item in ordered]
    gaps = [max(ordered[index + 1].x0 - ordered[index].x1, 0.0) for index in range(len(ordered) - 1)]
    median_width = _median_or_default(widths, 8.0)
    median_gap = _median_or_default(gaps, 10.0)
    threshold = gap_threshold if gap_threshold is not None else max(16.0, median_width * 1.8, median_gap * 2.2)

    segments: list[list[LayoutWord]] = [[ordered[0]]]
    for word in ordered[1:]:
        previous = segments[-1][-1]
        gap = word.x0 - previous.x1
        if gap > threshold:
            segments.append([word])
        else:
            segments[-1].append(word)
    return segments


def _segment_text(segment: Sequence[LayoutWord]) -> str:
    return _clean_text(" ".join(word.text for word in segment))


def _join_row_text(row: Sequence[str]) -> str:
    return _clean_text(" ".join(cell for cell in row if cell))


def _merge_continuation_row(
    previous_row: list[str],
    current_row: list[str],
    current_text: str,
) -> bool:
    if not previous_row or not current_row:
        return False
    if is_section_row(current_text):
        return False
    has_code = any(is_code_like(cell) for cell in current_row)
    has_price = any(is_price_like(cell) for cell in current_row)
    if has_code or has_price:
        return False
    if len(current_text) > 120:
        return False

    previous_target = None
    for index in range(len(previous_row) - 1, -1, -1):
        if not is_price_like(previous_row[index]):
            previous_target = index
            break
    if previous_target is None:
        return False

    merged_text = _clean_text(previous_row[previous_target] + " " + current_text)
    previous_row[previous_target] = merged_text
    return True


def rows_from_words(words: Iterable[object], page_width: float | None = None) -> list[list[str]]:
    row_groups = group_words_into_rows(words)
    rows: list[list[str]] = []

    for row_index, group in enumerate(row_groups):
        if not group:
            continue
        segments = split_row_into_segments(group)
        row = [_segment_text(segment) for segment in segments if _segment_text(segment)]
        row_text = _join_row_text(row)
        if not row_text:
            continue

        if row_index < 3 and len(row) > 1:
            rows.append(row)
            continue

        if rows and _merge_continuation_row(rows[-1], row, row_text):
            continue

        rows.append(row)

    return rows
