from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    database_url: str = "postgresql+psycopg://medarchive:medarchive@postgres:5432/medarchive"
    redis_url: str = "redis://redis:6379/0"
    cors_origins_raw: str = "http://localhost:3000,http://127.0.0.1:3000"
    storage_dir: str = "/app/storage"
    ocr_provider: str = "auto"
    google_vision_language_hints_raw: str = "ru,en"
    document_ai_project_id: str = ""
    document_ai_location: str = "us"
    document_ai_processor_name: str = ""
    document_ai_processor_display_name: str = "medarchive-pdf-ocr"
    document_ai_processor_type: str = "OCR_PROCESSOR"
    document_ai_auto_create_processor: bool = True
    document_ai_batch_pages: int = 5
    gemini_api_key: str = ""
    gemini_pdf_model: str = "gemini-2.5-flash"
    gemini_pdf_batch_size: int = 5
    pdf_ocr_dpi: int = 220
    service_match_auto_threshold: int = 92
    service_match_review_threshold: int = 85
    exchange_rate_api_url: str = "https://open.er-api.com/v6/latest/{currency}"
    exchange_rate_timeout_seconds: float = 5.0

    @property
    def cors_origins(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins_raw.split(",") if origin.strip()]

    @property
    def google_vision_language_hints(self) -> list[str]:
        return [hint.strip() for hint in self.google_vision_language_hints_raw.split(",") if hint.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
