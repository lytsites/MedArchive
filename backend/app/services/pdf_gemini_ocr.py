from __future__ import annotations

import json
import re
import time
from functools import lru_cache
from io import BytesIO
from typing import Any, Sequence

import cv2
import numpy as np
from PIL import Image, ImageEnhance, ImageFilter, ImageOps

from app.core.config import settings

try:
    from google import genai  # type: ignore
    from google.genai import types  # type: ignore
except Exception:  # pragma: no cover
    genai = None
    types = None


_OCR_PROMPT = """
You are extracting rows from scanned medical price-list PDF pages.

Return ONLY strict JSON with this exact shape:
{
  "pages": [
    {
      "page": 1,
      "rows": [
        ["code", "service", "resident_price", "nonresident_price", "original_price", "section"]
      ]
    }
  ]
}

Rules:
- Preserve page numbers exactly.
- Keep rows in top-to-bottom order.
- Do not invent values.
- Keep values in the original language.
- Read the page like OCR, but also use visible table lines, column borders, and section separators to preserve structure.
- Prefer table structure over raw line order when both are visible.
- Split merged text into the correct columns when the page layout makes the columns obvious.
- Keep section headers as separate rows.
- Use empty strings or null for missing cells.
- Prices must contain only digits and separators; no currency words.
- If a row is a section/header row, put the text into the section cell and leave the others empty.
- If the page is unreadable, return an empty rows list for that page.
- Do not wrap the JSON in markdown fences.
"""


def _extract_json_payload(text: str) -> dict[str, Any]:
    candidate = (text or "").strip()
    if not candidate:
        return {}
    if candidate.startswith("```"):
        candidate = re.sub(r"^```(?:json)?\s*", "", candidate, flags=re.IGNORECASE)
        candidate = re.sub(r"\s*```$", "", candidate)
    start = candidate.find("{")
    end = candidate.rfind("}")
    if start >= 0 and end > start:
        candidate = candidate[start : end + 1]
    payload = json.loads(candidate)
    return payload if isinstance(payload, dict) else {}


def _warn(stats: Any, message: str) -> None:
    warnings = getattr(stats, "warnings", None)
    if isinstance(warnings, list):
        warnings.append(message)


@lru_cache(maxsize=1)
def _client() -> object:
    if genai is None or types is None:
        raise RuntimeError("google-genai is not installed")
    if not settings.gemini_api_key.strip():
        raise RuntimeError("Gemini API key is not configured")
    return genai.Client(api_key=settings.gemini_api_key.strip())


