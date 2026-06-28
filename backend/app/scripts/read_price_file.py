from __future__ import annotations

import io
import re
import shutil
import sys
from pathlib import Path

import pdfplumber
from PIL import Image

try:
    import fitz  # type: ignore
except Exception:  # pragma: no cover
    fitz = None

from app.services.ocr import ocr_document_text


def _clean_text(value: object | None) -> str:
    if value is None:
        return ""
    return re.sub(r"\s+", " ", str(value)).strip()


def _page_has_text(page: pdfplumber.page.Page) -> bool:
    text = _clean_text(page.extract_text())
    if text:
        return True
    words = page.extract_words(keep_blank_chars=False, use_text_flow=True)
    return bool(words)


def _extract_pdf_lines(page: pdfplumber.page.Page) -> list[str]:
    words = page.extract_words(keep_blank_chars=False, use_text_flow=True)
    if not words:
        return []

    bands: list[tuple[float, list[dict[str, object]]]] = []
    for word in sorted(words, key=lambda w: (float(w["top"]), float(w["x0"]))):
        top = float(word["top"])
        if not bands or abs(top - bands[-1][0]) > 4:
            bands.append((top, [word]))
        else:
            bands[-1][1].append(word)

    lines: list[str] = []

    for _top, band_words in bands:
        line = " ".join(str(w["text"]) for w in sorted(band_words, key=lambda w: float(w["x0"])))
        line = _clean_text(line)
        if not line:
            continue
        lines.append(line)

    return lines


def _ocr_pdf_lines(path: Path) -> list[tuple[int, list[str]]]:
    if fitz is None:
        raise RuntimeError("OCR is unavailable: install PyMuPDF")

    result: list[tuple[int, list[str]]] = []
    with fitz.open(path) as pdf:  # type: ignore[union-attr]
        for index, page in enumerate(pdf, start=1):
            pixmap = page.get_pixmap(matrix=fitz.Matrix(2, 2), alpha=False)  # type: ignore[union-attr]
            image = Image.open(io.BytesIO(pixmap.tobytes("png")))
            text, _engine = ocr_document_text(image, engine="auto")
            text = _clean_text(text)
            lines = [line.strip() for line in text.splitlines() if line.strip()]
            result.append((index, lines))
    return result


def main() -> None:
    if len(sys.argv) < 2:
        raise SystemExit("Usage: python -m app.scripts.read_price_file <path-to-file>")

    path = Path(sys.argv[1])
    if not path.exists():
        raise SystemExit(f"File not found: {path}")

    if path.suffix.lower() != ".pdf":
        raise SystemExit("This debug script currently handles PDF files only.")

    with pdfplumber.open(path) as pdf:
        text_pages = [page for page in pdf.pages if _page_has_text(page)]
        if text_pages:
            print("MODE: PDF-TEXT")
            for page_number, page in enumerate(pdf.pages, start=1):
                lines = _extract_pdf_lines(page)
                if not lines:
                    continue
                print(f"\n--- PAGE {page_number} ---")
                for line_number, line in enumerate(lines, start=1):
                    print(f"{page_number:03d}:{line_number:04d} {line}")
            return

    print("MODE: OCR")
    for page_number, lines in _ocr_pdf_lines(path):
        if not lines:
            continue
        print(f"\n--- PAGE {page_number} ---")
        for line_number, line in enumerate(lines, start=1):
            print(f"{page_number:03d}:{line_number:04d} {line}")


if __name__ == "__main__":
    main()
