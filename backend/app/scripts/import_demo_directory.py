from __future__ import annotations

import sys
from pathlib import Path

from app.core.database import SessionLocal, init_db
from app.services.archive_import import import_directory


def main() -> None:
    if len(sys.argv) < 2:
        raise SystemExit("Usage: python -m app.scripts.import_demo_directory <path-to-demo-dir>")

    directory = Path(sys.argv[1])
    if not directory.exists() or not directory.is_dir():
        raise SystemExit(f"Directory not found: {directory}")

    init_db()
    session = SessionLocal()
    try:
        stats = import_directory(session, directory)
    finally:
        session.close()

    print(
        "Imported demo directory: "
        f"partners={stats.partner_count}, documents={stats.document_count}, "
        f"items={stats.item_count}, matched={stats.matched_item_count}"
    )
    if stats.warnings:
        print("Warnings:")
        for warning in stats.warnings:
            print(f"- {warning}")


if __name__ == "__main__":
    main()
