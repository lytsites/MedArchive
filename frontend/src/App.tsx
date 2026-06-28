import { type FormEvent, type ReactNode, useEffect, useMemo, useState } from 'react'

type RouteState =
  | { page: 'dashboard' }
  | { page: 'admin' }
  | { page: 'search' }
  | { page: 'partner'; id: string }
  | { page: 'document'; id: string }
  | { page: 'archive'; id: string }

type Service = {
  service_id: string
  service_name: string
  category: string | null
  icd_code: string | null
}

type Partner = {
  partner_id: string
  name: string
  city: string | null
  address: string | null
  bin: string | null
  contact_email: string | null
  contact_phone: string | null
  is_active: boolean
  created_at: string
  updated_at: string
}

type PriceItem = {
  item_id: string
  doc_id: string
  partner_id: string
  service_name_raw: string
  service_code_source: string | null
  service_id: string | null
  price_resident_kzt: number | null
  price_nonresident_kzt: number | null
  price_original: number | null
  currency_original: string | null
  is_verified: boolean
  verification_note: string | null
  effective_date: string | null
  is_active: boolean
}

type Archive = {
  archive_id: string
  file_name: string
  saved_path: string
  status: string
  partner_count: number
  document_count: number
  item_count: number
  matched_item_count: number
  warnings: string[] | null
  uploaded_at: string
  processed_at: string | null
}

type DocumentGroup = {
  doc_id: string
  partner_id: string
  partner_name: string
  file_name: string
  file_base_name: string
  source_path: string | null
  source_label: string
  effective_date: string | null
  parse_status: string
  items: Array<{
    item_id: string
    service_name_raw: string
    service_code_source: string | null
    price_original: number | null
    currency_original: string | null
    is_verified: boolean
    verification_note: string | null
  }>
}

type DocumentsResponse = { documents: DocumentGroup[] }
type ArchivesResponse = { archives: Archive[] }
type SearchResponse = { services: Service[]; partners: Partner[] }
type UnmatchedResponse = PriceItem[]
type VerificationQueueResponse = PriceItem[]
type ServicePartnerItem = {
  partner: Partner
  price_item: PriceItem
}
type PartnerProfile = {
  partner: Partner
  documents: Array<{
    doc_id: string
    partner_id: string
    partner_name: string
    file_name: string
    file_base_name: string
    source_label: string
    effective_date: string | null
    parse_status: string
    items: unknown[]
  }>
  items: Array<{
    price_item: PriceItem
    service: Service | null
  }>
  latest_effective_date: string | null
}
type DocumentDetail = {
  document: {
    doc_id: string
    partner_id: string
    file_name: string
    source_path: string | null
    file_format: string
    effective_date: string | null
    parsed_at: string | null
    parse_status: string
    parse_log: string | null
    raw_content: string | null
  }
  partner: Partner
  archive: Archive | null
  items: PriceItem[]
}
type ArchiveDetail = {
  archive: Archive
  documents: Array<{
    doc_id: string
    partner_id: string
    partner_name: string
    file_name: string
    file_base_name: string
    source_path: string | null
    source_label: string
    effective_date: string | null
    parse_status: string
    item_count: number
  }>
}
type UnifiedUploadResponse = {
  ok: boolean
  upload_type: 'archive' | 'document'
  file_name: string
  saved_path: string
  status: string
  archive_id: string | null
  doc_id: string | null
  partner_id: string | null
  partner_name: string | null
  partner_count: number | null
  document_count: number | null
  item_count: number | null
  matched_item_count: number | null
  warnings: string[]
}
type DeleteResponse = {
  ok: boolean
  deleted_id: string
  deleted_type: string
}
type MatchResponse = {
  ok: boolean
  item_id: string
  service_id: string
}
type PendingUpload = {
  id: string
  file_name: string
  upload_type: 'archive' | 'document'
  source_label: string
  status: 'loading' | 'failed'
  message: string | null
}
type ReviewItemDraft = {
  item_id: string
  service_name_raw: string
  service_code_source: string
  price_resident_kzt: string
  price_nonresident_kzt: string
  price_original: string
  currency_original: string
}

const apiBase = (import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000').replace(/\/$/, '')

async function apiGet<T>(path: string): Promise<T> {
  const response = await fetch(`${apiBase}${path}`)
  if (!response.ok) {
    throw new Error(`Request failed: ${response.status}`)
  }
  return response.json() as Promise<T>
}

async function apiDelete<T>(path: string): Promise<T> {
  const response = await fetch(`${apiBase}${path}`, { method: 'DELETE' })
  if (!response.ok) {
    throw new Error(`Request failed: ${response.status}`)
  }
  return response.json() as Promise<T>
}

async function apiPut<T>(path: string, body: unknown): Promise<T> {
  const response = await fetch(`${apiBase}${path}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  if (!response.ok) {
    throw new Error(`Request failed: ${response.status}`)
  }
  return response.json() as Promise<T>
}

async function apiPost<T>(path: string, body: unknown): Promise<T> {
  const response = await fetch(`${apiBase}${path}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  if (!response.ok) {
    throw new Error(`Request failed: ${response.status}`)
  }
  return response.json() as Promise<T>
}

function navigate(href: string) {
  window.history.pushState({}, '', href)
  window.dispatchEvent(new PopStateEvent('popstate'))
}

function parseRoute(): RouteState {
  const path = window.location.pathname.replace(/\/+$/, '') || '/'
  if (path === '/' || path === '/dashboard') return { page: 'dashboard' }
  if (path === '/admin') return { page: 'admin' }
  if (path === '/search') return { page: 'search' }
  if (path.startsWith('/partners/')) return { page: 'partner', id: path.slice('/partners/'.length) }
  if (path.startsWith('/documents/')) return { page: 'document', id: path.slice('/documents/'.length) }
  if (path.startsWith('/archives/')) return { page: 'archive', id: path.slice('/archives/'.length) }
  return { page: 'dashboard' }
}

function formatMoney(value: number | null) {
  if (value == null) return '—'
  return new Intl.NumberFormat('ru-KZ', { maximumFractionDigits: 2 }).format(value)
}

function formatPriceCell(item: { price_resident_kzt: number | null; price_nonresident_kzt: number | null; price_original: number | null; currency_original: string | null }) {
  if (item.price_resident_kzt != null || item.price_nonresident_kzt != null) {
    return {
      resident: item.price_resident_kzt != null ? `${formatMoney(item.price_resident_kzt)} KZT` : '—',
      nonresident: item.price_nonresident_kzt != null ? `${formatMoney(item.price_nonresident_kzt)} KZT` : '—',
      original: item.price_original != null ? `${formatMoney(item.price_original)} ${item.currency_original ?? ''}`.trim() : '—',
    }
  }
  return {
    resident: '—',
    nonresident: '—',
    original: item.price_original != null ? `${formatMoney(item.price_original)} ${item.currency_original ?? ''}`.trim() : '—',
  }
}

function formatDocumentLabel(fileName: string, sourceLabel: string) {
  return `${fileName.replace(/\.[^.]+$/, '')} (${sourceLabel})`
}

function displayDocumentName(fileName: string, fallback?: string | null) {
  if (!fileName) return fallback ?? '—'
  const baseName = fileName.replace(/\.[^.]+$/, '')
  if (/^[0-9a-f-]{12,}$/i.test(baseName)) {
    return fallback ?? fileName
  }
  return baseName
}

function sourceLabelFromFileName(fileName: string) {
  const extension = fileName.split('.').pop()?.toLowerCase() ?? ''
  if (extension === 'docx') return 'WORD'
  if (extension === 'xls' || extension === 'xlsx') return 'EXCEL'
  if (extension === 'pdf') return 'PDF'
  if (extension === 'zip') return 'ZIP'
  return extension.toUpperCase() || 'FILE'
}

function resolvedDocumentName(fileName: string, fallback?: string | null, docId?: string) {
  const normalizeStem = (value: string | null | undefined) => {
    if (!value) return null
    const trimmed = value.trim()
    if (!trimmed) return null
    const leaf = trimmed.split(/[\\/]/).pop() ?? trimmed
    return leaf.replace(/\.[^.]+$/, '')
  }
  const isInternal = (value: string | null | undefined) => {
    const stem = normalizeStem(value)
    if (!stem) return true
    if (/^[0-9a-f-]{12,}$/i.test(stem)) return true
    if (stem.toLowerCase() === 'upload') return true
    return false
  }
  const fileStem = normalizeStem(fileName)
  if (fileStem && !isInternal(fileStem)) return fileStem
  const fallbackStem = normalizeStem(fallback)
  if (fallbackStem && !isInternal(fallbackStem)) return fallbackStem
  if (docId) return shortId(docId)
  return fileStem ?? fallbackStem ?? 'Файл'
}

function statusLabel(status: string) {
  switch (status) {
    case 'processed':
      return 'обработан'
    case 'needs_review':
      return 'требует проверки'
    case 'processing':
      return 'обрабатывается'
    case 'pending':
      return 'в очереди'
    case 'partial':
      return 'частично разобран'
    case 'error':
      return 'ошибка'
    case 'failed':
      return 'ошибка'
    case 'loading':
      return 'загрузка'
    default:
      return status || 'неизвестно'
  }
}

function statusClassName(status: string) {
  if (status === 'processed') return 'status-badge ok'
  if (status === 'needs_review' || status === 'error' || status === 'failed') return 'status-badge error'
  return 'status-badge'
}

function documentFormatKey(fileName: string, fileFormat?: string) {
  const extension = (fileFormat || fileName.split('.').pop() || '').toLowerCase()
  if (extension === 'xlsx') return 'xlsx'
  if (extension === 'xls') return 'xls'
  if (extension === 'docx') return 'docx'
  if (extension === 'pdf') return 'pdf'
  if (extension === 'zip') return 'zip'
  return 'file'
}

function shortId(value: string, size = 12) {
  if (value.length <= size * 2) return value
  return `${value.slice(0, size)}…${value.slice(-size)}`
}

function iconStroke() {
  return {
    fill: 'none',
    stroke: 'currentColor',
    strokeWidth: 1.8,
    strokeLinecap: 'round' as const,
    strokeLinejoin: 'round' as const,
  }
}

function ArrowLeftIcon() {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true">
      <path {...iconStroke()} d="M19 12H5m6-6-6 6 6 6" />
    </svg>
  )
}

function FolderIcon() {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true">
      <path {...iconStroke()} d="M3 7.5A2.5 2.5 0 0 1 5.5 5H10l2 2h6.5A2.5 2.5 0 0 1 21 9.5v8A2.5 2.5 0 0 1 18.5 20h-13A2.5 2.5 0 0 1 3 17.5z" />
    </svg>
  )
}

