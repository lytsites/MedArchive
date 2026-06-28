import shutil
import zipfile
from pathlib import Path
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import SessionLocal, get_db
from app.models import ArchiveBatch, Partner, PriceDocument, PriceItem, Service
from app.services.archive_import import import_archive, import_single_document
from app.schemas import (
    ArchiveDetailOut,
    ArchiveDocumentOut,
    ArchiveOut,
    DeleteResponse,
    ArchivesResponse,
    DocumentReviewRequest,
    DocumentReviewResponse,
    DocumentDetailOut,
    DocumentGroupOut,
    DocumentsResponse,
    MatchRequest,
    MatchResponse,
    PartnerOut,
    PartnerServiceOut,
    PartnerProfileOut,
    DocumentItemOut,
    PriceDocumentOut,
    PriceItemOut,
    SearchResponse,
    ServiceOut,
    ServicePartnerOut,
    UploadArchiveResponse,
    UploadDocumentResponse,
    UnifiedUploadResponse,
)

router = APIRouter()


def _source_label(document: PriceDocument) -> str:
    format_map = {
        "docx": "WORD",
        "xlsx": "EXCEL",
        "xls": "EXCEL",
        "pdf": "PDF",
    }
    return format_map.get(document.file_format.lower(), document.file_format.upper())


def _remove_path(path_str: str | None) -> None:
    if not path_str:
        return
    path = Path(path_str)
    try:
        if path.is_dir():
            shutil.rmtree(path, ignore_errors=True)
        elif path.exists():
            path.unlink()
    except OSError:
        return


async def _save_upload(file: UploadFile) -> tuple[Path, bytes]:
    storage_dir = Path(settings.storage_dir)
    storage_dir.mkdir(parents=True, exist_ok=True)
    suffix = Path(file.filename or "upload").suffix or ".bin"
    content = await file.read()
    saved_path = storage_dir / f"{uuid4().hex}{suffix}"
    saved_path.write_bytes(content)
    return saved_path, content


def _archive_response(
    *,
    file_name: str,
    saved_path: Path,
    stats,
) -> UnifiedUploadResponse:
    archive_id = UUID(stats.archive_id) if stats.archive_id else None
    archive_status = "processed"
    if archive_id is not None:
        with SessionLocal() as lookup_session:
            archive = lookup_session.get(ArchiveBatch, archive_id)
            if archive is not None:
                archive_status = archive.status
    return UnifiedUploadResponse(
        ok=True,
        upload_type="archive",
        archive_id=archive_id,
        file_name=file_name,
        saved_path=str(saved_path),
        status=archive_status,
        partner_count=stats.partner_count,
        document_count=stats.document_count,
        item_count=stats.item_count,
        matched_item_count=stats.matched_item_count,
        warnings=stats.warnings,
    )


def _document_response(
    *,
    file_name: str,
    saved_path: Path,
    stats,
    document: PriceDocument,
) -> UnifiedUploadResponse:
    partner_name = None
    partner_id = None
    with SessionLocal() as lookup_session:
        partner = lookup_session.get(Partner, document.partner_id)
        if partner is not None:
            partner_name = partner.name
            partner_id = partner.partner_id
    return UnifiedUploadResponse(
        ok=True,
        upload_type="document",
        doc_id=document.doc_id,
        partner_id=partner_id,
        partner_name=partner_name,
        file_name=file_name,
        saved_path=str(saved_path),
        status=document.parse_status,
        item_count=stats.item_count,
        warnings=stats.warnings,
    )


