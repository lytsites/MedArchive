from __future__ import annotations

from functools import lru_cache
from io import BytesIO
from typing import Literal

from PIL import Image

from app.core.config import settings

try:
    from google.cloud import vision  # type: ignore
except Exception:  # pragma: no cover
    vision = None

try:
    import pytesseract  # type: ignore
except Exception:  # pragma: no cover
    pytesseract = None

OcrEngine = Literal["auto", "vision", "tesseract"]


@lru_cache(maxsize=1)
def _vision_client() -> object:
    if vision is None:
        raise RuntimeError("google-cloud-vision is not installed")
    return vision.ImageAnnotatorClient()


def vision_available() -> bool:
    if vision is None:
        return False
    try:
        _vision_client()
        return True
    except Exception:
        return False


def _vision_document_text(image: Image.Image) -> str:
    client = _vision_client()
    buffer = BytesIO()
    image.save(buffer, format="PNG")
    image_bytes = buffer.getvalue()
    response = client.document_text_detection(  # type: ignore[attr-defined]
        image=vision.Image(content=image_bytes),  # type: ignore[union-attr]
        image_context=vision.ImageContext(language_hints=settings.google_vision_language_hints),  # type: ignore[union-attr]
    )
    annotation = getattr(response, "full_text_annotation", None)
    text = getattr(annotation, "text", "") if annotation is not None else ""
    return text or ""


def _tesseract_document_text(image: Image.Image) -> str:
    if pytesseract is None:
        raise RuntimeError("pytesseract is not installed")
    try:
        text = pytesseract.image_to_string(image, lang="rus+eng")
    except Exception:
        text = pytesseract.image_to_string(image)
    return text or ""


def ocr_document_text(image: Image.Image, engine: OcrEngine = "auto") -> tuple[str, str]:
    preferred = settings.ocr_provider.strip().lower()
    if engine == "auto":
        engine = "vision" if preferred in {"auto", "vision"} else "tesseract"

    if engine == "vision":
        try:
            return _vision_document_text(image), "vision"
        except Exception:
            if preferred == "vision":
                raise RuntimeError(
                    "Google Vision OCR is enabled, but the client could not be created. "
                    "Check GOOGLE_APPLICATION_CREDENTIALS and the mounted credentials file."
                )

    return _tesseract_document_text(image), "tesseract"