function PathIcon() {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true">
      <path {...iconStroke()} d="M6 7h8a3 3 0 1 1 0 6H9a3 3 0 1 0 0 6h9" />
      <path {...iconStroke()} d="M8 5 5 8l3 3" />
    </svg>
  )
}

function DatabaseIcon() {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true">
      <ellipse {...iconStroke()} cx="12" cy="6.5" rx="7" ry="3.5" />
      <path {...iconStroke()} d="M5 6.5v5c0 1.93 3.13 3.5 7 3.5s7-1.57 7-3.5v-5" />
      <path {...iconStroke()} d="M5 11.5v5c0 1.93 3.13 3.5 7 3.5s7-1.57 7-3.5v-5" />
    </svg>
  )
}

function CalendarIcon() {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true">
      <rect {...iconStroke()} x="3.5" y="5.5" width="17" height="15" rx="2.5" />
      <path {...iconStroke()} d="M7.5 3.5v4M16.5 3.5v4M3.5 9.5h17" />
    </svg>
  )
}

function BuildingIcon() {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true">
      <path {...iconStroke()} d="M4.5 20.5h15M6.5 20.5V6.5l5.5-3 5.5 3v14" />
      <path {...iconStroke()} d="M9 10h.01M12 10h.01M15 10h.01M9 14h.01M12 14h.01M15 14h.01" />
    </svg>
  )
}

function HomeIcon() {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true">
      <path {...iconStroke()} d="M4.5 10.5 12 4l7.5 6.5v8a2 2 0 0 1-2 2h-3.5v-6h-4v6H6.5a2 2 0 0 1-2-2z" />
    </svg>
  )
}

function SearchIcon() {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true">
      <circle {...iconStroke()} cx="11" cy="11" r="6.5" />
      <path {...iconStroke()} d="m16 16 4 4" />
    </svg>
  )
}

function ShieldIcon() {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true">
      <path {...iconStroke()} d="M12 3.5 5.5 6v5.6c0 4.2 2.7 7.9 6.5 9 3.8-1.1 6.5-4.8 6.5-9V6z" />
      <path {...iconStroke()} d="M12 8v7M8.8 11.2 12 8l3.2 3.2" />
    </svg>
  )
}

function UploadIcon() {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true">
      <path {...iconStroke()} d="M12 15.5v-9" />
      <path {...iconStroke()} d="m8.5 9 3.5-3.5L15.5 9" />
      <path {...iconStroke()} d="M5.5 16.5v2a2 2 0 0 0 2 2h9a2 2 0 0 0 2-2v-2" />
    </svg>
  )
}

function ExternalLinkIcon() {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true">
      <path {...iconStroke()} d="M14 5.5h4.5V10" />
      <path {...iconStroke()} d="M10 14 18.5 5.5" />
      <path {...iconStroke()} d="M18.5 13v4a1.5 1.5 0 0 1-1.5 1.5h-10A1.5 1.5 0 0 1 5.5 17V7A1.5 1.5 0 0 1 7 5.5h4" />
    </svg>
  )
}

function TrashIcon() {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true">
      <path {...iconStroke()} d="M4.5 7.5h15" />
      <path {...iconStroke()} d="M9.5 3.5h5l1 2h-7z" />
      <path {...iconStroke()} d="M7.5 7.5v10a2 2 0 0 0 2 2h5a2 2 0 0 0 2-2v-10" />
      <path {...iconStroke()} d="M10 10.5v5M14 10.5v5" />
    </svg>
  )
}

function CheckCircleIcon() {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true">
      <circle {...iconStroke()} cx="12" cy="12" r="8.5" />
      <path {...iconStroke()} d="m8.5 12.5 2.3 2.3 4.7-5.1" />
    </svg>
  )
}

function AlertCircleIcon() {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true">
      <circle {...iconStroke()} cx="12" cy="12" r="8.5" />
      <path {...iconStroke()} d="M12 8.2v5.2M12 16.8h.01" />
    </svg>
  )
}

function FileTypeIcon({ fileName, fileFormat }: { fileName: string; fileFormat?: string }) {
  const formatKey = documentFormatKey(fileName, fileFormat)
  const iconClass =
    formatKey === 'docx'
      ? 'docx'
      : formatKey === 'pdf'
        ? 'pdf'
        : formatKey === 'zip'
          ? 'zip'
          : formatKey === 'xlsx'
            ? 'xlsx'
            : formatKey === 'xls'
              ? 'xls'
              : 'blank'
  return (
    <div className={`doc-file-icon ${formatKey}`} aria-hidden="true">
      <span className={`fiv-viv fiv-size-xl fiv-icon-${iconClass}`} />
    </div>
  )
}

function ReviewState({ item }: { item: PriceItem }) {
  const needsReview = itemNeedsReview(item)
  const label = needsReview ? itemReviewReason(item) : item.verification_note ?? 'совпадение подтверждено'
  return (
    <div className={`review-state ${needsReview ? 'warn' : 'ok'}`}>
      <span className="review-state-icon">{needsReview ? <AlertCircleIcon /> : <CheckCircleIcon />}</span>
      <span>{label}</span>
    </div>
  )
}