def _recalculate_archive_totals(db: Session, archive_id: UUID) -> None:
    archive = db.get(ArchiveBatch, archive_id)
    if archive is None:
        return
    documents = list(
        db.scalars(
            select(PriceDocument).where(PriceDocument.archive_id == archive_id)
        ).all()
    )
    document_ids = [document.doc_id for document in documents]
    item_count = 0
    matched_count = 0
    if document_ids:
        item_count = db.scalar(
            select(func.count()).select_from(PriceItem).where(PriceItem.doc_id.in_(document_ids))
        ) or 0
        matched_count = db.scalar(
            select(func.count()).select_from(PriceItem).where(
                PriceItem.doc_id.in_(document_ids),
                PriceItem.service_id.is_not(None),
            )
        ) or 0
    archive.document_count = len(documents)
    archive.item_count = item_count
    archive.matched_item_count = matched_count
    if any(document.parse_status == "error" for document in documents):
        archive.status = "error"
    elif not documents or any(document.parse_status == "needs_review" for document in documents):
        archive.status = "needs_review"
    else:
        archive.status = "processed"


def _document_needs_review(db: Session, doc_id: UUID) -> bool:
    items = list(db.scalars(select(PriceItem).where(PriceItem.doc_id == doc_id)).all())
    if not items:
        return True
    for item in items:
        has_price = any(
            value is not None
            for value in (
                item.price_resident_kzt,
                item.price_nonresident_kzt,
                item.price_original,
            )
        )
        invalid_price = any(
            value <= 0
            for value in (
                item.price_resident_kzt,
                item.price_nonresident_kzt,
                item.price_original,
            )
            if value is not None
        )
        invalid_nonresident_price = (
            item.price_resident_kzt is not None
            and item.price_nonresident_kzt is not None
            and item.price_nonresident_kzt < item.price_resident_kzt
        )
        if not item.is_verified and (
            item.service_id is None
            or not has_price
            or invalid_price
            or invalid_nonresident_price
            or bool(item.verification_note and "price date is in the future" in item.verification_note)
            or bool(item.verification_note and "anomaly:" in item.verification_note)
        ):
            return True
    return False


def _item_needs_review(item: PriceItem) -> bool:
    if item.is_verified:
        return False
    has_price = any(
        value is not None
        for value in (
            item.price_resident_kzt,
            item.price_nonresident_kzt,
            item.price_original,
        )
    )
    prices = [
        value
        for value in (
            item.price_resident_kzt,
            item.price_nonresident_kzt,
            item.price_original,
        )
        if value is not None
    ]
    invalid_price = any(value <= 0 for value in prices)
    invalid_nonresident_price = (
        item.price_resident_kzt is not None
        and item.price_nonresident_kzt is not None
        and item.price_nonresident_kzt < item.price_resident_kzt
    )
    anomaly = bool(item.verification_note and "anomaly:" in item.verification_note)
    future_date = bool(item.verification_note and "price date is in the future" in item.verification_note)
    return item.service_id is None or not has_price or invalid_price or invalid_nonresident_price or anomaly or future_date


@router.get("/archives", response_model=ArchivesResponse)
def list_archives(db: Session = Depends(get_db)) -> ArchivesResponse:
    archives = list(
        db.scalars(
            select(ArchiveBatch).order_by(ArchiveBatch.uploaded_at.desc())
        ).all()
    )
    return ArchivesResponse(archives=archives)


@router.get("/archives/{archive_id}", response_model=ArchiveDetailOut)
def archive_detail(archive_id: str, db: Session = Depends(get_db)) -> ArchiveDetailOut:
    archive = db.get(ArchiveBatch, archive_id)
    if not archive:
        raise HTTPException(status_code=404, detail="Archive not found")

    documents_stmt = (
        select(PriceDocument, Partner)
        .join(Partner, Partner.partner_id == PriceDocument.partner_id)
        .where(PriceDocument.archive_id == archive.archive_id)
        .order_by(Partner.name, PriceDocument.effective_date.desc().nullslast(), PriceDocument.file_name)
    )
    rows = db.execute(documents_stmt).all()
    document_ids = [document.doc_id for document, _partner in rows]
    item_counts: dict[str, int] = {}
    if document_ids:
        counts_stmt = (
            select(PriceItem.doc_id, PriceItem.item_id)
            .where(PriceItem.doc_id.in_(document_ids))
        )
        for doc_id, _item_id in db.execute(counts_stmt).all():
            key = str(doc_id)
            item_counts[key] = item_counts.get(key, 0) + 1

    documents = [
        ArchiveDocumentOut(
            doc_id=document.doc_id,
            partner_id=partner.partner_id,
            partner_name=partner.name,
            file_name=document.file_name,
            file_base_name=Path(document.file_name).stem,
            source_path=document.source_path,
            source_label=_source_label(document),
            effective_date=document.effective_date,
            parse_status=document.parse_status,
            item_count=item_counts.get(str(document.doc_id), 0),
        )
        for document, partner in rows
    ]
    return ArchiveDetailOut(archive=ArchiveOut.model_validate(archive), documents=documents)


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/services", response_model=list[ServiceOut])
def list_services(
    category: str | None = None,
    db: Session = Depends(get_db),
) -> list[Service]:
    stmt = select(Service).where(Service.is_active.is_(True)).order_by(Service.service_name)
    if category:
        stmt = stmt.where(Service.category.ilike(f"%{category}%"))
    return list(db.scalars(stmt).all())


