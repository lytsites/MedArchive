from __future__ import annotations

import uuid
from datetime import date, datetime

from pydantic import BaseModel, Field


class PartnerOut(BaseModel):
    partner_id: uuid.UUID
    name: str
    city: str | None = None
    address: str | None = None
    bin: str | None = None
    contact_email: str | None = None
    contact_phone: str | None = None
    is_active: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ArchiveOut(BaseModel):
    archive_id: uuid.UUID
    partner_id: uuid.UUID | None = None
    file_name: str
    saved_path: str
    status: str
    partner_count: int
    document_count: int
    item_count: int
    matched_item_count: int
    warnings: list[str] | None = None
    uploaded_at: datetime
    processed_at: datetime | None = None

    model_config = {"from_attributes": True}


class ServiceOut(BaseModel):
    service_id: uuid.UUID
    service_name: str
    synonyms: list[str] | None = None
    category: str | None = None
    icd_code: str | None = None
    is_active: bool

    model_config = {"from_attributes": True}


class PriceDocumentOut(BaseModel):
    doc_id: uuid.UUID
    partner_id: uuid.UUID
    file_name: str
    source_path: str | None = None
    file_format: str
    effective_date: date | None = None
    parsed_at: datetime | None = None
    parse_status: str
    parse_log: str | None = None
    raw_content: str | None = None

    model_config = {"from_attributes": True}


class PriceItemOut(BaseModel):
    item_id: uuid.UUID
    doc_id: uuid.UUID
    partner_id: uuid.UUID
    service_name_raw: str
    service_code_source: str | None = None
    service_id: uuid.UUID | None = None
    price_resident_kzt: float | None = None
    price_nonresident_kzt: float | None = None
    price_original: float | None = None
    currency_original: str | None = None
    is_verified: bool
    verification_note: str | None = None
    effective_date: date | None = None
    is_active: bool

    model_config = {"from_attributes": True}


class DocumentItemOut(BaseModel):
    item_id: uuid.UUID
    service_name_raw: str
    service_code_source: str | None = None
    price_original: float | None = None
    currency_original: str | None = None
    is_verified: bool
    verification_note: str | None = None

    model_config = {"from_attributes": True}


class DocumentGroupOut(BaseModel):
    doc_id: uuid.UUID
    partner_id: uuid.UUID
    partner_name: str
    file_name: str
    file_base_name: str
    source_path: str | None = None
    source_label: str
    effective_date: date | None = None
    parse_status: str
    items: list[DocumentItemOut]


class DocumentsResponse(BaseModel):
    documents: list[DocumentGroupOut]


class DocumentDetailOut(BaseModel):
    document: PriceDocumentOut
    partner: PartnerOut
    archive: ArchiveOut | None = None
    items: list[PriceItemOut]


class ArchiveDocumentOut(BaseModel):
    doc_id: uuid.UUID
    partner_id: uuid.UUID
    partner_name: str
    file_name: str
    file_base_name: str
    source_path: str | None = None
    source_label: str
    effective_date: date | None = None
    parse_status: str
    item_count: int


class ArchiveDetailOut(BaseModel):
    archive: ArchiveOut
    documents: list[ArchiveDocumentOut]


class ArchivesResponse(BaseModel):
    archives: list[ArchiveOut]


class SearchResponse(BaseModel):
    services: list[ServiceOut]
    partners: list[PartnerOut]


class ServicePartnerOut(BaseModel):
    partner: PartnerOut
    price_item: PriceItemOut


class PartnerServiceOut(BaseModel):
    price_item: PriceItemOut
    service: ServiceOut | None = None


class PartnerProfileOut(BaseModel):
    partner: PartnerOut
    documents: list[DocumentGroupOut]
    items: list[PartnerServiceOut]
    latest_effective_date: date | None = None


class MatchRequest(BaseModel):
    item_id: uuid.UUID = Field(...)
    service_id: uuid.UUID | None = None
    create_service_name: str | None = None
    create_service_category: str | None = None
    create_service_code: str | None = None
    verification_note: str | None = None


class MatchResponse(BaseModel):
    ok: bool
    item_id: uuid.UUID
    service_id: uuid.UUID


class ReviewItemUpdate(BaseModel):
    item_id: uuid.UUID
    service_name_raw: str
    service_code_source: str | None = None
    price_resident_kzt: float | None = None
    price_nonresident_kzt: float | None = None
    price_original: float | None = None
    currency_original: str | None = "KZT"


class DocumentReviewRequest(BaseModel):
    items: list[ReviewItemUpdate]


class DocumentReviewResponse(BaseModel):
    ok: bool
    doc_id: uuid.UUID
    status: str
    item_count: int


class UploadArchiveResponse(BaseModel):
    ok: bool
    archive_id: uuid.UUID | None = None
    file_name: str
    saved_path: str
    status: str
    partner_count: int
    document_count: int
    item_count: int
    matched_item_count: int
    warnings: list[str] = Field(default_factory=list)


class UploadDocumentResponse(BaseModel):
    ok: bool
    doc_id: uuid.UUID | None = None
    partner_id: uuid.UUID | None = None
    partner_name: str | None = None
    file_name: str
    saved_path: str
    status: str
    item_count: int
    warnings: list[str] = Field(default_factory=list)


class UnifiedUploadResponse(BaseModel):
    ok: bool
    upload_type: str
    file_name: str
    saved_path: str
    status: str
    archive_id: uuid.UUID | None = None
    doc_id: uuid.UUID | None = None
    partner_id: uuid.UUID | None = None
    partner_name: str | None = None
    partner_count: int | None = None
    document_count: int | None = None
    item_count: int | None = None
    matched_item_count: int | None = None
    warnings: list[str] = Field(default_factory=list)


class DeleteResponse(BaseModel):
    ok: bool
    deleted_id: str
    deleted_type: str
