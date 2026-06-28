from __future__ import annotations

import glob
from pathlib import Path

import fitz

from app.services.pdf_table_ocr import extract_pdf_table_rows_from_page


def main() -> None:
    paths = [Path(p) for p in glob.glob("/app/demo/*2026.pdf")]
    pdf_path = next((path for path in paths if path.name.endswith("1 2026.pdf")), None)
    if pdf_path is None:
        raise SystemExit("Target PDF not found")

    with fitz.open(pdf_path) as pdf:
        for page_number in [0, 1]:
            print(f"--- PAGE {page_number + 1} ---")
            page = pdf[page_number]
            rows, _content = extract_pdf_table_rows_from_page(page, None)
            for idx, (code, name, price) in enumerate(rows[:80], start=1):
                print(f"{page_number+1:03d}:{idx:04d} {code} | {name} | {price}")


if __name__ == "__main__":
    main()
