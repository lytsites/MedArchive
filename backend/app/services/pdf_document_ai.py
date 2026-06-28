from __future__ import annotations

import io
from functools import lru_cache
from typing import Any, Sequence

import cv2
import numpy as np
from google.api_core.client_options import ClientOptions
from PIL import Image, ImageEnhance, ImageFilter, ImageOps
from pypdf import PdfReader, PdfWriter

from app.core.config import settings

try:
    from google.cloud import documentai  # type: ignore
except Exception:  # pragma: no cover
    documentai = None

try:
    import fitz  # type: ignore
except Exception:  # pragma: no cover
    fitz = None


def _warn(stats: Any, message: str) -> None:
    warnings = getattr(stats, "warnings", None)
    if isinstance(warnings, list):
        warnings.append(message)


def _clean_text(value: object | None) -> str:
    if value is None:
        return ""
    text = str(value).replace("\u00ad", "")
    return " ".join(text.split()).strip()


def _text_from_anchor(document_text: str, text_anchor: object | None) -> str:
    if not document_text or text_anchor is None:
        return ""
    segments = getattr(text_anchor, "text_segments", None) or []
    parts: list[str] = []
    for segment in segments:
        start_index = int(getattr(segment, "start_index", 0) or 0)
        end_index = int(getattr(segment, "end_index", 0) or 0)
        if end_index > start_index:
            parts.append(document_text[start_index:end_index])
    return _clean_text("".join(parts))


def _page_number(page: object, fallback_index: int) -> int:
    page_number = getattr(page, "page_number", None)
    try:
        return int(page_number)
    except Exception:
        return fallback_index


def _render_pdf_page_image(page: object, dpi: int | None = None) -> Image.Image:
    if fitz is None:
        raise RuntimeError("PyMuPDF is not available")
    resolved_dpi = dpi or settings.pdf_ocr_dpi
    scale = resolved_dpi / 72.0
    pixmap = page.get_pixmap(matrix=fitz.Matrix(scale, scale), alpha=False)  # type: ignore[union-attr]
    return Image.frombytes("RGB", [pixmap.width, pixmap.height], pixmap.samples)