def _prepare_image(image: Image.Image) -> Image.Image:
    prepared = image.convert("RGB")
    array = np.array(prepared)
    gray = cv2.cvtColor(array, cv2.COLOR_RGB2GRAY)
    gray = cv2.GaussianBlur(gray, (3, 3), 0)
    _, thresh = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    coords = np.column_stack(np.where(thresh > 0))
    if coords.size:
        rect = cv2.minAreaRect(coords)
        angle = rect[-1]
        if angle < -45:
            angle = -(90 + angle)
        else:
            angle = -angle
        if abs(angle) >= 0.25:
            (h, w) = array.shape[:2]
            matrix = cv2.getRotationMatrix2D((w // 2, h // 2), angle, 1.0)
            array = cv2.warpAffine(
                array,
                matrix,
                (w, h),
                flags=cv2.INTER_CUBIC,
                borderMode=cv2.BORDER_REPLICATE,
            )
            prepared = Image.fromarray(array)
    prepared = ImageOps.autocontrast(prepared)
    prepared = ImageEnhance.Sharpness(prepared).enhance(1.35)
    prepared = ImageEnhance.Contrast(prepared).enhance(1.15)
    prepared = prepared.filter(ImageFilter.SHARPEN)
    min_width = 2200
    if prepared.width and prepared.width < min_width:
        new_height = max(1, int(prepared.height * (min_width / prepared.width)))
        prepared = prepared.resize((min_width, new_height), Image.Resampling.LANCZOS)
    return prepared


def _normalize_cell(value: object | None) -> str:
    if value is None:
        return ""
    text = str(value).strip()
    if not text:
        return ""
    text = re.sub(r"\s+", " ", text)
    return text


def _render_payload(image: Image.Image) -> bytes:
    buffer = BytesIO()
    image.save(buffer, format="PNG", optimize=True)
    return buffer.getvalue()


def _batch(items: Sequence[tuple[int, Image.Image]], size: int) -> list[list[tuple[int, Image.Image]]]:
    if size <= 0:
        size = 1
    return [list(items[index : index + size]) for index in range(0, len(items), size)]


def _is_retryable_error(exc: Exception) -> bool:
    message = str(exc).lower()
    return any(
        token in message
        for token in (
            "503",
            "unavailable",
            "high demand",
            "resource_exhausted",
            "rate limit",
            "quota",
            "deadline exceeded",
            "timeout",
        )
    )


def _generate_with_retry(client: object, contents: list[object]) -> object:
    last_exc: Exception | None = None
    for attempt in range(5):
        try:
            return client.models.generate_content(  # type: ignore[attr-defined]
                model=settings.gemini_pdf_model,
                contents=contents,
                config=types.GenerateContentConfig(  # type: ignore[attr-defined]
                    temperature=0,
                    response_mime_type="application/json",
                    max_output_tokens=4096,
                ),
            )
        except Exception as exc:
            last_exc = exc
            if attempt >= 4 or not _is_retryable_error(exc):
                raise
            sleep_seconds = min(12.0, 1.5 * (2**attempt))
            time.sleep(sleep_seconds)
    if last_exc is not None:
        raise last_exc
    raise RuntimeError("Gemini request failed without an exception")


def extract_rows_from_pdf_pages(
    pages: Sequence[tuple[int, Image.Image]],
    stats: Any | None = None,
) -> dict[int, list[list[str]]]:
    if not pages:
        return {}

    client = _client()
    results: dict[int, list[list[str]]] = {}

    for batch in _batch(pages, settings.gemini_pdf_batch_size):
        contents: list[object] = [_OCR_PROMPT]
        for page_number, image in batch:
            prepared = _prepare_image(image)
            contents.append(f"\nPAGE: {page_number}\n")
            contents.append(
                types.Part.from_bytes(  # type: ignore[attr-defined]
                    data=_render_payload(prepared),
                    mime_type="image/png",
                )
            )

        try:
            response = _generate_with_retry(client, contents)
        except Exception as exc:
            _warn(stats, f"Gemini PDF OCR batch failed: {exc}")
            continue

        try:
            payload = _extract_json_payload(getattr(response, "text", "") or "{}")
        except Exception as exc:
            _warn(stats, f"Gemini PDF OCR returned invalid JSON: {exc}")
            continue

        page_entries = payload.get("pages", [])
        if not isinstance(page_entries, list):
            _warn(stats, "Gemini PDF OCR payload does not contain a pages array")
            continue

        for page_entry in page_entries:
            if not isinstance(page_entry, dict):
                continue
            page_number = page_entry.get("page")
            try:
                page_number = int(page_number)
            except Exception:
                continue

            page_rows: list[list[str]] = []
            raw_rows = page_entry.get("rows", [])
            if not isinstance(raw_rows, list):
                continue

            for raw_row in raw_rows:
                if isinstance(raw_row, dict):
                    ordered = [
                        _normalize_cell(raw_row.get("code")),
                        _normalize_cell(raw_row.get("service")),
                        _normalize_cell(raw_row.get("resident_price")),
                        _normalize_cell(raw_row.get("nonresident_price")),
                        _normalize_cell(raw_row.get("original_price")),
                        _normalize_cell(raw_row.get("section")),
                    ]
                    row = [cell for cell in ordered if cell]
                elif isinstance(raw_row, list):
                    row = [_normalize_cell(cell) for cell in raw_row if _normalize_cell(cell)]
                else:
                    row = [_normalize_cell(raw_row)]
                if any(row):
                    page_rows.append(row)

            results[page_number] = page_rows

        if results:
            _warn(stats, "PDF OCR used Gemini batch extraction")

    return results