function DocumentCell({
  fileName,
  sourcePath,
  docId,
  sourceLabel,
  compact = false,
}: {
  fileName: string
  sourcePath?: string | null
  docId?: string
  sourceLabel: string
  compact?: boolean
}) {
  return (
    <div className={compact ? 'document-cell compact' : 'document-cell'}>
      <FileTypeIcon fileName={fileName} fileFormat={fileName.split('.').pop() ?? undefined} />
      <div className="document-cell-copy">
        <div className="document-cell-title">{resolvedDocumentName(fileName, sourcePath, docId)}</div>
        <div className="document-cell-subtitle">{sourceLabel}</div>
      </div>
    </div>
  )
}

function pendingId() {
  if ('crypto' in window && typeof window.crypto.randomUUID === 'function') {
    return window.crypto.randomUUID()
  }
  return `${Date.now()}-${Math.random().toString(16).slice(2)}`
}

function itemNeedsReview(item: PriceItem) {
  const flags = itemValidationFlags(item)
  const anomaly = Boolean(item.verification_note && item.verification_note.includes('anomaly:'))
  const futureDate = Boolean(item.verification_note && item.verification_note.includes('price date is in the future'))
  return !item.is_verified && (item.service_id == null || flags.rowPriceInvalid || flags.nonresidentLowerThanResident || anomaly || futureDate)
}

function itemValidationFlags(item: PriceItem) {
  const hasPrice =
    item.price_resident_kzt != null ||
    item.price_nonresident_kzt != null ||
    item.price_original != null
  const prices = [item.price_resident_kzt, item.price_nonresident_kzt, item.price_original].filter(
    (value): value is number => value != null,
  )
  const rowPriceInvalid = !hasPrice || prices.some((value) => value <= 0)
  const nonresidentLowerThanResident =
    item.price_resident_kzt != null &&
    item.price_nonresident_kzt != null &&
    item.price_nonresident_kzt < item.price_resident_kzt
  return {
    missingServiceName: !item.service_name_raw.trim(),
    rowPriceInvalid,
    nonresidentLowerThanResident,
    residentFieldInvalid: item.price_resident_kzt != null ? item.price_resident_kzt <= 0 : !hasPrice,
    nonresidentFieldInvalid:
      item.price_nonresident_kzt != null
        ? item.price_nonresident_kzt <= 0 || nonresidentLowerThanResident
        : false,
    originalFieldInvalid: item.price_original != null ? item.price_original <= 0 : !hasPrice,
  }
}

function itemReviewReason(item: PriceItem) {
  const flags = itemValidationFlags(item)
  if (flags.missingServiceName) return 'пустое название услуги'
  if (flags.rowPriceInvalid) return 'цена должна быть числом и больше нуля'
  if (flags.nonresidentLowerThanResident) return 'цена нерезидента ниже цены резидента'
  if (item.verification_note && item.verification_note.includes('price date is in the future')) {
    return 'дата прайса в будущем'
  }
  if (item.verification_note && item.verification_note.includes('anomaly:')) {
    return 'аномальное изменение цены'
  }
  if (item.service_id == null) return 'нужно сопоставить со справочником'
  return item.verification_note ?? 'проверить'
}

function formatInputValue(value: number | null) {
  return value == null ? '' : String(value)
}

function parseInputNumber(value: string) {
  const cleaned = value.replace(/\s+/g, '').replace(',', '.')
  if (!cleaned) return null
  const parsed = Number(cleaned)
  return Number.isFinite(parsed) ? parsed : null
}

function pageTitle(route: RouteState) {
  switch (route.page) {
    case 'admin':
      return 'Админ-раздел'
    case 'search':
      return 'Поиск услуги'
    case 'partner':
      return 'Страница партнёра'
    case 'document':
      return 'Документ'
    case 'archive':
      return 'Архив'
    default:
      return 'Дашборд'
  }
}

function NavLink({
  href,
  active,
  icon,
  children,
}: {
  href: string
  active: boolean
  icon?: ReactNode
  children: ReactNode
}) {
  return (
    <a
      className={active ? 'nav-link active' : 'nav-link'}
      href={href}
      onClick={(event) => {
        event.preventDefault()
        navigate(href)
      }}
    >
      {icon ? <span className="nav-link-icon">{icon}</span> : null}
      {children}
    </a>
  )
}

function useAppData(route: RouteState, searchQuery: string) {
  const [services, setServices] = useState<Service[]>([])
  const [archives, setArchives] = useState<Archive[]>([])
  const [documents, setDocuments] = useState<DocumentGroup[]>([])
  const [unmatched, setUnmatched] = useState<PriceItem[]>([])
  const [verificationQueue, setVerificationQueue] = useState<PriceItem[]>([])
  const [searchResponse, setSearchResponse] = useState<SearchResponse | null>(null)
  const [searchLoading, setSearchLoading] = useState(false)
  const [searchError, setSearchError] = useState<string | null>(null)
  const [partnerProfile, setPartnerProfile] = useState<PartnerProfile | null>(null)
  const [documentDetail, setDocumentDetail] = useState<DocumentDetail | null>(null)
  const [archiveDetail, setArchiveDetail] = useState<ArchiveDetail | null>(null)

  const loadLists = async () => {
    const [servicesData, unmatchedData, verificationQueueData, archivesData, documentsData] = await Promise.all([
      apiGet<Service[]>('/services'),
      apiGet<UnmatchedResponse>('/unmatched'),
      apiGet<VerificationQueueResponse>('/verification-queue'),
      apiGet<ArchivesResponse>('/archives'),
      apiGet<DocumentsResponse>('/documents'),
    ])
    setServices(servicesData)
    setUnmatched(unmatchedData)
    setVerificationQueue(verificationQueueData)
    setArchives(archivesData.archives)
    setDocuments(documentsData.documents)
  }

  useEffect(() => {
    void loadLists().catch((error) => console.error(error))
  }, [])

  useEffect(() => {
    if (route.page !== 'search') return
    setSearchLoading(true)
    setSearchError(null)
    void apiGet<SearchResponse>(`/search?q=${encodeURIComponent(searchQuery)}`)
      .then(setSearchResponse)
      .catch((error) => setSearchError(error instanceof Error ? error.message : 'Search failed'))
      .finally(() => setSearchLoading(false))
  }, [route.page])

  useEffect(() => {
    if (route.page !== 'partner') return
    void apiGet<PartnerProfile>(`/partners/${route.id}`)
      .then(setPartnerProfile)
      .catch((error) => console.error(error))
  }, [route.page, route.id])

  useEffect(() => {
    if (route.page !== 'document') return
    void apiGet<DocumentDetail>(`/documents/${route.id}`)
      .then(setDocumentDetail)
      .catch((error) => console.error(error))
  }, [route.page, route.id])

  useEffect(() => {
    if (route.page !== 'archive') return
    void apiGet<ArchiveDetail>(`/archives/${route.id}`)
      .then(setArchiveDetail)
      .catch((error) => console.error(error))
  }, [route.page, route.id])

  return {
    services,
    archives,
    documents,
    unmatched,
    verificationQueue,
    searchResponse,
    searchLoading,
    searchError,
    partnerProfile,
    documentDetail,
    archiveDetail,
    reloadLists: loadLists,
    setSearchResponse,
    setSearchError,
    setSearchLoading,
    setDocumentDetail,
  }
}