@router.get("/partners", response_model=list[PartnerOut])
def list_partners(
    city: str | None = None,
    is_active: bool | None = None,
    db: Session = Depends(get_db),
) -> list[Partner]:
    stmt = select(Partner).order_by(Partner.name)
    if city:
        stmt = stmt.where(Partner.city.ilike(f"%{city}%"))
    if is_active is not None:
        stmt = stmt.where(Partner.is_active.is_(is_active))
    return list(db.scalars(stmt).all())


@router.get("/documents", response_model=DocumentsResponse)
def list_documents(db: Session = Depends(get_db)) -> DocumentsResponse:
    stmt = (
        select(PriceDocument, Partner)
        .join(Partner, Partner.partner_id == PriceDocument.partner_id)
        .order_by(Partner.name, PriceDocument.effective_date.desc().nullslast(), PriceDocument.file_name)
    )
    rows = db.execute(stmt).all()
    if not rows:
        return DocumentsResponse(documents=[])
    document_ids = [document.doc_id for document, _partner in rows]
    items_stmt = (
        select(PriceItem)
        .where(PriceItem.doc_id.in_(document_ids))
        .order_by(PriceItem.service_name_raw)
    )
    items_by_doc: dict[str, list[DocumentItemOut]] = {}
    for item in db.scalars(items_stmt).all():
        items_by_doc.setdefault(str(item.doc_id), []).append(
            DocumentItemOut.model_validate(item)
        )

    documents = []
    for document, partner in rows:
        documents.append(
            DocumentGroupOut(
                doc_id=document.doc_id,
                partner_id=partner.partner_id,
                partner_name=partner.name,
                file_name=document.file_name,
                file_base_name=Path(document.file_name).stem,
                source_path=document.source_path,
                source_label=_source_label(document),
                effective_date=document.effective_date,
                parse_status=document.parse_status,
                items=items_by_doc.get(str(document.doc_id), []),
            )
    )
    return DocumentsResponse(documents=documents)


@router.post("/upload", response_model=UnifiedUploadResponse)
async def upload(file: UploadFile = File(...)) -> UnifiedUploadResponse:
    saved_path, content = await _save_upload(file)
    suffix = saved_path.suffix.lower()

    if suffix == ".zip":
        if not zipfile.is_zipfile(saved_path):
            _remove_path(str(saved_path))
            raise HTTPException(status_code=400, detail="Invalid ZIP archive")
        session = SessionLocal()
        try:
            stats = import_archive(session, saved_path)
        finally:
            session.close()
        return _archive_response(
            file_name=file.filename or saved_path.name,
            saved_path=saved_path,
            stats=stats,
        )

    if suffix not in {".pdf", ".docx", ".xlsx", ".xls"}:
        _remove_path(str(saved_path))
        raise HTTPException(status_code=400, detail="Unsupported file type")

    session = SessionLocal()
    try:
        stats, document = import_single_document(session, saved_path, content, original_name=file.filename)
        session.refresh(document)
    finally:
        session.close()

    return _document_response(
        file_name=file.filename or saved_path.name,
        saved_path=saved_path,
        stats=stats,
        document=document,
    )


