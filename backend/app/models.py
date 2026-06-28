from __future__ import annotations

import uuid
from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Index, Numeric, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class Partner(Base):
    __tablename__ = "partners"

    partner_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    city: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)
    address: Mapped[str | None] = mapped_column(String(500), nullable=True)
    bin: Mapped[str | None] = mapped_column(String(12), nullable=True, index=True)
    contact_email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    contact_phone: Mapped[str | None] = mapped_column(String(64), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    documents: Mapped[list["PriceDocument"]] = relationship(back_populates="partner")
    items: Mapped[list["PriceItem"]] = relationship(back_populates="partner")
    archives: Mapped[list["ArchiveBatch"]] = relationship(back_populates="partner")


class ArchiveBatch(Base):
    __tablename__ = "archive_batches"

    archive_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    partner_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("partners.partner_id"), nullable=True, index=True)
    file_name: Mapped[str] = mapped_column(String(500), nullable=False)
    saved_path: Mapped[str] = mapped_column(String(1000), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="processing", index=True)
    partner_count: Mapped[int] = mapped_column(default=0)
    document_count: Mapped[int] = mapped_column(default=0)
    item_count: Mapped[int] = mapped_column(default=0)
    matched_item_count: Mapped[int] = mapped_column(default=0)
    warnings: Mapped[list[str] | None] = mapped_column(JSONB, nullable=True, default=list)
    uploaded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    partner: Mapped[Partner | None] = relationship(back_populates="archives")
    documents: Mapped[list["PriceDocument"]] = relationship(back_populates="archive")


class Service(Base):
    __tablename__ = "services"

    service_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    service_name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    synonyms: Mapped[list[str] | None] = mapped_column(JSONB, nullable=True, default=list)
    category: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    icd_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    price_items: Mapped[list["PriceItem"]] = relationship(back_populates="service")


class PriceDocument(Base):
    __tablename__ = "price_documents"

    doc_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    archive_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("archive_batches.archive_id"), nullable=True, index=True)
    partner_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("partners.partner_id"), nullable=False, index=True)
    file_name: Mapped[str] = mapped_column(String(500), nullable=False)
    source_path: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    file_format: Mapped[str] = mapped_column(String(32), nullable=False)
    effective_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    parsed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    parse_status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending", index=True)
    parse_log: Mapped[str | None] = mapped_column(Text, nullable=True)
    raw_content: Mapped[str | None] = mapped_column(Text, nullable=True)

    archive: Mapped[ArchiveBatch | None] = relationship(back_populates="documents")
    partner: Mapped[Partner] = relationship(back_populates="documents")
    items: Mapped[list["PriceItem"]] = relationship(back_populates="document")


class PriceItem(Base):
    __tablename__ = "price_items"
    __table_args__ = (
        Index("ix_price_items_unmatched", "service_id", "is_active"),
    )

    item_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    doc_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("price_documents.doc_id"), nullable=False, index=True)
    partner_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("partners.partner_id"), nullable=False, index=True)
    service_name_raw: Mapped[str] = mapped_column(String(500), nullable=False)
    service_code_source: Mapped[str | None] = mapped_column(String(128), nullable=True)
    service_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("services.service_id"), nullable=True, index=True)
    price_resident_kzt: Mapped[float | None] = mapped_column(Numeric(12, 2), nullable=True)
    price_nonresident_kzt: Mapped[float | None] = mapped_column(Numeric(12, 2), nullable=True)
    price_original: Mapped[float | None] = mapped_column(Numeric(12, 2), nullable=True)
    currency_original: Mapped[str | None] = mapped_column(String(12), nullable=True)
    is_verified: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    verification_note: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    effective_date: Mapped[date | None] = mapped_column(Date, nullable=True, index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    document: Mapped[PriceDocument] = relationship(back_populates="items")
    partner: Mapped[Partner] = relationship(back_populates="items")
    service: Mapped[Service | None] = relationship(back_populates="price_items")