function AppBody() {
  const [route, setRoute] = useState<RouteState>(parseRoute())
  const [searchQuery, setSearchQuery] = useState('Клиника')
  const [selectedServiceId, setSelectedServiceId] = useState<string | null>(null)
  const [servicePartners, setServicePartners] = useState<ServicePartnerItem[]>([])
  const [servicePartnersLoading, setServicePartnersLoading] = useState(false)
  const [uploadFile, setUploadFile] = useState<File | null>(null)
  const [uploadInputKey, setUploadInputKey] = useState(0)
  const [pendingUploads, setPendingUploads] = useState<PendingUpload[]>([])
  const [uploadResult, setUploadResult] = useState<UnifiedUploadResponse | null>(null)
  const [uploadError, setUploadError] = useState<string | null>(null)
  const [reviewDrafts, setReviewDrafts] = useState<ReviewItemDraft[]>([])
  const [acknowledgedFields, setAcknowledgedFields] = useState<Set<string>>(new Set())
  const [reviewSaving, setReviewSaving] = useState(false)
  const [reviewError, setReviewError] = useState<string | null>(null)

  useEffect(() => {
    const onLocation = () => setRoute(parseRoute())
    window.addEventListener('popstate', onLocation)
    return () => window.removeEventListener('popstate', onLocation)
  }, [])

  const {
    services,
    archives,
    documents,
    unmatched,
    verificationQueue,
    searchResponse,
    searchLoading,
    searchError,
    partnerProfile,
    documentDetail,
    archiveDetail,
    reloadLists,
    setSearchResponse,
    setSearchError,
    setSearchLoading,
    setDocumentDetail,
  } = useAppData(route, searchQuery)
  const reviewMode = route.page === 'document' && documentDetail?.document.parse_status === 'needs_review'

  const dashboardStats = useMemo(() => {
    const totalItems = archives.reduce((sum, archive) => sum + archive.item_count, 0)
    const matchedItems = archives.reduce((sum, archive) => sum + archive.matched_item_count, 0)
    return {
      documentsCount: documents.length,
      normalization: totalItems > 0 ? Math.round((matchedItems / totalItems) * 100) : 0,
      queue: verificationQueue.length,
      archivesCount: archives.length,
    }
  }, [archives, documents.length, verificationQueue.length])

  const reviewDocumentsQueue = useMemo(() => {
    const documentMap = new Map(
      documents.map((document) => [
        document.doc_id,
        {
          doc_id: document.doc_id,
          file_name: document.file_name,
          source_label: document.source_label,
          partner_name: document.partner_name,
        },
      ]),
    )

    const queueMap = new Map<string, {
      doc_id: string
      file_name: string
      source_label: string
      partner_name: string
      issues_count: number
    }>()

    for (const item of verificationQueue) {
      const document = documentMap.get(item.doc_id)
      if (!document) continue
      const current = queueMap.get(item.doc_id)
      if (current) {
        current.issues_count += 1
        continue
      }
      queueMap.set(item.doc_id, {
        ...document,
        issues_count: 1,
      })
    }

    return Array.from(queueMap.values()).sort((left, right) => right.issues_count - left.issues_count)
  }, [documents, verificationQueue])

  useEffect(() => {
    if (!documentDetail) return
    setReviewDrafts(
      documentDetail.items.map((item) => ({
        item_id: item.item_id,
        service_name_raw: item.service_name_raw,
        service_code_source: item.service_code_source ?? '',
        price_resident_kzt: formatInputValue(item.price_resident_kzt),
        price_nonresident_kzt: formatInputValue(item.price_nonresident_kzt),
        price_original: formatInputValue(item.price_original),
        currency_original: item.currency_original ?? 'KZT',
      })),
    )
    setAcknowledgedFields(new Set())
    setReviewError(null)
  }, [documentDetail?.document.doc_id])

  const openService = async (service: Service) => {
    setSelectedServiceId(service.service_id)
    setServicePartnersLoading(true)
    try {
      const data = await apiGet<ServicePartnerItem[]>(`/services/${service.service_id}/partners`)
      setServicePartners(data)
    } catch (error) {
      console.error(error)
      setServicePartners([])
    } finally {
      setServicePartnersLoading(false)
    }
  }

  const runSearch = async (event?: FormEvent) => {
    event?.preventDefault()
    setSearchLoading(true)
    setSearchError(null)
    try {
      const data = await apiGet<SearchResponse>(`/search?q=${encodeURIComponent(searchQuery)}`)
      setSearchResponse(data)
    } catch (error) {
      setSearchError(error instanceof Error ? error.message : 'Search failed')
    } finally {
      setSearchLoading(false)
    }
  }

  const handleUpload = async (event: FormEvent) => {
    event.preventDefault()
    if (!uploadFile) return
    const fileToUpload = uploadFile
    const extension = fileToUpload.name.split('.').pop()?.toLowerCase() ?? ''
    const uploadType = extension === 'zip' ? 'archive' : 'document'
    const id = pendingId()
    setPendingUploads((current) => [
      {
        id,
        file_name: fileToUpload.name,
        upload_type: uploadType,
        source_label: sourceLabelFromFileName(fileToUpload.name),
        status: 'loading',
        message: null,
      },
      ...current,
    ])
    setUploadFile(null)
    setUploadInputKey((current) => current + 1)
    setUploadError(null)
    try {
      const formData = new FormData()
      formData.append('file', fileToUpload)
      const response = await fetch(`${apiBase}/upload`, {
        method: 'POST',
        body: formData,
      })
      if (!response.ok) {
        throw new Error(`Upload failed: ${response.status}`)
      }
      const data = (await response.json()) as UnifiedUploadResponse
      setUploadResult(data)
      setPendingUploads((current) => current.filter((upload) => upload.id !== id))
      await reloadLists()
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Upload failed'
      setUploadError(message)
      setPendingUploads((current) =>
        current.map((upload) =>
          upload.id === id ? { ...upload, status: 'failed', message } : upload,
        ),
      )
    }
  }

  const deleteDocument = async (docId: string) => {
    if (!window.confirm('Удалить файл вместе с данными?')) return
    try {
      await apiDelete<DeleteResponse>(`/documents/${docId}`)
      await reloadLists()
      if (route.page === 'document' && route.id === docId) {
        navigate('/admin')
      }
    } catch (error) {
      window.alert(error instanceof Error ? error.message : 'Не удалось удалить файл')
    }
  }

  const deleteArchive = async (archiveId: string) => {
    if (!window.confirm('Удалить архив и все связанные документы?')) return
    try {
      await apiDelete<DeleteResponse>(`/archives/${archiveId}`)
      await reloadLists()
      if (route.page === 'archive' && route.id === archiveId) {
        navigate('/admin')
      }
    } catch (error) {
      window.alert(error instanceof Error ? error.message : 'Не удалось удалить архив')
    }
  }

  const updateReviewDraft = (itemId: string, field: keyof ReviewItemDraft, value: string) => {
    setReviewDrafts((current) =>
      current.map((draft) =>
        draft.item_id === itemId ? { ...draft, [field]: value } : draft,
      ),
    )
  }

  const acknowledgeField = (itemId: string, field: keyof ReviewItemDraft) => {
    setAcknowledgedFields((current) => {
      const next = new Set(current)
      next.add(`${itemId}:${field}`)
      return next
    })
  }

  const reviewInputClass = (item: PriceItem, field: keyof ReviewItemDraft) => {
    const acknowledged = acknowledgedFields.has(`${item.item_id}:${field}`)
    if (!itemNeedsReview(item) || acknowledged) return 'review-input'
    const flags = itemValidationFlags(item)
    if (field === 'service_name_raw') {
      return flags.missingServiceName ? 'review-input needs-review' : 'review-input'
    }
    if (field === 'service_code_source') {
      return 'review-input'
    }
    if (field === 'price_resident_kzt') {
      return flags.residentFieldInvalid ? 'review-input needs-review' : 'review-input'
    }
    if (field === 'price_nonresident_kzt') {
      return flags.nonresidentFieldInvalid ? 'review-input needs-review' : 'review-input'
    }
    if (field === 'price_original') {
      return flags.originalFieldInvalid ? 'review-input needs-review' : 'review-input'
    }
    return 'review-input'
  }

  const saveReview = async () => {
    if (!documentDetail) return
    setReviewSaving(true)
    setReviewError(null)
    try {
      await apiPut(`/documents/${documentDetail.document.doc_id}/review`, {
        items: reviewDrafts.map((draft) => ({
          item_id: draft.item_id,
          service_name_raw: draft.service_name_raw,
          service_code_source: draft.service_code_source || null,
          price_resident_kzt: parseInputNumber(draft.price_resident_kzt),
          price_nonresident_kzt: parseInputNumber(draft.price_nonresident_kzt),
          price_original: parseInputNumber(draft.price_original),
          currency_original: draft.currency_original || 'KZT',
        })),
      })
      const [freshDocument] = await Promise.all([
        apiGet<DocumentDetail>(`/documents/${documentDetail.document.doc_id}`),
        reloadLists(),
      ])
      setDocumentDetail(freshDocument)
    } catch (error) {
      setReviewError(error instanceof Error ? error.message : 'Не удалось сохранить проверку')
    } finally {
      setReviewSaving(false)
    }
  }


  if (reviewMode && documentDetail) {
    const metaItems: Array<{ label: string; value: ReactNode; icon: ReactNode }> = [
      { label: 'Архив', value: documentDetail.archive?.file_name ?? '—', icon: <FolderIcon /> },
      { label: 'Путь', value: documentDetail.document.source_path ?? '—', icon: <PathIcon /> },
      { label: 'Файл в БД', value: documentDetail.document.doc_id, icon: <DatabaseIcon /> },
      { label: 'Партнер', value: documentDetail.partner.name, icon: <BuildingIcon /> },
      { label: 'Дата прайса', value: documentDetail.document.effective_date ?? '—', icon: <CalendarIcon /> },
    ]

    return (
      <div className="review-shell">
        <div className="review-page">
          <div className="review-topbar">
            <button type="button" className="back-button" onClick={() => navigate('/admin')}>
              <ArrowLeftIcon />
              <span>Назад</span>
            </button>
          </div>

          <section className="stack">
            <article className="panel review-panel review-hero">
              <div className="review-hero-main">
                <FileTypeIcon fileName={documentDetail.document.file_name} fileFormat={documentDetail.document.file_format} />
                <div className="review-hero-copy">
                  <h1 className="review-title">
                    {resolvedDocumentName(documentDetail.document.file_name, documentDetail.document.source_path, documentDetail.document.doc_id)}
                  </h1>
                  <div className="review-hero-pills">
                    <span className="chip review-chip review-chip-format">{documentDetail.document.file_format.toUpperCase()}</span>
                    <span className={`chip review-chip ${statusClassName(documentDetail.document.parse_status)}`}>
                      {statusLabel(documentDetail.document.parse_status)}
                    </span>
                    <span className="chip review-chip review-chip-muted">
                      {resolvedDocumentName(documentDetail.document.file_name, documentDetail.document.source_path, documentDetail.document.doc_id)}
                    </span>
                    <button
                      type="button"
                      className="review-icon-button"
                      onClick={() => void deleteDocument(documentDetail.document.doc_id)}
                      aria-label="Удалить файл"
                      title="Удалить файл"
                    >
                      <TrashIcon />
                    </button>
                  </div>
                </div>
              </div>
              <div className="review-meta-card">
                {metaItems.map((item) => (
                  <div className="review-meta-row" key={item.label}>
                    <span className="review-meta-icon">{item.icon}</span>
                    <span className="review-meta-label">{item.label}:</span>
                    <span className="review-meta-value">{item.value}</span>
                  </div>
                ))}
              </div>
            </article>

            {documentDetail.document.parse_log && (
              <article className="panel review-panel">
                <div className="section-head">
                  <h2>Лог разбора</h2>
                </div>
                <pre className="raw-text">{documentDetail.document.parse_log}</pre>
              </article>
            )}

            <article className="panel review-panel">
              <div className="section-head">
                <h2>Проверка строк</h2>
              </div>
              <div className="table-wrap review-table-wrap">
                <table className="review-table">
                  <thead>
                    <tr>
                      <th>#</th>
                      <th>Услуга</th>
                      <th>Код</th>
                      <th>Резидент</th>
                      <th>Нерезидент</th>
                      <th>Оригинал</th>
                      <th>Проверка</th>
                    </tr>
                  </thead>
                  <tbody>
                    {documentDetail.items.map((item, index) => {
                      const draft = reviewDrafts.find((entry) => entry.item_id === item.item_id)
                      if (!draft) return null
                      return (
                        <tr key={item.item_id} className={itemNeedsReview(item) ? 'review-row' : undefined}>
                          <td>{index + 1}</td>
                          <td>
                            <input
                              className={reviewInputClass(item, 'service_name_raw')}
                              value={draft.service_name_raw}
                              onFocus={() => acknowledgeField(item.item_id, 'service_name_raw')}
                              onChange={(event) => updateReviewDraft(item.item_id, 'service_name_raw', event.target.value)}
                            />
                          </td>
                          <td>
                            <input
                              className={reviewInputClass(item, 'service_code_source')}
                              value={draft.service_code_source}
                              onFocus={() => acknowledgeField(item.item_id, 'service_code_source')}
                              onChange={(event) => updateReviewDraft(item.item_id, 'service_code_source', event.target.value)}
                            />
                          </td>
                          <td>
                            <input
                              className={reviewInputClass(item, 'price_resident_kzt')}
                              value={draft.price_resident_kzt}
                              onFocus={() => acknowledgeField(item.item_id, 'price_resident_kzt')}
                              onChange={(event) => updateReviewDraft(item.item_id, 'price_resident_kzt', event.target.value)}
                            />
                          </td>
                          <td>
                            <input
                              className={reviewInputClass(item, 'price_nonresident_kzt')}
                              value={draft.price_nonresident_kzt}
                              onFocus={() => acknowledgeField(item.item_id, 'price_nonresident_kzt')}
                              onChange={(event) => updateReviewDraft(item.item_id, 'price_nonresident_kzt', event.target.value)}
                            />
                          </td>
                          <td>
                            <input
                              className={reviewInputClass(item, 'price_original')}
                              value={draft.price_original}
                              onFocus={() => acknowledgeField(item.item_id, 'price_original')}
                              onChange={(event) => updateReviewDraft(item.item_id, 'price_original', event.target.value)}
                            />
                          </td>
                          <td className="review-state-cell">
                            <ReviewState item={item} />
                          </td>
                        </tr>
                      )
                    })}
                  </tbody>
                </table>
              </div>
            </article>
          </section>

          <div className="review-page-footer">
            {reviewError && <span className="form-error">{reviewError}</span>}
            <div className="review-footer-actions">
              <button className="secondary-button" type="button" onClick={() => navigate('/admin')} disabled={reviewSaving}>
                Отмена
              </button>
              <button className="primary-button" type="button" onClick={() => void saveReview()} disabled={reviewSaving}>
                {reviewSaving ? 'Сохраняю…' : 'Сохранить'}
              </button>
            </div>
          </div>
        </div>
      </div>
    )
  }

  return (
    <div className="shell">
      <aside className="sidebar">
        <div className="brand">
          <div className="brand-mark">M</div>
          <div>
            <div className="brand-title">MedArchive</div>
            <div className="brand-subtitle">Архив прайсов</div>
          </div>
        </div>

        <nav className="nav">
          <NavLink href="/" active={route.page === 'dashboard'} icon={<HomeIcon />}>
            Дашборд
          </NavLink>
          <NavLink href="/search" active={route.page === 'search'} icon={<SearchIcon />}>
            Поиск услуги
          </NavLink>
          <NavLink href="/admin" active={route.page === 'admin'} icon={<ShieldIcon />}>
            Админ-раздел
          </NavLink>
        </nav>
      </aside>

      <main className="content">
        <header className="topbar">
          <div>
            <h1>{pageTitle(route)}</h1>
            <p>
              {route.page === 'dashboard'
                ? 'Короткая сводка по документам, нормализации и очереди проверки.'
                : route.page === 'search'
                  ? 'Ищем услугу и сразу показываем партнёров с ценами.'
                  : route.page === 'admin'
                    ? 'Загрузка файлов, статусы обработки, списки документов и архивов.'
                    : route.page === 'partner'
                      ? 'Полный прайс партнёра, контакты и дата актуальности.'
                      : route.page === 'document'
                        ? 'Просмотр одного файла и его разобранных позиций.'
                        : 'Просмотр архива и всех входящих документов.'}
            </p>
          </div>
        </header>

        {route.page === 'dashboard' && (
          <section className="stack">
            <section className="dashboard">
              <article className="panel">
                <h2>Документы</h2>
                <div className="stat-large">{dashboardStats.documentsCount}</div>
                <p>Все загруженные файлы в базе</p>
              </article>
              <article className="panel">
                <h2>Нормализация</h2>
                <div className="stat-large">{dashboardStats.normalization}%</div>
                <p>Успешно сопоставленные позиции</p>
              </article>
              <article className="panel">
                <h2>Очередь</h2>
                <div className="stat-large">{dashboardStats.queue}</div>
                <p>Позиции для ручной проверки</p>
              </article>
              <article className="panel">
                <h2>Архивы</h2>
                <div className="stat-large">{dashboardStats.archivesCount}</div>
                <p>Загруженные архивы</p>
              </article>
            </section>

            <article className="panel">
              <div className="dashboard-links">
                <button className="primary-button" type="button" onClick={() => navigate('/admin')}>
                  Загрузка
                </button>
                <button className="secondary-button" type="button" onClick={() => navigate('/search')}>
                  Поиск услуги
                </button>
              </div>
            </article>
          </section>
        )}

        {route.page === 'admin' && (
          <section className="stack admin-stack">
            <article className="panel admin-upload-panel">
              <h2>Загрузка</h2>
              <form onSubmit={handleUpload} className="admin-upload-form">
                <label className="upload-picker" htmlFor={`upload-input-${uploadInputKey}`}>
                  <span className="upload-picker-button">Выберите файл</span>
                  <span className="upload-picker-name">{uploadFile?.name ?? 'Файл не выбран'}</span>
                </label>
                <input
                  id={`upload-input-${uploadInputKey}`}
                  key={uploadInputKey}
                  className="file-input sr-only"
                  type="file"
                  accept=".zip,.pdf,.docx,.xls,.xlsx"
                  onChange={(event) => setUploadFile(event.target.files?.[0] ?? null)}
                />
                <button className="primary-button upload-submit" type="submit" disabled={!uploadFile}>
                  <UploadIcon />
                  <span>Загрузить</span>
                </button>
              </form>
              <p className="muted admin-upload-hint">
                Принимает ZIP и одиночные документы: PDF, DOCX, XLS, XLSX.
              </p>
              {uploadError && <p className="form-error">{uploadError}</p>}
              {uploadResult && (
                <div className="admin-upload-result">
                  <DocumentCell
                    fileName={uploadResult.file_name}
                    sourceLabel={uploadResult.upload_type === 'archive' ? 'ZIP' : sourceLabelFromFileName(uploadResult.file_name)}
                  />
                  <div className="admin-upload-result-copy">
                    <div className="admin-result-row"><strong>Тип:</strong> {uploadResult.upload_type}</div>
                    <div className="admin-result-row">
                      <strong>Статус:</strong>{' '}
                      <span className={statusClassName(uploadResult.status)}>{statusLabel(uploadResult.status)}</span>
                    </div>
                    {uploadResult.upload_type === 'archive' ? (
                      <>
                        <div className="admin-result-row"><strong>Документы:</strong> {uploadResult.document_count ?? 0}</div>
                        <div className="admin-result-row"><strong>Позиции:</strong> {uploadResult.item_count ?? 0}</div>
                        <div className="admin-result-row"><strong>Совпадения:</strong> {uploadResult.matched_item_count ?? 0}</div>
                      </>
                    ) : (
                      <>
                        <div className="admin-result-row"><strong>Партнёр:</strong> {uploadResult.partner_name ?? '—'}</div>
                        <div className="admin-result-row"><strong>Позиции:</strong> {uploadResult.item_count ?? 0}</div>
                      </>
                    )}
                    {uploadResult.upload_type === 'document' && uploadResult.doc_id && (
                      <button
                        type="button"
                        className="admin-inline-action"
                        onClick={() => navigate(`/documents/${uploadResult.doc_id}`)}
                      >
                        <span>Открыть документ</span>
                        <ExternalLinkIcon />
                      </button>
                    )}
                    {uploadResult.upload_type === 'archive' && uploadResult.archive_id && (
                      <button
                        type="button"
                        className="admin-inline-action"
                        onClick={() => navigate(`/archives/${uploadResult.archive_id}`)}
                      >
                        <span>Открыть архив</span>
                        <ExternalLinkIcon />
                      </button>
                    )}
                  </div>
                </div>
              )}
            </article>

            <article className="panel admin-section-panel">
              <div className="section-head">
                <h2>Очередь проверки</h2>
              </div>
              {reviewDocumentsQueue.length ? (
                <div className="table-wrap soft-table-wrap">
                  <table className="soft-table">
                    <thead>
                      <tr>
                        <th>Документ</th>
                        <th>Партнёр</th>
                        <th>Формат</th>
                        <th>Строк на проверку</th>
                        <th>Действия</th>
                      </tr>
                    </thead>
                    <tbody>
                      {reviewDocumentsQueue.map((document) => (
                        <tr key={document.doc_id}>
                          <td><DocumentCell fileName={document.file_name} sourcePath={document.source_path} docId={document.doc_id} sourceLabel={document.source_label} compact /></td>
                          <td>{document.partner_name}</td>
                          <td>{document.source_label}</td>
                          <td>{document.issues_count}</td>
                          <td>
                              <button
                                type="button"
                                className="admin-inline-action"
                                onClick={() => navigate(`/documents/${document.doc_id}`)}
                              >
                                <span>Проверить</span>
                                <ExternalLinkIcon />
                              </button>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              ) : (
                <div className="empty-state">
                  <span className="empty-state-icon"><FolderIcon /></span>
                  <strong>Очередь пуста</strong>
                  <span className="muted">Документы без спорных позиций появятся здесь.</span>
                </div>
              )}
            </article>

            <article className="panel admin-section-panel">
              <div className="section-head">
                <h2>Документы</h2>
              </div>
              <div className="table-wrap soft-table-wrap">
                <table className="soft-table">
                  <thead>
                    <tr>
                      <th>Файл</th>
                      <th>Партнёр</th>
                      <th>Формат</th>
                      <th>Статус</th>
                      <th>Позиции</th>
                      <th>Действия</th>
                    </tr>
                  </thead>
                  <tbody>
                    {pendingUploads
                      .filter((upload) => upload.upload_type === 'document')
                      .map((upload) => (
                        <tr key={upload.id} className="upload-pending">
                          <td><DocumentCell fileName={upload.file_name} sourcePath={upload.source_path} docId={upload.doc_id} sourceLabel={upload.source_label} compact /></td>
                          <td>—</td>
                          <td>{upload.source_label}</td>
                          <td>
                            <span className={statusClassName(upload.status)}>{statusLabel(upload.status)}</span>
                          </td>
                          <td>—</td>
                          <td>{upload.status === 'failed' ? upload.message ?? 'ошибка загрузки' : 'ожидание'}</td>
                        </tr>
                      ))}
                    {documents.map((document) => {
                      const needsReview = document.parse_status === 'needs_review'
                      return (
                        <tr key={document.doc_id}>
                          <td><DocumentCell fileName={document.file_name} sourcePath={document.source_path} docId={document.doc_id} sourceLabel={document.source_label} compact /></td>
                          <td>{document.partner_name}</td>
                          <td>{document.source_label}</td>
                          <td>
                            <span className={statusClassName(document.parse_status)}>{statusLabel(document.parse_status)}</span>
                          </td>
                          <td>{document.items.length}</td>
                          <td>
                            <div className="table-actions admin-table-actions">
                              <button
                                type="button"
                                className="admin-inline-action"
                                onClick={() => navigate(`/documents/${document.doc_id}`)}
                              >
                                <span>{needsReview ? 'Проверить' : 'Открыть'}</span>
                                <ExternalLinkIcon />
                              </button>
                              <button
                                type="button"
                                className="danger-link-button admin-danger-action"
                                onClick={() => void deleteDocument(document.doc_id)}
                              >
                                <TrashIcon />
                                <span>Удалить</span>
                              </button>
                            </div>
                          </td>
                        </tr>
                      )
                    })}
                  </tbody>
                </table>
              </div>
            </article>

            <article className="panel admin-section-panel">
              <div className="section-head">
                <h2>Архивы</h2>
              </div>
              {pendingUploads.filter((upload) => upload.upload_type === 'archive').length || archives.length ? (
                <div className="table-wrap soft-table-wrap">
                  <table className="soft-table">
                    <thead>
                      <tr>
                        <th>Архив</th>
                        <th>Статус</th>
                        <th>Документы</th>
                        <th>Позиции</th>
                        <th>Действия</th>
                      </tr>
                    </thead>
                    <tbody>
                      {pendingUploads
                        .filter((upload) => upload.upload_type === 'archive')
                        .map((upload) => (
                          <tr key={upload.id} className="upload-pending">
                            <td><DocumentCell fileName={upload.file_name} sourcePath={upload.source_path} docId={upload.doc_id} sourceLabel="ZIP" compact /></td>
                            <td>
                              <span className={statusClassName(upload.status)}>{statusLabel(upload.status)}</span>
                            </td>
                            <td>—</td>
                            <td>—</td>
                            <td>{upload.status === 'failed' ? upload.message ?? 'ошибка загрузки' : 'ожидание'}</td>
                          </tr>
                        ))}
                      {archives.map((archive) => (
                        <tr key={archive.archive_id}>
                          <td><DocumentCell fileName={archive.file_name} sourcePath={archive.file_name} sourceLabel="ZIP" compact /></td>
                          <td>
                            <span className={statusClassName(archive.status)}>{statusLabel(archive.status)}</span>
                          </td>
                          <td>{archive.document_count}</td>
                          <td>{archive.item_count}</td>
                          <td>
                            <div className="table-actions admin-table-actions">
                              <button
                                type="button"
                                className="admin-inline-action"
                                onClick={() => navigate(`/archives/${archive.archive_id}`)}
                              >
                                <span>Открыть</span>
                                <ExternalLinkIcon />
                              </button>
                              <button
                                type="button"
                                className="danger-link-button admin-danger-action"
                                onClick={() => void deleteArchive(archive.archive_id)}
                              >
                                <TrashIcon />
                                <span>Удалить</span>
                              </button>
                            </div>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              ) : (
                <div className="empty-state">
                  <span className="empty-state-icon"><FolderIcon /></span>
                  <strong>Архивы отсутствуют</strong>
                  <span className="muted">Загруженные архивы появятся здесь.</span>
                </div>
              )}
            </article>
          </section>
        )}

        {route.page === 'search' && (
          <section className="stack">
            <article className="panel">
              <h2>Поиск услуги</h2>
              <form onSubmit={runSearch} className="archive-form">
                <input
                  className="search-input"
                  value={searchQuery}
                  onChange={(event) => setSearchQuery(event.target.value)}
                  placeholder="Введите название услуги"
                />
                <button className="primary-button" type="submit">
                  Искать
                </button>
              </form>
              {searchLoading && <p style={{ marginTop: 12 }}>Ищу…</p>}
              {searchError && <p className="form-error">{searchError}</p>}
            </article>

            <article className="panel">
              <div className="section-head">
                <h2>Подходящие услуги</h2>
              </div>
              <div className="table-wrap">
                <table>
                  <thead>
                    <tr>
                      <th>Услуга</th>
                      <th>Категория</th>
                      <th>Код</th>
                    </tr>
                  </thead>
                  <tbody>
                    {(searchResponse?.services ?? []).slice(0, 20).map((service) => (
                      <tr key={service.service_id}>
                        <td>
                          <button
                            type="button"
                            className="inline-link-button"
                            onClick={async () => {
                              setSelectedServiceId(service.service_id)
                              setServicePartnersLoading(true)
                              try {
                                const data = await apiGet<ServicePartnerItem[]>(`/services/${service.service_id}/partners`)
                                setServicePartners(data)
                              } catch (error) {
                                console.error(error)
                                setServicePartners([])
                              } finally {
                                setServicePartnersLoading(false)
                              }
                            }}
                          >
                            {service.service_name}
                          </button>
                        </td>
                        <td>{service.category ?? '—'}</td>
                        <td>{service.icd_code ?? '—'}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </article>

            <article className="panel">
              <div className="section-head">
                <h2>Партнёры и цены</h2>
              </div>
              {selectedServiceId ? (
                servicePartnersLoading ? (
                  <p>Загружаю цены…</p>
                ) : servicePartners.length ? (
                  <div className="table-wrap">
                    <table>
                      <thead>
                        <tr>
                          <th>Партнёр</th>
                          <th>Резидент</th>
                          <th>Нерезидент</th>
                          <th>Контакты</th>
                        </tr>
                      </thead>
                      <tbody>
                        {servicePartners.map(({ partner, price_item }) => {
                          const prices = formatPriceCell(price_item)
                          return (
                            <tr key={`${partner.partner_id}-${price_item.item_id}`}>
                              <td>
                                <button
                                  type="button"
                                  className="inline-link-button"
                                  onClick={() => navigate(`/partners/${partner.partner_id}`)}
                                >
                                  {partner.name}
                                </button>
                              </td>
                              <td>{prices.resident}</td>
                              <td>{prices.nonresident}</td>
                              <td>{partner.contact_phone ?? partner.contact_email ?? '—'}</td>
                            </tr>
                          )
                        })}
                      </tbody>
                    </table>
                  </div>
                ) : (
                  <p>По этой услуге пока нет партнёров.</p>
                )
              ) : (
                <p>Выберите услугу в таблице выше.</p>
              )}
            </article>
          </section>
        )}

        {route.page === 'partner' && partnerProfile && (
          <section className="stack">
            <article className="panel">
              <h2>{partnerProfile.partner.name}</h2>
              <div className="chip-grid" style={{ marginBottom: 12 }}>
                <span className="chip">{partnerProfile.partner.city ?? '—'}</span>
                <span className="chip">{partnerProfile.partner.contact_phone ?? '—'}</span>
                <span className="chip">{partnerProfile.partner.contact_email ?? '—'}</span>
                <span className="chip">{partnerProfile.latest_effective_date ?? '—'}</span>
              </div>
              <div className="result-box">
                <div>Адрес: {partnerProfile.partner.address ?? '—'}</div>
                <div>BIN: {partnerProfile.partner.bin ?? '—'}</div>
                <div>Статус: {partnerProfile.partner.is_active ? 'активен' : 'неактивен'}</div>
              </div>
              <div style={{ marginTop: 12 }}>
                <a className="inline-link" href="/search" onClick={(event) => { event.preventDefault(); navigate('/search') }}>
                  Назад к поиску
                </a>
              </div>
            </article>

            <article className="panel">
              <div className="section-head">
                <h2>Полный прайс</h2>
              </div>
              <div className="table-wrap">
                <table>
                  <thead>
                    <tr>
                      <th>#</th>
                      <th>Услуга</th>
                      <th>Код</th>
                      <th>Резидент</th>
                      <th>Нерезидент</th>
                      <th>Оригинал</th>
                    </tr>
                  </thead>
                  <tbody>
                    {partnerProfile.items.slice(0, 200).map(({ price_item, service }) => {
                      const prices = formatPriceCell(price_item)
                      return (
                        <tr key={price_item.item_id}>
                          <td>{service?.service_name ?? price_item.service_name_raw}</td>
                          <td>{price_item.service_code_source ?? '—'}</td>
                          <td>{prices.resident}</td>
                          <td>{prices.nonresident}</td>
                          <td>{prices.original}</td>
                        </tr>
                      )
                    })}
                  </tbody>
                </table>
              </div>
            </article>

            <article className="panel">
              <div className="section-head">
                <h2>Документы партнёра</h2>
              </div>
              <div className="table-wrap">
                <table>
                  <thead>
                    <tr>
                      <th>Файл</th>
                      <th>Источник</th>
                      <th>Дата актуальности</th>
                    </tr>
                  </thead>
                  <tbody>
                    {partnerProfile.documents.map((document) => (
                      <tr key={document.doc_id}>
                        <td>
                          <button
                            type="button"
                            className="inline-link-button"
                            onClick={() => navigate(`/documents/${document.doc_id}`)}
                          >
                            {formatDocumentLabel(document.file_name, document.source_label)}
                          </button>
                        </td>
                        <td>{document.partner_name}</td>
                        <td>{document.effective_date ?? '—'}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </article>
          </section>
        )}

        {route.page === 'document' && documentDetail && (
          <section className="stack">
            <article className="panel">
              <h2>{resolvedDocumentName(documentDetail.document.file_name, documentDetail.document.source_path, documentDetail.document.doc_id)}</h2>
              <div className="chip-grid" style={{ marginBottom: 12 }}>
                <span className="chip">{documentDetail.document.file_format.toUpperCase()}</span>
                <span className={`chip ${statusClassName(documentDetail.document.parse_status)}`}>{statusLabel(documentDetail.document.parse_status)}</span>
                <span className="chip">{documentDetail.partner.name}</span>
                <span className="chip">{documentDetail.document.effective_date ?? '—'}</span>
              </div>
              <div className="result-box">
                <div>Архив: {documentDetail.archive?.file_name ?? '—'}</div>
                <div>Путь: {documentDetail.document.source_path ?? '—'}</div>
                <div>Файл в БД: {documentDetail.document.doc_id}</div>
              </div>
              <div style={{ marginTop: 12, display: 'flex', gap: 12, flexWrap: 'wrap' }}>
                <a className="inline-link" href="/admin" onClick={(event) => { event.preventDefault(); navigate('/admin') }}>
                  Назад
                </a>
                <button type="button" className="danger-link-button" onClick={() => void deleteDocument(documentDetail.document.doc_id)}>
                  Удалить файл
                </button>
              </div>
            </article>

            {documentDetail.document.parse_log && (
              <article className="panel">
                <div className="section-head">
                  <h2>Лог разбора</h2>
                </div>
                <pre className="raw-text">{documentDetail.document.parse_log}</pre>
              </article>
            )}

            <article className="panel">
              <div className="section-head">
                <h2>{documentDetail.document.parse_status === 'needs_review' ? 'Проверка строк' : 'Позиции'}</h2>
              </div>
              <div className="table-wrap">
                <table>
                  <thead>
                    <tr>
                      <th>Услуга</th>
                      <th>Код</th>
                      <th>Резидент</th>
                      <th>Нерезидент</th>
                      <th>Оригинал</th>
                      <th>Проверка</th>
                    </tr>
                  </thead>
                  <tbody>
                    {documentDetail.items.map((item, index) => {
                      const prices = formatPriceCell(item)
                      const draft = reviewDrafts.find((entry) => entry.item_id === item.item_id)
                      if (documentDetail.document.parse_status === 'needs_review' && draft) {
                        return (
                          <tr key={item.item_id} className={itemNeedsReview(item) ? 'review-row' : undefined}>
                            <td>{index + 1}</td>
                            <td>
                              <input
                                className={reviewInputClass(item, 'service_name_raw')}
                                value={draft.service_name_raw}
                                onFocus={() => acknowledgeField(item.item_id, 'service_name_raw')}
                                onChange={(event) => updateReviewDraft(item.item_id, 'service_name_raw', event.target.value)}
                              />
                            </td>
                            <td>
                              <input
                                className={reviewInputClass(item, 'service_code_source')}
                                value={draft.service_code_source}
                                onFocus={() => acknowledgeField(item.item_id, 'service_code_source')}
                                onChange={(event) => updateReviewDraft(item.item_id, 'service_code_source', event.target.value)}
                              />
                            </td>
                            <td>
                              <input
                                className={reviewInputClass(item, 'price_resident_kzt')}
                                value={draft.price_resident_kzt}
                                onFocus={() => acknowledgeField(item.item_id, 'price_resident_kzt')}
                                onChange={(event) => updateReviewDraft(item.item_id, 'price_resident_kzt', event.target.value)}
                              />
                            </td>
                            <td>
                              <input
                                className={reviewInputClass(item, 'price_nonresident_kzt')}
                                value={draft.price_nonresident_kzt}
                                onFocus={() => acknowledgeField(item.item_id, 'price_nonresident_kzt')}
                                onChange={(event) => updateReviewDraft(item.item_id, 'price_nonresident_kzt', event.target.value)}
                              />
                            </td>
                            <td>
                              <input
                                className={reviewInputClass(item, 'price_original')}
                                value={draft.price_original}
                                onFocus={() => acknowledgeField(item.item_id, 'price_original')}
                                onChange={(event) => updateReviewDraft(item.item_id, 'price_original', event.target.value)}
                              />
                            </td>
                            <td>{itemNeedsReview(item) ? itemReviewReason(item) : item.verification_note ?? '—'}</td>
                          </tr>
                        )
                      }
                      return (
                        <tr key={item.item_id}>
                          <td>{index + 1}</td>
                          <td>{item.service_name_raw}</td>
                          <td>{item.service_code_source ?? '—'}</td>
                          <td>{prices.resident}</td>
                          <td>{prices.nonresident}</td>
                          <td>{prices.original}</td>
                          <td>{item.verification_note ?? '—'}</td>
                        </tr>
                      )
                    })}
                  </tbody>
                </table>
              </div>
              {documentDetail.document.parse_status === 'needs_review' && (
                <div className="review-footer">
                  {reviewError && <span className="form-error">{reviewError}</span>}
                  <button className="primary-button" type="button" onClick={() => void saveReview()} disabled={reviewSaving}>
                    {reviewSaving ? 'Сохраняю…' : 'Сохранить проверку'}
                  </button>
                </div>
              )}
            </article>
          </section>
        )}

        {route.page === 'archive' && archiveDetail && (
          <section className="stack">
            <article className="panel">
              <h2>{archiveDetail.archive.file_name}</h2>
              <div className="chip-grid" style={{ marginBottom: 12 }}>
                <span className="chip">{statusLabel(archiveDetail.archive.status)}</span>
                <span className="chip">{archiveDetail.archive.document_count} документов</span>
                <span className="chip">{archiveDetail.archive.item_count} позиций</span>
              </div>
              <div className="result-box">
                <div>Загружен: {new Date(archiveDetail.archive.uploaded_at).toLocaleString('ru-RU')}</div>
                <div>Обработан: {archiveDetail.archive.processed_at ? new Date(archiveDetail.archive.processed_at).toLocaleString('ru-RU') : '—'}</div>
                <div>Путь: {archiveDetail.archive.saved_path}</div>
              </div>
              <div style={{ marginTop: 12, display: 'flex', gap: 12, flexWrap: 'wrap' }}>
                <a className="inline-link" href="/admin" onClick={(event) => { event.preventDefault(); navigate('/admin') }}>
                  Назад
                </a>
                <button type="button" className="danger-link-button" onClick={() => void deleteArchive(archiveDetail.archive.archive_id)}>
                  Удалить архив
                </button>
              </div>
            </article>

            <article className="panel">
              <div className="section-head">
                <h2>Документы в архиве</h2>
              </div>
              <div className="table-wrap">
                <table>
                  <thead>
                    <tr>
                      <th>Файл</th>
                      <th>Партнёр</th>
                      <th>Формат</th>
                      <th>Статус</th>
                      <th>Позиции</th>
                    </tr>
                  </thead>
                  <tbody>
                    {archiveDetail.documents.map((document) => (
                      <tr key={document.doc_id}>
                        <td>
                          <button
                            type="button"
                            className="inline-link-button"
                            onClick={() => navigate(`/documents/${document.doc_id}`)}
                          >
                            {formatDocumentLabel(document.file_name, document.source_label)}
                          </button>
                        </td>
                        <td>{document.partner_name}</td>
                        <td>{document.source_label}</td>
                        <td>
                          <span className={statusClassName(document.parse_status)}>{statusLabel(document.parse_status)}</span>
                        </td>
                        <td>{document.item_count}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </article>
          </section>
        )}
      </main>
    </div>
  )
}

export default function App() {
  return <AppBody />
}
