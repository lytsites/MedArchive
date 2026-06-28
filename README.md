# MedArchive

MedArchive — сервис для загрузки, распознавания, нормализации и поиска медицинских прайс-листов клиник.

Проект принимает отдельные файлы и ZIP-архивы, извлекает услуги и цены из PDF/DOCX/XLS/XLSX, отправляет спорные строки на ручную проверку и хранит результат в единой базе.

## Что входит в проект

- FastAPI backend
- React + Vite frontend
- PostgreSQL для данных
- Redis и Celery для фоновой обработки
- Docker Compose для запуска всей системы
- OCR-пайплайн для PDF с поддержкой Document AI и fallback-режимов

## Поддерживаемые форматы

- PDF
- DOCX
- XLS
- XLSX
- ZIP с файлами внутри, включая вложенные папки

## Что уже есть в интерфейсе

- поиск услуг
- страница партнёра с полным прайсом
- админ-раздел для загрузки файлов
- список документов и архивов
- очередь ручной проверки
- отдельная полноэкранная страница проверки документа

## Что нужно для запуска

- Docker Desktop
- Docker Compose
- 8 GB RAM или больше
- доступ в интернет для первого `docker compose build`
- Google Cloud Document AI credentials, если хотите обрабатывать PDF через Document AI

## Структура проекта

- `backend/` — API, импорт файлов, OCR, БД
- `frontend/` — интерфейс пользователя
- `data/reference.xlsx` — справочник услуг
- `demo/` — демо-файлы клиник и ZIP-архив
- `credentials/document-ai.json` — JSON ключ сервисного аккаунта Google Cloud
- `storage/` — загруженные файлы и результаты обработки

## Быстрый старт

### 1. Скопировать переменные окружения

PowerShell:

```powershell
Copy-Item .env.example .env
```

Если нужен bash:

```bash
cp .env.example .env
```

### 2. Положить ключ Google Cloud

Для Document AI нужен service account JSON.

Положите файл сюда:

```text
credentials/document-ai.json
```

Если у вас другой файл, либо переименуйте его в `document-ai.json`, либо поменяйте:

```env
GOOGLE_APPLICATION_CREDENTIALS=/app/credentials/document-ai.json
```

### 3. Проверить справочник услуг

Справочник уже лежит в проекте как:

```text
data/reference.xlsx
```

Если хотите использовать свой справочник, замените этот файл на свой `.xlsx`.

### 4. Запустить проект

```bash
docker compose up --build
```

После запуска:

- фронтенд: `http://localhost:3000`
- backend Swagger: `http://localhost:8000/docs`

## Загрузка справочника услуг

После старта контейнеров импортируйте справочник в базу:

```bash
docker compose exec backend python -m app.scripts.load_service_reference /app/data/reference.xlsx
```

Скрипт ожидает в первой строке заголовки и читает такие поля:

- `Name_ru`
- `Specialty` или `specialty`
- `TarificatrCode` или `TariffCode`

## Рекомендуемая конфигурация OCR

Для PDF лучше использовать Document AI:

```env
OCR_PROVIDER=document_ai
DOCUMENT_AI_PROJECT_ID=central-trees-491011-c5
DOCUMENT_AI_LOCATION=us
DOCUMENT_AI_PROCESSOR_NAME=
DOCUMENT_AI_PROCESSOR_DISPLAY_NAME=medarchive-pdf-ocr
DOCUMENT_AI_PROCESSOR_TYPE=OCR_PROCESSOR
DOCUMENT_AI_AUTO_CREATE_PROCESSOR=true
DOCUMENT_AI_BATCH_PAGES=5
PDF_OCR_DPI=220
```

Если Document AI временно недоступен, в проекте есть fallback-ветки OCR, но для демонстрации лучше прогонять документы заранее и не полагаться на них в момент показа.

## Полезные команды

```bash
docker compose ps
docker compose logs -f backend
docker compose logs -f frontend
docker compose down
```

## Как загружать документы

Через админ-раздел можно загружать:

- один файл
- ZIP-архив

Фоновая обработка сама разберёт файл, создаст документ и, если нужно, отправит спорные строки в очередь проверки.

## Что важно знать перед демо

- PDF-сканы могут быть тяжёлыми, поэтому для показа лучше заранее прогнать нужные файлы.
- Для OCR по PDF важны корректные Google Cloud credentials и включённый Document AI.
- Если в прайсе есть спорные строки, они попадут в ручную проверку и откроются на отдельной странице.

## Локальный запуск без Docker

Docker — основной и рекомендуемый способ запуска. Но если нужно, можно поднять проект вручную:

Backend:

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Frontend:

```bash
cd frontend
npm install
npm run dev
```

## Troubleshooting

### Docker не видит Google credentials

Проверьте, что файл лежит именно здесь:

```text
credentials/document-ai.json
```

И что в `.env` указан правильный путь:

```env
GOOGLE_APPLICATION_CREDENTIALS=/app/credentials/document-ai.json
```

### Импорт справочника не стартует

Проверьте, что `data/reference.xlsx` существует и файл не повреждён.

### PDF обрабатываются слишком долго

- уменьшите батч OCR
- прогоните документы заранее
- проверьте, что Google Cloud квоты и billing активны