def _deskew_image(image: Image.Image) -> Image.Image:
    rgb = image.convert("RGB")
    array = np.array(rgb)
    gray = cv2.cvtColor(array, cv2.COLOR_RGB2GRAY)
    gray = cv2.GaussianBlur(gray, (3, 3), 0)
    _, thresh = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    coords = np.column_stack(np.where(thresh > 0))
    if coords.size == 0:
        return rgb
    rect = cv2.minAreaRect(coords)
    angle = rect[-1]
    if angle < -45:
        angle = -(90 + angle)
    else:
        angle = -angle
    if abs(angle) < 0.25:
        return rgb
    (h, w) = array.shape[:2]
    center = (w // 2, h // 2)
    matrix = cv2.getRotationMatrix2D(center, angle, 1.0)
    rotated = cv2.warpAffine(
        array,
        matrix,
        (w, h),
        flags=cv2.INTER_CUBIC,
        borderMode=cv2.BORDER_REPLICATE,
    )
    return Image.fromarray(rotated)


def _enhance_image(image: Image.Image) -> Image.Image:
    prepared = image.convert("RGB")
    prepared = ImageOps.autocontrast(prepared)
    prepared = ImageEnhance.Sharpness(prepared).enhance(1.35)
    prepared = ImageEnhance.Contrast(prepared).enhance(1.15)
    prepared = prepared.filter(ImageFilter.SHARPEN)
    return prepared


def _prepare_image(image: Image.Image) -> Image.Image:
    prepared = _deskew_image(image)
    prepared = _enhance_image(prepared)
    min_width = 2200
    if prepared.width and prepared.width < min_width:
        new_height = max(1, int(prepared.height * (min_width / prepared.width)))
        prepared = prepared.resize((min_width, new_height), Image.Resampling.LANCZOS)
    return prepared


def _chunk(items: Sequence[tuple[int, Image.Image]], size: int) -> list[list[tuple[int, Image.Image]]]:
    if size <= 0:
        size = 1
    return [list(items[index : index + size]) for index in range(0, len(items), size)]


def _images_to_pdf_bytes(images: Sequence[Image.Image]) -> bytes:
    if not images:
        return b""
    pdf_images = [img.convert("RGB") for img in images]
    buffer = io.BytesIO()
    first, *rest = pdf_images
    first.save(buffer, format="PDF", save_all=True, append_images=rest)
    return buffer.getvalue()


def _chunk_pdf_bytes(data: bytes, batch_pages: int) -> list[tuple[int, bytes]]:
    if batch_pages <= 0:
        batch_pages = 5
    reader = PdfReader(io.BytesIO(data))
    total_pages = len(reader.pages)
    if total_pages <= batch_pages:
        return [(0, data)]
    batches: list[tuple[int, bytes]] = []
    for start in range(0, total_pages, batch_pages):
        writer = PdfWriter()
        stop = min(start + batch_pages, total_pages)
        for page_index in range(start, stop):
            writer.add_page(reader.pages[page_index])
        buffer = io.BytesIO()
        writer.write(buffer)
        batches.append((start, buffer.getvalue()))
    return batches


@lru_cache(maxsize=1)
def _client() -> object:
    if documentai is None:
        raise RuntimeError("google-cloud-documentai is not installed")
    location = settings.document_ai_location.strip() or "us"
    opts = ClientOptions(api_endpoint=f"{location}-documentai.googleapis.com")
    return documentai.DocumentProcessorServiceClient(client_options=opts)


@lru_cache(maxsize=1)
def _processor_name() -> str:
    if documentai is None:
        raise RuntimeError("google-cloud-documentai is not installed")

    explicit_name = settings.document_ai_processor_name.strip()
    if explicit_name:
        return explicit_name

    project_id = settings.document_ai_project_id.strip()
    location = settings.document_ai_location.strip() or "us"
    if not project_id:
        raise RuntimeError("Document AI project ID is not configured")

    client = _client()
    parent = client.common_location_path(project_id, location)  # type: ignore[attr-defined]
    processor_type = settings.document_ai_processor_type.strip() or "OCR_PROCESSOR"
    display_name = settings.document_ai_processor_display_name.strip()

    try:
        existing = client.list_processors(parent=parent)  # type: ignore[attr-defined]
        for processor in existing:
            if getattr(processor, "display_name", "") == display_name and getattr(processor, "type_", "") == processor_type:
                name = getattr(processor, "name", "")
                if name:
                    return str(name)
    except Exception:
        pass

    if not settings.document_ai_auto_create_processor:
        raise RuntimeError("Document AI processor name is not configured")

    processor = client.create_processor(  # type: ignore[attr-defined]
        parent=parent,
        processor=documentai.Processor(display_name=display_name, type_=processor_type),  # type: ignore[attr-defined]
    )
    name = getattr(processor, "name", "")
    if not name:
        raise RuntimeError("Document AI processor was created without a resource name")
    return str(name)


def _rows_from_table(table: object, document_text: str) -> list[list[str]]:
    rows: list[list[str]] = []
    header_rows = list(getattr(table, "header_rows", []) or [])
    body_rows = list(getattr(table, "body_rows", []) or [])
    for table_row in header_rows + body_rows:
        row_values: list[str] = []
        for cell in getattr(table_row, "cells", []) or []:
            layout = getattr(cell, "layout", None)
            text_anchor = getattr(layout, "text_anchor", None) if layout is not None else None
            cell_text = _text_from_anchor(document_text, text_anchor)
            if cell_text:
                row_values.append(cell_text)
        if any(row_values):
            rows.append(row_values)
    return rows


def _rows_from_lines(page: object, document_text: str) -> list[list[str]]:
    rows: list[list[str]] = []
    line_items: list[tuple[float, float, str]] = []
    for line in getattr(page, "lines", []) or []:
        layout = getattr(line, "layout", None)
        text_anchor = getattr(layout, "text_anchor", None) if layout is not None else None
        text = _text_from_anchor(document_text, text_anchor)
        if not text:
            continue
        bounding_poly = getattr(layout, "bounding_poly", None) if layout is not None else None
        vertices = getattr(bounding_poly, "vertices", None) if bounding_poly is not None else None
        y_value = 0.0
        x_value = 0.0
        if vertices:
            xs = [float(getattr(vertex, "x", 0) or 0) for vertex in vertices]
            ys = [float(getattr(vertex, "y", 0) or 0) for vertex in vertices]
            x_value = min(xs) if xs else 0.0
            y_value = min(ys) if ys else 0.0
        line_items.append((y_value, x_value, text))
    for _, __, text in sorted(line_items, key=lambda item: (item[0], item[1])):
        rows.append([text])
    return rows


def _rows_from_blocks(page: object, document_text: str) -> list[list[str]]:
    block_items: list[tuple[float, float, str]] = []
    for block in getattr(page, "blocks", []) or []:
        layout = getattr(block, "layout", None)
        text_anchor = getattr(layout, "text_anchor", None) if layout is not None else None
        text = _text_from_anchor(document_text, text_anchor)
        if not text:
            continue
        bounding_poly = getattr(layout, "bounding_poly", None) if layout is not None else None
        vertices = getattr(bounding_poly, "vertices", None) if bounding_poly is not None else None
        y_value = 0.0
        x_value = 0.0
        if vertices:
            xs = [float(getattr(vertex, "x", 0) or 0) for vertex in vertices]
            ys = [float(getattr(vertex, "y", 0) or 0) for vertex in vertices]
            x_value = min(xs) if xs else 0.0
            y_value = min(ys) if ys else 0.0
        block_items.append((y_value, x_value, text))

    if not block_items:
        return []

    block_items.sort(key=lambda item: (item[0], item[1]))
    rows: list[list[str]] = []
    current_row: list[tuple[float, str]] = []
    last_y: float | None = None
    row_tolerance = 10.0

    for y_value, x_value, text in block_items:
        if last_y is None or abs(y_value - last_y) <= row_tolerance:
            current_row.append((x_value, text))
            last_y = y_value
            continue
        current_row.sort(key=lambda item: item[0])
        row_values = [_clean_text(value) for _, value in current_row if _clean_text(value)]
        if row_values:
            rows.append(row_values)
        current_row = [(x_value, text)]
        last_y = y_value

    if current_row:
        current_row.sort(key=lambda item: item[0])
        row_values = [_clean_text(value) for _, value in current_row if _clean_text(value)]
        if row_values:
            rows.append(row_values)
    return rows


def _extract_from_document(document: object, page_offset: int, stats: Any | None = None) -> tuple[list[list[str]], str]:
    document_text = getattr(document, "text", "") or ""
    rows: list[list[str]] = []
    content_lines: list[str] = []

    for page_index, page in enumerate(getattr(document, "pages", []) or [], start=1):
        page_number = _page_number(page, page_offset + page_index)
        page_rows: list[list[str]] = []

        for table in getattr(page, "tables", []) or []:
            page_rows.extend(_rows_from_table(table, document_text))

        if not page_rows:
            page_rows.extend(_rows_from_blocks(page, document_text))

        if not page_rows:
            page_rows.extend(_rows_from_lines(page, document_text))

        if page_rows:
            rows.extend(page_rows)
            content_lines.extend(" | ".join(cell for cell in row if cell) for row in page_rows if any(cell for cell in row))
        elif document_text:
            content_lines.append(f"[page {page_number}]")

    if not rows and document_text:
        rows = [[line] for line in (_clean_text(line) for line in document_text.splitlines()) if line]
        content_lines = [line for line in (_clean_text(line) for line in document_text.splitlines()) if line]

    if rows:
        _warn(stats, "PDF OCR used Document AI")
    return rows, "\n".join(content_lines or [document_text])


def _extract_rows_from_pdf_chunk(data: bytes, page_offset: int, stats: Any | None = None) -> tuple[list[list[str]], str]:
    if documentai is None:
        raise RuntimeError("google-cloud-documentai is not installed")
    if not data:
        return [], ""

    processor_name = _processor_name()
    client = _client()
    raw_document = documentai.RawDocument(content=data, mime_type="application/pdf")  # type: ignore[attr-defined]
    request_kwargs = {
        "name": processor_name,
        "raw_document": raw_document,
    }

    try:
        response = client.process_document(request=documentai.ProcessRequest(**request_kwargs))  # type: ignore[attr-defined]
    except Exception as exc:
        _warn(stats, f"Document AI OCR failed: {exc}")
        raise

    document = getattr(response, "document", None)
    if document is None:
        return [], ""
    return _extract_from_document(document, page_offset, stats)


def extract_rows_from_pdf_bytes(data: bytes, stats: Any | None = None) -> tuple[list[list[str]], str]:
    if documentai is None:
        raise RuntimeError("google-cloud-documentai is not installed")
    if not data:
        return [], ""

    if fitz is None:
        batch_pages = max(1, int(getattr(settings, "document_ai_batch_pages", 5) or 5))
        all_rows: list[list[str]] = []
        all_chunks: list[str] = []
        chunk_batches = _chunk_pdf_bytes(data, batch_pages)
        if len(chunk_batches) == 1:
            return _extract_rows_from_pdf_chunk(data, 0, stats)
        for page_offset, chunk_data in chunk_batches:
            rows, content = _extract_rows_from_pdf_chunk(chunk_data, page_offset, stats)
            if rows:
                all_rows.extend(rows)
            if content:
                all_chunks.append(content)
        return all_rows, "\n".join(chunk for chunk in all_chunks if chunk)

    rendered_pages: list[tuple[int, Image.Image]] = []
    with fitz.open(stream=data, filetype="pdf") as pdf:  # type: ignore[union-attr]
        for page_index, page in enumerate(pdf, start=1):
            try:
                rendered = _render_pdf_page_image(page, dpi=settings.pdf_ocr_dpi)
                rendered_pages.append((page_index, _prepare_image(rendered)))
            except Exception as exc:
                _warn(stats, f"Document AI page render failed: {exc}")

    if not rendered_pages:
        return [], ""

    batch_pages = max(1, int(getattr(settings, "document_ai_batch_pages", 5) or 5))
    all_rows: list[list[str]] = []
    all_chunks: list[str] = []
    for batch in _chunk(rendered_pages, batch_pages):
        page_offset = batch[0][0] - 1
        batch_pdf = _images_to_pdf_bytes([image for _, image in batch])
        if not batch_pdf:
            continue
        rows, content = _extract_rows_from_pdf_chunk(batch_pdf, page_offset, stats)
        if rows:
            all_rows.extend(rows)
        if content:
            all_chunks.append(content)
    return all_rows, "\n".join(chunk for chunk in all_chunks if chunk)
