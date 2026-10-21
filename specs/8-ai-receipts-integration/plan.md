# Implementation Plan: AI Receipt Integration & Multi-Provider Architecture

This implementation plan details the engineering deliverables required to integrate automated AI receipt parsing into Wrangler, as specified in [`specs/v3/1-ai-receipts-integration/spec.md`](file:///D:/src/personal/wrangler/specs/v3/1-ai-receipts-integration/spec.md).

The feature introduces a pluggable AI provider abstraction layer (supporting OpenAI vision models and deterministic mock fixtures), multi-file batch staging in `ImportView`, and receipt-first intake with real-time auto-fill in `ManualEntryView`. It introduces zero database migrations and zero schema changes.

The plan is organized into sequential phases and atomic implementation tasks. Each task specifies concrete deliverables and automated unit or integration test coverage adhering to project conventions and development standards defined in [`AGENTS.md`](file:///D:/src/personal/wrangler/AGENTS.md).

---

## Phase 1: Backend Dependencies & AI Abstraction Layer

*Goal:* Equip the backend with PDF inspection capabilities, define the extensible AI provider interface, implement mock and OpenAI providers, and provide factory-based provider instantiation.

### 1.1 Add `pypdf` Dependency & AI Configuration Settings
- In [`api/pyproject.toml`](file:///D:/src/personal/wrangler/api/pyproject.toml):
  - Add `"pypdf>=5.0.0"` to the `dependencies` array.
- In [`api/src/core/config.py`](file:///D:/src/personal/wrangler/api/src/core/config.py):
  - Add AI configuration settings to [`Settings`](file:///D:/src/personal/wrangler/api/src/core/config.py):
    - `AI_PROVIDER: str = "openai"` (supports `"openai"` or `"mock"`)
    - `OPENAI_API_KEY: str = ""`
    - `OPENAI_MODEL: str = "gpt-4o-mini"`
    - `OPENAI_BASE_URL: str = "https://api.openai.com/v1"`
    - `AI_TIMEOUT_SECONDS: int = 60`
    - `AI_MAX_BATCH_CONCURRENCY: int = 3`
    - `AI_MAX_PDF_PAGES: int = 3`
    - `MAX_RECEIPT_FILE_SIZE: int = 20 * 1024 * 1024` (20 MB limit)

### 1.2 Implement AI Provider Base Interface and Parse Result Schema
- Create [`api/src/services/ai/base.py`](file:///D:/src/personal/wrangler/api/src/services/ai/base.py):
  - Define `ReceiptParseResult(BaseModel)`:
    - `merchant: str | None = Field(default=None, description="Clean name of the merchant or store")`
    - `date: datetime.date | None = Field(default=None, description="Transaction date")`
    - `total_amount: Decimal | None = Field(default=None, description="Final total amount charged")`
    - `description: str | None = Field(default=None, description="Concise description formatted as '{Merchant} - {Summary of items purchased}'")`
    - `model_config = ConfigDict(from_attributes=True)`
  - Define `BaseReceiptParserProvider(ABC)`:
    - `@property @abstractmethod def provider_id(self) -> str:`
    - `@abstractmethod async def parse_receipt(self, file_bytes: bytes, filename: str, mime_type: str) -> ReceiptParseResult:`
    - Document exceptions: `ValueError` for unsupported format or payload rejection, `RuntimeError` for unrecoverable provider/API errors.

### 1.3 Implement Mock Receipt Parser Provider
- Create [`api/src/services/ai/mock_provider.py`](file:///D:/src/personal/wrangler/api/src/services/ai/mock_provider.py):
  - Define `MockReceiptParser(BaseReceiptParserProvider)`:
    - `provider_id = "mock"`
    - Implement `async def parse_receipt(self, file_bytes: bytes, filename: str, mime_type: str) -> ReceiptParseResult`:
      - If filename contains `"corrupt"`, `"invalid"`, or `"fail"`, raise `ValueError(f"Corrupt or unreadable document: {filename}")`.
      - If filename contains `"timeout"`, raise `RuntimeError("AI provider request timed out")`.
      - If filename contains `"missing_total"`, return result with `total_amount=None`.
      - Extract numeric amount from filename matching pattern `(\d+)[._](\d{2})` if present (e.g. `sample_receipt_45_99.png` -> `Decimal("45.99")`); otherwise default to `Decimal("45.99")`.
      - Extract or default merchant: `"Sample Store"`.
      - Default date: `datetime.date.today()`.
      - Default description: `f"{merchant} - Office supplies"`.

### 1.4 Implement OpenAI Receipt Parser Provider
- Create [`api/src/services/ai/openai_provider.py`](file:///D:/src/personal/wrangler/api/src/services/ai/openai_provider.py):
  - Define `OpenAIReceiptParser(BaseReceiptParserProvider)`:
    - `provider_id = "openai"`
    - Constructor parameters: `api_key: str`, `model: str = "gpt-4o-mini"`, `base_url: str = "https://api.openai.com/v1"`, `timeout_seconds: int = 60`, `max_pdf_pages: int = 10`.
    - Validate API key presence; raise `RuntimeError("OPENAI_API_KEY is not configured")` if empty or missing.
    - PDF page validation: if `mime_type == "application/pdf"`, inspect page count using `len(pypdf.PdfReader(io.BytesIO(file_bytes)).pages)`. If page count exceeds `max_pdf_pages`, raise `ValueError(f"PDF page count exceeds maximum allowed limit of {self.max_pdf_pages} pages")`.
    - Multi-modal payload construction:
      - Raster images (`image/jpeg`, `image/png`, `image/webp`): base64 encoded and attached via `{"type": "image_url", "image_url": {"url": f"data:{mime_type};base64,{b64_str}"}}`.
      - PDF documents (`application/pdf`): base64 encoded and attached via `{"type": "file", "file": {"filename": filename, "file_data": f"data:application/pdf;base64,{b64_str}"}}`.
      - Unsupported MIME types: raise `ValueError(f"Unsupported MIME type: {mime_type}")`.
    - System prompt: North American expense accountant prompt instructing model to identify true merchant name, sanitize line item noise, parse dates to standard `YYYY-MM-DD`, extract settled total, and format description as `"{Merchant} - {Items Summary}"`.
    - Structured outputs schema: OpenAI `response_format` with `type: "json_schema"`, `strict: True`, enforcing `merchant`, `date`, `total_amount`, and `description`.
    - HTTP Client: execute async POST to `f"{self.base_url.rstrip('/')}/chat/completions"` using `httpx.AsyncClient(timeout=self.timeout_seconds)`.
    - Translate HTTP 4xx/5xx responses or connection errors to `RuntimeError`.
    - Deserialize response JSON conforming to `ReceiptParseResult`.

### 1.5 Implement AI Provider Factory
- Create [`api/src/services/ai/factory.py`](file:///D:/src/personal/wrangler/api/src/services/ai/factory.py):
  - Implement `get_receipt_parser() -> BaseReceiptParserProvider`:
    - Read `provider = settings.AI_PROVIDER.lower().strip()`.
    - If `"openai"`: return `OpenAIReceiptParser(api_key=settings.OPENAI_API_KEY, model=settings.OPENAI_MODEL, base_url=settings.OPENAI_BASE_URL, timeout_seconds=settings.AI_TIMEOUT_SECONDS, max_pdf_pages=settings.AI_MAX_PDF_PAGES)`.
    - If `"mock"`: return `MockReceiptParser()`.
    - Otherwise raise `ValueError(f"Unsupported AI_PROVIDER: '{provider}'")`.

### 1.6 AI Abstraction Layer Unit Test Suite
- Create [`api/tests/test_ai_provider.py`](file:///D:/src/personal/wrangler/api/tests/test_ai_provider.py):
  - Test `ReceiptParseResult` model serialization, optional fields, and Decimal parsing.
  - Test `MockReceiptParser`:
    - Deterministic filename parsing (e.g. `receipt_87_45.jpg` -> `Decimal("87.45")`).
    - Fallback defaults when filename contains no amount cues.
    - Missing total handling (`missing_total` keyword).
    - Corrupt document error simulation (`corrupt` keyword).
    - Timeout error simulation (`timeout` keyword).
  - Test `OpenAIReceiptParser` using mocked `httpx.AsyncClient`:
    - Successful raster image dispatch (`image/jpeg`, `image/png`, `image/webp`) with base64 data URL.
    - Successful PDF document dispatch with native Chat Completions file block.
    - PDF page threshold enforcement via `pypdf` rejecting documents exceeding `AI_MAX_PDF_PAGES` with `ValueError`.
    - Empty API key raising `RuntimeError`.
    - Upstream 4xx/5xx HTTP errors translating to `RuntimeError`.
  - Test `get_receipt_parser` factory resolving `"mock"`, `"openai"`, and raising `ValueError` on unknown provider strings.

---

## Phase 2: Receipt Parser Importer & Backend Multi-File Processing

*Goal:* Implement the `ReceiptParserImporter`, update the importers execution pipeline with pre-AI SHA-256 deduplication, concurrency control, and resilient partial success, and expose the ad-hoc parse endpoint.

### 2.1 Implement `ReceiptParserImporter` and Register in Default Importers
- Create [`api/src/services/importers/ai_receipt.py`](file:///D:/src/personal/wrangler/api/src/services/importers/ai_receipt.py):
  - Define `ReceiptParserImporter(BaseImporter)`:
    - `importer_id = "receipt_parser"`
    - `source_name = "receipt_parser"`
    - `display_name = "Receipt Scanner (AI)"`
    - `description = "Scan receipt photos (.png, .jpg, .webp) or PDFs into staging with attached files."`
    - `input_type = ImporterInputType.FILE`
    - `accepted_file_types = [".jpg", ".jpeg", ".png", ".webp", ".pdf"]`
    - `supports_mark_imported = False`
    - Implement `async def fetch_and_parse(self, file_bytes: bytes | None = None, filename: str | None = None) -> list[ImportedTransactionData]`:
      - Verify `file_bytes` is provided and non-empty; raise `ImporterValidationError("Receipt file content is required")` if missing.
      - Map file extension to MIME type (`image/jpeg`, `image/png`, `image/webp`, `application/pdf`); raise `ImporterValidationError` if unsupported.
      - Compute deterministic hash `external_id = f"sha256:{hashlib.sha256(file_bytes).hexdigest()}"`.
      - Call `parser = get_receipt_parser(); result = await parser.parse_receipt(file_bytes, filename or "receipt", mime_type)`.
      - Return `[ImportedTransactionData(external_id=external_id, date=result.date, description=result.description or result.merchant or "Receipt", total_amount=result.total_amount, receipt=ImporterReceiptData(filename=filename or "receipt", content=file_bytes, content_type=mime_type))]`.
- In [`api/src/services/importers/registry.py`](file:///D:/src/personal/wrangler/api/src/services/importers/registry.py):
  - Import `ReceiptParserImporter` from `.ai_receipt`.
  - Register `register_importer(ReceiptParserImporter())`.

### 2.2 Update Importer Schemas with `failed_files`
- In [`api/src/schemas/importer.py`](file:///D:/src/personal/wrangler/api/src/schemas/importer.py):
  - Update `ImporterRunResponse`:
    - Add `failed_files: list[str] = Field(default_factory=list)` to track per-file errors in batch imports without aborting valid rows.

### 2.3 Extend Importers Router for Multi-File Concurrency, Resilient Error Handling & Pre-AI Deduplication
- In [`api/src/routers/importers.py`](file:///D:/src/personal/wrangler/api/src/routers/importers.py):
  - In `run_importer`:
    - Multi-file extraction: retrieve files from `form.getlist("files")` falling back to `form.getlist("file")`.
    - If `importer.input_type == ImporterInputType.FILE`:
      - Verify at least one file was uploaded; raise `HTTPException(400, "File upload is required for this importer")` if empty.
      - Validate each file size does not exceed `settings.MAX_RECEIPT_FILE_SIZE` (20 MB); raise `HTTPException(413, f"File '{file.filename}' exceeds maximum allowed size of 20MB")` if exceeded.
      - Check file extensions against `importer.accepted_file_types`; raise `HTTPException(400, f"Unsupported file type. Allowed: {', '.join(importer.accepted_file_types)}")` if invalid.
    - Pre-AI SHA-256 Deduplication (for `receipt_parser`):
      - Read file bytes and compute SHA-256 external IDs.
      - Batch query existing external IDs from `staged_transactions` and `transactions` where `source == importer.source_name`.
      - Check files against existing IDs and duplicate files within the batch; increment `skipped_duplicates += 1` and skip AI parsing for duplicates.
    - Concurrency Control:
      - Limit parallel file parsing using `semaphore = asyncio.Semaphore(settings.AI_MAX_BATCH_CONCURRENCY)`.
    - Resilient Partial Success:
      - Wrap individual file parsing in `try...except (ImporterValidationError, ValueError, RuntimeError, Exception) as exc:`
      - Record failures in `failed_files.append(f"{filename}: {str(exc)}")`.
      - Successfully parsed items persist receipt files to `RECEIPT_STORAGE_DIR` and save `StagedTransaction` records in the database.
    - Return `ImporterRunResponse` with `total_parsed`, `staged_count`, `skipped_duplicates`, `items`, and `failed_files`.

### 2.4 Implement Ad-Hoc Receipt Parse Endpoint
- In [`api/src/routers/receipts.py`](file:///D:/src/personal/wrangler/api/src/routers/receipts.py):
  - Add `POST /api/receipts/parse` accepting `file: UploadFile`:
    - Enforce file size limit <= 20 MB; return `HTTPException(413, "Receipt file exceeds 20MB limit")`.
    - Validate MIME type against `image/jpeg`, `image/png`, `image/webp`, `application/pdf`; return `HTTPException(400, "Unsupported file type. Allowed: .jpg, .jpeg, .png, .webp, .pdf")`.
    - Invoke active parser via `parser = get_receipt_parser()`.
    - Handle `ValueError` (e.g. PDF page limit exceeded, unreadable format) -> return `HTTPException(400, detail=str(exc))`.
    - Handle `RuntimeError` (e.g. unconfigured `OPENAI_API_KEY`, upstream network failure) -> return `HTTPException(503, detail=str(exc))`.
    - Return `ReceiptParseResult` schema response.

### 2.5 Importer & Receipts API Test Suite
- Create [`api/tests/test_receipt_parser_api.py`](file:///D:/src/personal/wrangler/api/tests/test_receipt_parser_api.py):
  - Test `POST /api/receipts/parse`:
    - Valid image returns 200 OK with extracted `merchant`, `date`, `total_amount`, `description`.
    - Unsupported file MIME type returns 400 Bad Request.
    - File exceeding 20 MB returns 413 Payload Too Large.
    - Upstream provider error or missing API key returns 503 Service Unavailable.
  - Test `POST /api/importers/receipt_parser/run`:
    - Single file staging with receipt file persisted into `RECEIPT_STORAGE_DIR` and valid `StagedTransaction`.
    - Multi-file staging with concurrent file execution producing multiple staged records.
    - Pre-AI deduplication: re-uploading an identical receipt file skips AI parsing and increments `skipped_duplicates`.
    - Resilient batch import: uploading a batch containing one valid and one corrupt receipt imports the valid transaction and populates `failed_files` with the corrupt file.
    - Incomplete receipt extraction: parsing a receipt with missing total creates a `StagedTransaction` with `total_amount = None` and `is_ready = False`.

---

## Phase 3: Frontend Types, Stores & Pinia State

*Goal:* Update TypeScript interfaces and Pinia stores to handle multi-file staging, batch error reporting, and ad-hoc receipt parsing.

### 3.1 Update Staging Types and Store with Multi-File Upload & Failure Reporting
- In [`web/src/types/staging.ts`](file:///D:/src/personal/wrangler/web/src/types/staging.ts):
  - Add `failed_files?: string[]` to [`ImporterRunResponse`](file:///D:/src/personal/wrangler/web/src/types/staging.ts).
- In [`web/src/stores/staging.ts`](file:///D:/src/personal/wrangler/web/src/stores/staging.ts):
  - Update `canRunImporter(importer: ImporterMetadata | null, file: File | File[] | null): boolean` to handle arrays:
    - If `Array.isArray(file)`, return `file.length > 0`.
    - Otherwise return `Boolean(file)`.
  - Update `runImporter(importerId: string, file?: File | File[] | null): Promise<ImporterRunResponse>`:
    - If `Array.isArray(file)`, append each file to `FormData` (`fd.append("files", f)`).
    - If single `File`, append `fd.append("files", file)`.
  - In `SOURCE_FILTER_OPTIONS`: add `{ label: "Receipt Scanner", value: "receipt_parser" }`.
  - In `formatImporterSummaryToast`: append failure summary if `result.failed_files && result.failed_files.length > 0`.

### 3.2 Add Receipt Parsing Types and Action to Transaction Store
- In [`web/src/types/transaction.ts`](file:///D:/src/personal/wrangler/web/src/types/transaction.ts):
  - Define and export `ReceiptParseResponse`:
    ```typescript
    export interface ReceiptParseResponse {
      merchant: string | null
      date: string | null
      total_amount: number | string | null
      description: string | null
    }
    ```
- In [`web/src/stores/transactions.ts`](file:///D:/src/personal/wrangler/web/src/stores/transactions.ts):
  - Implement `async function parseReceipt(file: File): Promise<ReceiptParseResponse>`:
    - Construct `FormData` with `fd.append("file", file)`.
    - POST to `/api/receipts/parse` via `apiClient.post<ReceiptParseResponse>("/api/receipts/parse", fd)`.
    - Return extracted response data.

### 3.3 Pinia Staging & Transaction Receipt Store Unit Test Suite
- Create [`web/tests/receiptStores.test.ts`](file:///D:/src/personal/wrangler/web/tests/receiptStores.test.ts):
  - Test `canRunImporter` helper with `null`, single `File`, empty array `[]`, and populated array `[File, File]`.
  - Test `stagingStore.runImporter` with array of files verifying `FormData` composition.
  - Test `formatImporterSummaryToast` formatting clean success, duplicates skipped, and failed files messages.
  - Test `transactionStore.parseReceipt` verifying multipart form POST and parsed return payload.

---

## Phase 4: Frontend UI Views (ImportView & ManualEntryView)

*Goal:* Enable multi-file selection and batch feedback in `ImportView.vue`, and restructure `ManualEntryView.vue` for receipt-first intake with interactive AI scan triggers and automatic form cascading.

### 4.1 Update `ImportView.vue` for Multi-File Receipt Staging & Batch Feedback
- In [`web/src/views/ImportView.vue`](file:///D:/src/personal/wrangler/web/src/views/ImportView.vue):
  - Update `importerFile` state type: `const importerFile = ref<File | File[] | null>(null)`.
  - Update `<q-file>` input in the importer bar:
    - `:multiple="selectedImporter?.importer_id === 'receipt_parser'"`
    - `:use-chips="true"`
    - Display file count caption when multiple files are selected.
  - Update `onRunImporter()`:
    - If `result.failed_files?.length > 0` or `result.skipped_duplicates > 0`: display warning toast (`notifyWarning`) summarizing staged count, skipped count, and failure details.
    - Otherwise display positive toast (`notifySuccess`).
    - Clear `importerFile` and refresh staging table.

### 4.2 Restructure `ManualEntryView.vue` for Receipt-First Layout & AI Auto-Fill
- In [`web/src/views/ManualEntryView.vue`](file:///D:/src/personal/wrangler/web/src/views/ManualEntryView.vue):
  - Reorder form card layout (Receipt-First Intake):
    - **Row 1:** Receipt Attachment (`<q-file>`) with inline AI Scan trigger.
    - **Row 2:** Date (`YYYY-MM-DD`) and Amount (`$`).
    - **Row 3:** Description / Payee.
    - **Row 4:** Allocations (Splits).
  - Add inline scan button in `#after` slot of `<q-file>`:
    - Icon `auto_awesome`, color `primary`, `:loading="isParsingReceipt"`, `:disable="!form.receipt_file"`, `data-testid="btn-scan-receipt"`.
    - Tooltip: `"Scan & Auto-Fill with AI"`.
  - Maintain programmatic initial focus on the Date input so manual keyboard workflows remain uninhibited.
  - Implement `isParsingReceipt = ref(false)` and `async function parseCurrentReceipt()`:
    - Invoke `transactionStore.parseReceipt(form.value.receipt_file)`.
    - Cascade extracted values downward:
      - `if (parsed.date) form.value.date = parsed.date`
      - `if (parsed.description) form.value.description = parsed.description; else if (parsed.merchant) form.value.description = parsed.merchant`
      - `if (parsed.total_amount) form.value.total_amount = String(parsed.total_amount)`
      - If `form.value.splits.length === 1`, split 0 automatically synchronizes with `total_amount`.
    - Display success notification: `notifySuccess("Receipt parsed! Please verify details.")`.
    - Display error notification on failure: `notifyError(err.message || "Failed to parse receipt")`.
  - Auto-trigger scan on file drop or selection via `@update:model-value="onReceiptSelected"`.
  - Expose `parseCurrentReceipt` and `isParsingReceipt` in `defineExpose`.

### 4.3 Frontend Component Test Suite for Receipt Import and Manual Entry Auto-Fill
- Create [`web/tests/receiptUi.test.ts`](file:///D:/src/personal/wrangler/web/tests/receiptUi.test.ts):
  - Test `ManualEntryView` component:
    - Verify Row 1 renders receipt attachment input (`input-receipt-file`) and scan button (`btn-scan-receipt`).
    - Verify triggering receipt scan populates date, total_amount, description, and synchronizes split amount.
    - Verify Date input receives initial focus on mount for manual keyboard entry.
  - Test `ImportView` component:
    - Verify `<q-file>` enables `:multiple` when `selectedImporter.importer_id === 'receipt_parser'`.
    - Verify batch run with partial failures invokes warning notification.