@router.post("/documents/upload", response_model=UnifiedUploadResponse)
async def upload_document(file: UploadFile = File(...)) -> UnifiedUploadResponse:
    saved_path, content = await _save_upload(file)
    suffix = saved_path.suffix.lower()
    if suffix not in {".pdf", ".docx", ".xlsx", ".xls"}:
        _remove_path(str(saved_path))
        raise HTTPException(status_code=400, detail="Unsupported document type")

    session = SessionLocal()
    try:
        stats, document = import_single_document(session, saved_path, content, original_name=file.filename)
        session.refresh(document)
    finally:
        session.close()

    return _document_response(
        file_name=file.filename or saved_path.name,
        saved_path=saved_path,
        stats=stats,
        document=document,
    )


@router.get("/documents/{doc_id}", response_model=DocumentDetailOut)
def document_detail(doc_id: str, db: Session = Depends(get_db)) -> DocumentDetailOut:
    document_uuid = UUID(doc_id)
    stmt = (
        select(PriceDocument, Partner, ArchiveBatch)
        .join(Partner, Partner.partner_id == PriceDocument.partner_id)
        .join(ArchiveBatch, ArchiveBatch.archive_id == PriceDocument.archive_id, isouter=True)
        .where(PriceDocument.doc_id == document_uuid)
    )
    row = db.execute(stmt).first()
    if not row:
        raise HTTPException(status_code=404, detail="Document not found")
    document, partner, archive = row
    items = list(
        db.scalars(
            select(PriceItem)
            .where(PriceItem.doc_id == document.doc_id)
            .order_by(PriceItem.service_name_raw)
        ).all()
    )
    return DocumentDetailOut(
        document=PriceDocumentOut.model_validate(document),
        partner=PartnerOut.model_validate(partner),
        archive=ArchiveOut.model_validate(archive) if archive is not None else None,
        items=[PriceItemOut.model_validate(item) for item in items],
    )


@router.put("/documents/{doc_id}/review", response_model=DocumentReviewResponse)
def save_document_review(
    doc_id: str,
    payload: DocumentReviewRequest,
    db: Session = Depends(get_db),
) -> DocumentReviewResponse:
    document_uuid = UUID(doc_id)
    document = db.get(PriceDocument, document_uuid)
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")

    existing_items = {
        item.item_id: item
        for item in db.scalars(select(PriceItem).where(PriceItem.doc_id == document_uuid)).all()
    }
    for update in payload.items:
        item = existing_items.get(update.item_id)
        if item is None:
            raise HTTPException(status_code=404, detail=f"Price item not found: {update.item_id}")
        item.service_name_raw = update.service_name_raw.strip() or item.service_name_raw
        item.service_code_source = update.service_code_source.strip() if update.service_code_source else None
        item.price_resident_kzt = update.price_resident_kzt
        item.price_nonresident_kzt = update.price_nonresident_kzt
        item.price_original = update.price_original
        item.currency_original = update.currency_original if any(
            value is not None
            for value in (
                update.price_resident_kzt,
                update.price_nonresident_kzt,
                update.price_original,
            )
        ) else None
        item.is_verified = True
        item.verification_note = "manual verified"

    document.parse_status = "processed"
    if document.archive_id is not None:
        _recalculate_archive_totals(db, document.archive_id)
    db.commit()
    return DocumentReviewResponse(
        ok=True,
        doc_id=document.doc_id,
        status=document.parse_status,
        item_count=len(existing_items),
    )


@router.delete("/documents/{doc_id}", response_model=DeleteResponse)
def delete_document(doc_id: str, db: Session = Depends(get_db)) -> DeleteResponse:
    document_uuid = UUID(doc_id)
    document = db.get(PriceDocument, document_uuid)
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")

    archive_id = document.archive_id
    source_path = document.source_path
    item_count = db.scalar(
        select(func.count()).select_from(PriceItem).where(PriceItem.doc_id == document.doc_id)
    ) or 0
    db.query(PriceItem).filter(PriceItem.doc_id == document.doc_id).delete(synchronize_session=False)
    db.delete(document)
    if archive_id is not None:
        _recalculate_archive_totals(db, archive_id)
    db.commit()
    _remove_path(source_path)
    return DeleteResponse(ok=True, deleted_id=str(document_uuid), deleted_type="document")


