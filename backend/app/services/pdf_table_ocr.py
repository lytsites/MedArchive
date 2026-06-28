from __future__ import annotations

import re
from dataclasses import dataclass
from functools import lru_cache
from io import BytesIO
from typing import Any

import cv2
import numpy as np
from PIL import Image, ImageEnhance, ImageFilter, ImageOps

from app.core.config import settings
from app.services.pdf_layout import rows_from_words

try:
    from google.cloud import vision  # type: ignore
except Exception:  # pragma: no cover
    vision = None

try:
    import fitz  # type: ignore
except Exception:  # pragma: no cover
    fitz = None

_VISION_ERROR_MESSAGE: str | None = None


@dataclass(frozen=True)
class WordBox:
    text: str
    x0: int
    y0: int
    x1: int
    y1: int

    @property
    def cx(self) -> float:
        return (self.x0 + self.x1) / 2

    @property
    def cy(self) -> float:
        return (self.y0 + self.y1) / 2


def _warn(stats: Any, message: str) -> None:
    warnings = getattr(stats, "warnings", None)
    if isinstance(warnings, list):
        warnings.append(message)


@lru_cache(maxsize=1)
def _vision_client() -> object:
    if vision is None:
        raise RuntimeError("google-cloud-vision is not installed")
    return vision.ImageAnnotatorClient()


def _render_page(page: "fitz.Page", dpi: int = 300) -> Image.Image:
    scale = dpi / 72.0
    pix = page.get_pixmap(matrix=fitz.Matrix(scale, scale), alpha=False)  # type: ignore[union-attr]
    return Image.frombytes("RGB", [pix.width, pix.height], pix.samples)