@router.delete("/archives/{archive_id}", response_model=DeleteResponse)
def delete_archive(archive_id: str, db: Session = Depends(get_db)) -> DeleteResponse:
    archive_uuid = UUID(archive_id)
    archive = db.get(ArchiveBatch, archive_uuid)
    if not archive:
        raise HTTPException(status_code=404, detail="Archive not found")

    documents = list(
        db.scalars(select(PriceDocument).where(PriceDocument.archive_id == archive_uuid)).all()
    )
    for document in documents:
        db.query(PriceItem).filter(PriceItem.doc_id == document.doc_id).delete(synchronize_session=False)
        db.delete(document)
    db.delete(archive)
    db.commit()
    _remove_path(archive.saved_path)
    return DeleteResponse(ok=True, deleted_id=str(archive_uuid), deleted_type="archive")


@router.get("/services/{service_id}/partners", response_model=list[ServicePartnerOut])
def service_partners(service_id: str, db: Session = Depends(get_db)) -> list[dict]:
    service = db.get(Service, service_id)
    if not service:
        raise HTTPException(status_code=404, detail="Service not found")
    stmt = (
        select(PriceItem, Partner)
        .join(Partner, Partner.partner_id == PriceItem.partner_id)
        .where(PriceItem.service_id == service_id, PriceItem.is_active.is_(True))
        .order_by(Partner.name)
    )
    rows = db.execute(stmt).all()
    return [{"partner": partner, "price_item": price_item} for price_item, partner in rows]


@router.get("/partners/{partner_id}/services", response_model=list[PartnerServiceOut])
def partner_services(partner_id: str, db: Session = Depends(get_db)) -> list[dict]:
    try:
        partner_uuid = UUID(partner_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Partner not found")
    partner = db.get(Partner, partner_uuid)
    if not partner:
        raise HTTPException(status_code=404, detail="Partner not found")
    stmt = (
        select(PriceItem, Service)
        .join(Service, Service.service_id == PriceItem.service_id, isouter=True)
        .where(PriceItem.partner_id == partner_uuid, PriceItem.is_active.is_(True))
        .order_by(PriceItem.effective_date.desc().nullslast())
    )
    rows = db.execute(stmt).all()
    return [{"price_item": price_item, "service": service} for price_item, service in rows]


@router.get("/partners/{partner_id}", response_model=PartnerProfileOut)
def partner_profile(partner_id: str, db: Session = Depends(get_db)) -> PartnerProfileOut:
    try:
        partner_uuid = UUID(partner_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Partner not found")
    partner = db.get(Partner, partner_uuid)
    if not partner:
        raise HTTPException(status_code=404, detail="Partner not found")

    documents = list(
        db.scalars(
            select(PriceDocument)
            .where(PriceDocument.partner_id == partner_uuid)
            .order_by(PriceDocument.effective_date.desc().nullslast(), PriceDocument.file_name)
        ).all()
    )
    items = list(
        db.execute(
            select(PriceItem, Service)
            .join(Service, Service.service_id == PriceItem.service_id, isouter=True)
            .where(PriceItem.partner_id == partner_uuid, PriceItem.is_active.is_(True))
            .order_by(PriceItem.effective_date.desc().nullslast(), PriceItem.service_name_raw)
        ).all()
    )
    latest_effective_date = None
    for document in documents:
        if document.effective_date is not None:
            latest_effective_date = document.effective_date
            break
    document_groups = [
        DocumentGroupOut(
            doc_id=document.doc_id,
            partner_id=partner.partner_id,
            partner_name=partner.name,
            file_name=document.file_name,
            file_base_name=Path(document.file_name).stem,
            source_path=document.source_path,
            source_label=_source_label(document),
            effective_date=document.effective_date,
            parse_status=document.parse_status,
            items=[],
        )
        for document in documents
    ]
    return PartnerProfileOut(
        partner=PartnerOut.model_validate(partner),
        documents=document_groups,
        items=[{"price_item": price_item, "service": service} for price_item, service in items],
        latest_effective_date=latest_effective_date,
    )


@router.get("/search", response_model=SearchResponse)
def search(q: str = Query(min_length=1), db: Session = Depends(get_db)) -> SearchResponse:
    services = db.scalars(select(Service).where(Service.service_name.ilike(f"%{q}%"))).all()
    partners = db.scalars(select(Partner).where(Partner.name.ilike(f"%{q}%"))).all()
    return SearchResponse(services=services, partners=partners)


@router.get("/unmatched", response_model=list[PriceItemOut])
def unmatched(db: Session = Depends(get_db)) -> list[PriceItem]:
    stmt = (
        select(PriceItem)
        .where(
            PriceItem.service_id.is_(None),
            PriceItem.is_active.is_(True),
            PriceItem.is_verified.is_(False),
        )
        .order_by(PriceItem.effective_date.desc().nullslast())
    )
    return list(db.scalars(stmt).all())


@router.get("/verification-queue", response_model=list[PriceItemOut])
def verification_queue(db: Session = Depends(get_db)) -> list[PriceItem]:
    candidates = list(
        db.scalars(
            select(PriceItem)
            .where(
                PriceItem.is_active.is_(True),
                PriceItem.is_verified.is_(False),
            )
            .order_by(PriceItem.effective_date.desc().nullslast(), PriceItem.service_name_raw)
        ).all()
    )
    return [item for item in candidates if _item_needs_review(item)]


@router.post("/match", response_model=MatchResponse)
def match_item(payload: MatchRequest, db: Session = Depends(get_db)) -> MatchResponse:
    item = db.get(PriceItem, payload.item_id)
    if not item:
        raise HTTPException(status_code=404, detail="Price item not found")
    service = None
    if payload.service_id is not None:
        service = db.get(Service, payload.service_id)
        if not service:
            raise HTTPException(status_code=404, detail="Service not found")
    elif payload.create_service_name:
        service_name = payload.create_service_name.strip()
        if not service_name:
            raise HTTPException(status_code=400, detail="Service name is required")
        service = db.scalars(
            select(Service).where(func.lower(Service.service_name) == service_name.lower())
        ).first()
        if service is None:
            service = Service(
                service_name=service_name,
                category=payload.create_service_category,
                icd_code=payload.create_service_code,
                synonyms=[item.service_name_raw] if item.service_name_raw != service_name else [],
                is_active=True,
            )
            db.add(service)
            db.flush()
    else:
        raise HTTPException(status_code=400, detail="service_id or create_service_name is required")
    item.service_id = service.service_id
    item.is_verified = True
    item.verification_note = payload.verification_note or "manual matched"
    document = db.get(PriceDocument, item.doc_id)
    if document is not None and not _document_needs_review(db, document.doc_id):
        document.parse_status = "processed"
        if document.archive_id is not None:
            _recalculate_archive_totals(db, document.archive_id)
    db.commit()
    db.refresh(item)
    return MatchResponse(ok=True, item_id=item.item_id, service_id=service.service_id)


@router.post("/archive/upload", response_model=UnifiedUploadResponse)
async def upload_archive(file: UploadFile = File(...)) -> UnifiedUploadResponse:
    saved_path, content = await _save_upload(file)
    if saved_path.suffix.lower() != ".zip" or not zipfile.is_zipfile(saved_path):
        _remove_path(str(saved_path))
        raise HTTPException(status_code=400, detail="Only ZIP archives are supported")

    session = SessionLocal()
    try:
        stats = import_archive(session, saved_path)
    finally:
        session.close()

    return _archive_response(
        file_name=file.filename or saved_path.name,
        saved_path=saved_path,
        stats=stats,
    )