def _preprocess_image(image: Image.Image) -> np.ndarray:
    image = ImageOps.grayscale(image)
    image = ImageOps.autocontrast(image)
    image = image.filter(ImageFilter.MedianFilter(size=3))
    image = ImageEnhance.Sharpness(image).enhance(1.8)
    arr = np.array(image)
    arr = cv2.GaussianBlur(arr, (3, 3), 0)
    _, binary = cv2.threshold(arr, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    return binary


def _cluster_positions(indices: np.ndarray, min_gap: int = 8) -> list[int]:
    if indices.size == 0:
        return []
    clusters: list[list[int]] = [[int(indices[0])]]
    for value in map(int, indices[1:]):
        if value - clusters[-1][-1] <= min_gap:
            clusters[-1].append(value)
        else:
            clusters.append([value])
    return [int(round(sum(cluster) / len(cluster))) for cluster in clusters]


def _detect_lines(binary: np.ndarray) -> tuple[list[int], list[int]]:
    inv = 255 - binary
    h, w = inv.shape

    vertical_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (1, max(20, h // 30)))
    horizontal_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (max(20, w // 20), 1))

    vertical = cv2.erode(inv, vertical_kernel, iterations=1)
    vertical = cv2.dilate(vertical, vertical_kernel, iterations=1)

    horizontal = cv2.erode(inv, horizontal_kernel, iterations=1)
    horizontal = cv2.dilate(horizontal, horizontal_kernel, iterations=1)

    vertical_score = vertical.sum(axis=0)
    horizontal_score = horizontal.sum(axis=1)

    vertical_threshold = max(vertical_score.max() * 0.45, vertical_score.mean() * 2.5)
    horizontal_threshold = max(horizontal_score.max() * 0.35, horizontal_score.mean() * 2.5)

    vertical_candidates = np.where(vertical_score >= vertical_threshold)[0]
    horizontal_candidates = np.where(horizontal_score >= horizontal_threshold)[0]

    x_lines = _cluster_positions(vertical_candidates, min_gap=max(6, w // 250))
    y_lines = _cluster_positions(horizontal_candidates, min_gap=max(6, h // 250))

    return x_lines, y_lines


def _clean_code(value: str) -> str:
    value = value.strip()
    value = value.replace(" ", "")
    value = value.replace("Рћ", "O").replace("Рѕ", "o")
    return value


def _choose_boundaries(x_lines: list[int], width: int) -> tuple[list[int], int, int, int]:
    if len(x_lines) >= 4:
        inner = [x for x in sorted(set(x_lines)) if 0.05 * width < x < 0.95 * width]
        if len(inner) >= 3:
            left = inner[0]
            right = inner[-1]
            code_split = inner[len(inner) // 3]
            price_split = inner[-2]
            boundaries = [left] + inner[1:-1] + [right]
            return boundaries, left, code_split, price_split
    left = int(width * 0.10)
    code_split = int(width * 0.23)
    price_split = int(width * 0.84)
    right = int(width * 0.95)
    boundaries = [left, code_split, price_split, right]
    return boundaries, left, code_split, price_split


def _vision_words_for_page(image: Image.Image) -> list[WordBox]:
    global _VISION_ERROR_MESSAGE
    if vision is None:
        raise RuntimeError("google-cloud-vision is not installed")
    if _VISION_ERROR_MESSAGE:
        raise RuntimeError(_VISION_ERROR_MESSAGE)

    buffer = BytesIO()
    image.save(buffer, format="PNG")
    client = _vision_client()
    response = client.document_text_detection(  # type: ignore[attr-defined]
        image=vision.Image(content=buffer.getvalue()),  # type: ignore[union-attr]
        image_context=vision.ImageContext(language_hints=settings.google_vision_language_hints),  # type: ignore[union-attr]
    )
    annotation = getattr(response, "full_text_annotation", None)
    if annotation is None or not getattr(annotation, "pages", None):
        return []

    words: list[WordBox] = []
    for page in annotation.pages:
        for block in getattr(page, "blocks", []):
            for paragraph in getattr(block, "paragraphs", []):
                for word in getattr(paragraph, "words", []):
                    text = "".join(symbol.text for symbol in getattr(word, "symbols", [])).strip()
                    bbox = getattr(word, "bounding_box", None)
                    vertices = getattr(bbox, "vertices", None) if bbox is not None else None
                    if not text or not vertices:
                        continue
                    xs = [int(getattr(vertex, "x", 0) or 0) for vertex in vertices]
                    ys = [int(getattr(vertex, "y", 0) or 0) for vertex in vertices]
                    words.append(WordBox(text=text, x0=min(xs), y0=min(ys), x1=max(xs), y1=max(ys)))
    return words


def _assign_words_to_cells(words: list[WordBox], x_bounds: list[int], y_bounds: list[int]) -> list[list[str]]:
    if len(x_bounds) < 2 or len(y_bounds) < 2:
        return []

    cells: list[list[list[WordBox]]] = [
        [[] for _ in range(len(x_bounds) - 1)]
        for _ in range(len(y_bounds) - 1)
    ]

    for word in words:
        for row_idx in range(len(y_bounds) - 1):
            if not (y_bounds[row_idx] <= word.cy < y_bounds[row_idx + 1]):
                continue
            for col_idx in range(len(x_bounds) - 1):
                if x_bounds[col_idx] <= word.cx < x_bounds[col_idx + 1]:
                    cells[row_idx][col_idx].append(word)
                    break
            break

    rows: list[list[str]] = []
    for row_cells in cells:
        row_texts: list[str] = []
        for cell_words in row_cells:
            if not cell_words:
                row_texts.append("")
                continue
            ordered = sorted(cell_words, key=lambda item: (item.y0, item.x0))
            row_text = " ".join(word.text for word in ordered)
            row_texts.append(re.sub(r"\s+", " ", row_text).strip())
        if any(row_texts):
            rows.append(row_texts)
    return rows


def _row_has_content(row: list[str]) -> bool:
    return any(cell.strip() for cell in row)


def _vision_rows_from_page(image: Image.Image) -> tuple[list[list[str]], str]:
    words = _vision_words_for_page(image)
    if not words:
        return [], ""
    rows = rows_from_words(words, page_width=image.width)
    text_chunks = [" | ".join(cell for cell in row if cell) for row in rows if any(cell for cell in row)]
    return rows, "\n".join(text_chunks)


def extract_pdf_table_rows_from_page(page: "fitz.Page", stats: Any | None = None) -> tuple[list[list[str]], str]:
    global _VISION_ERROR_MESSAGE
    if _VISION_ERROR_MESSAGE:
        return [], ""

    image = _render_page(page, dpi=300)
    binary = _preprocess_image(image)
    x_lines, y_lines = _detect_lines(binary)
    if len(x_lines) < 2 or len(y_lines) < 2:
        return [], ""

    x_bounds = [0] + sorted(set(x_lines)) + [image.width]
    y_bounds = [0] + sorted(set(y_lines)) + [image.height]

    try:
        words = _vision_words_for_page(image)
    except Exception as exc:
        message = str(exc)
        _VISION_ERROR_MESSAGE = message
        _warn(stats, f"Google Vision page OCR failed: {message}")
        return [], ""

    rows = _assign_words_to_cells(words, x_bounds, y_bounds)
    filtered_rows: list[list[str]] = []
    text_chunks: list[str] = []

    for row in rows:
        row_text = " ".join(cell for cell in row if cell).strip()
        if not row_text:
            continue
        if not re.search(r"\d", row_text) and not re.search(r"[A-ZА-Я]{1,4}\d", row_text, flags=re.IGNORECASE):
            continue
        if not _row_has_content(row):
            continue
        filtered_rows.append(row)
        text_chunks.append(" | ".join(cell for cell in row if cell))

    if filtered_rows:
        _warn(stats, "PDF table OCR used Google Vision page OCR")
    return filtered_rows, "\n".join(text_chunks)


def extract_pdf_table_rows_from_page_v2(page: "fitz.Page", stats: Any | None = None) -> tuple[list[list[str]], str]:
    global _VISION_ERROR_MESSAGE
    if _VISION_ERROR_MESSAGE:
        return [], ""

    image = _render_page(page, dpi=300)
    try:
        rows, text = _vision_rows_from_page(image)
    except Exception as exc:
        message = str(exc)
        _VISION_ERROR_MESSAGE = message
        _warn(stats, f"Google Vision page OCR failed: {message}")
        return [], ""

    if rows:
        _warn(stats, "PDF table OCR used Google Vision page OCR")
        return rows, text

    binary = _preprocess_image(image)
    x_lines, y_lines = _detect_lines(binary)
    if len(x_lines) < 2 or len(y_lines) < 2:
        return [], ""

    x_bounds = [0] + sorted(set(x_lines)) + [image.width]
    y_bounds = [0] + sorted(set(y_lines)) + [image.height]
    words = _vision_words_for_page(image)
    fallback_rows = _assign_words_to_cells(words, x_bounds, y_bounds)
    filtered_rows: list[list[str]] = []
    text_chunks: list[str] = []

    for row in fallback_rows:
        row_text = " ".join(cell for cell in row if cell).strip()
        if not row_text:
            continue
        if not re.search(r"\d", row_text) and not re.search(r"[A-ZРђ-РЇ]{1,4}\d", row_text, flags=re.IGNORECASE):
            continue
        if not _row_has_content(row):
            continue
        filtered_rows.append(row)
        text_chunks.append(" | ".join(cell for cell in row if cell))

    if filtered_rows:
        _warn(stats, "PDF table OCR used Google Vision page OCR")
    return filtered_rows, "\n".join(text_chunks)


def extract_pdf_table_rows(data: bytes, stats: Any | None = None) -> tuple[list[list[str]], str]:
    if fitz is None:
        _warn(stats, "PDF table OCR skipped: PyMuPDF is not available")
        return [], ""

    rows: list[list[str]] = []
    text_chunks: list[str] = []
    with fitz.open(stream=data, filetype="pdf") as pdf:  # type: ignore[union-attr]
        for page in pdf:
            page_rows, page_text = extract_pdf_table_rows_from_page_v2(page, stats)
            rows.extend(page_rows)
            if page_text:
                text_chunks.append(page_text)
    return rows, "\n".join(text_chunks)
