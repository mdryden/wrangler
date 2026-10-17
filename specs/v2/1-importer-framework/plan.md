# Implementation Plan for Transaction Importer Framework & Staging

This document outlines the step-by-step implementation plan based on `spec.md`. The plan is divided into logical, deliverable-driven phases with atomic tasks in dependency order.

Each task is numbered by its phase and sequence number (e.g., `1.1`, `1.2`, `2.1`). Every task includes automated unit and integration test coverage in `api/tests/` or `web/src/` verified via `pnpm test`, `pnpm lint`, and `pnpm format`.

---

## Phase 1: Database Schema, ORM Models & Company Deletion Guard
*Goal: Define the SQLAlchemy ORM models for staged transactions and draft allocations, apply the database schema migration via Alembic, and block company deletion when referenced by staged allocations.*

### 1.1 Create `StagedTransaction` and `StagedAllocation` ORM models
- Create `api/src/models/staged_transaction.py` defining `StagedTransaction(Base)` mapped to `staged_transactions`:
  - `id`: `Mapped[uuid.UUID]` (`Uuid`, primary key, `default=uuid.uuid4`)
  - `source`: `Mapped[str]` (`String`, `nullable=False`, `index=True`)
  - `external_id`: `Mapped[str | None]` (`String`, `nullable=True`)
  - `date`: `Mapped[datetime.date]` (`Date`, `nullable=False`)
  - `description`: `Mapped[str]` (`String`, `nullable=False`)
  - `total_amount`: `Mapped[Decimal]` (`Numeric(12, 2)`, `nullable=False`)
  - `currency_code`: `Mapped[str]` (`String`, `nullable=False`, `default="CAD"`)
  - `receipt_file_path`: `Mapped[str | None]` (`String`, `nullable=True`)
  - `status`: `Mapped[str]` (`String`, `nullable=False`, `default="STAGED"`, `index=True`)
  - `is_marked_imported`: `Mapped[bool]` (`Boolean`, `nullable=False`, `default=False`)
  - `ledger_transaction_id`: `Mapped[uuid.UUID | None]` (`Uuid`, `ForeignKey("transactions.id", ondelete="SET NULL")`, `nullable=True`)
  - `created_at`: `Mapped[datetime.datetime]` (`DateTime`, `nullable=False`, `default=lambda: datetime.datetime.now(datetime.UTC)`)
  - Table constraint: `UniqueConstraint("source", "external_id", name="uq_staged_transactions_source_external_id")`
  - Relationship: `allocations: Mapped[list[StagedAllocation]] = relationship("StagedAllocation", back_populates="staged_transaction", cascade="all, delete-orphan")`
- Create `api/src/models/staged_allocation.py` defining `StagedAllocation(Base)` mapped to `staged_allocations`:
  - `id`: `Mapped[uuid.UUID]` (`Uuid`, primary key, `default=uuid.uuid4`)
  - `staged_transaction_id`: `Mapped[uuid.UUID]` (`Uuid`, `ForeignKey("staged_transactions.id", ondelete="CASCADE")`, `nullable=False`)
  - `amount`: `Mapped[Decimal]` (`Numeric(12, 2)`, `nullable=False`)
  - `is_personal`: `Mapped[bool]` (`Boolean`, `nullable=False`, `default=False`)
  - `company_id`: `Mapped[uuid.UUID | None]` (`Uuid`, `ForeignKey("companies.id", ondelete="RESTRICT")`, `nullable=True`)
  - Relationships: `staged_transaction: Mapped[StagedTransaction] = relationship("StagedTransaction", back_populates="allocations")` and `company: Mapped[Company | None] = relationship("Company")`
- Add unit tests in `api/tests/test_models.py` verifying model persistence, relationships, cascade deletion of `StagedAllocation` on `StagedTransaction` deletion, `SET NULL` when a linked `Transaction` is deleted, and the `(source, external_id)` unique constraint.

### 1.2 Generate and apply Alembic migration for staging tables
- Register `StagedTransaction` and `StagedAllocation` imports in `api/alembic/env.py` so Alembic tracks their metadata.
- Create a new Alembic migration in `api/alembic/versions/` creating the `staged_transactions` (with indexes on `source` and `status`, and unique constraint `uq_staged_transactions_source_external_id`) and `staged_allocations` tables.
- Add or update migration tests verifying `alembic upgrade head` creates both tables and constraints cleanly.

### 1.3 Enforce `StagedAllocation` reference check on `Company` deletion
- Update `delete_company` (`DELETE /api/companies/{company_id}`) in `api/src/routers/companies.py`:
  - Query `func.count(StagedAllocation.id).where(StagedAllocation.company_id == company_id)` in addition to `Allocation`.
  - Return HTTP `400 Bad Request` if the company is referenced by any `Allocation` or `StagedAllocation` record.
- Add test coverage in `api/tests/test_companies.py` verifying that a company referenced by a `StagedAllocation` cannot be deleted (`400 Bad Request`), and can be deleted (`204 No Content`) once the staged allocation is removed.

---

## Phase 2: Backend Importer Framework & Registry
*Goal: Build the extensible importer abstraction (`BaseImporter`), shared CSV parsing pipeline (`BaseCsvImporter`), and central importer registry.*

### 2.1 Implement core importer data structures, `ImporterValidationError`, and `BaseImporter` ABC
- Create `api/src/services/importers/base.py` containing:
  - `ImporterValidationError(Exception)` for signaling input/row validation failures (`400 Bad Request`).
  - `ImporterInputType(StrEnum)` with values `FILE = "file"` and `NONE = "none"`.
  - `ImporterReceiptData(BaseModel)` with `filename: str`, `content: bytes`, `content_type: str = "application/pdf"`.
  - `ImportedTransactionData(BaseModel)` with `external_id: str | None = None`, `date: date`, `description: str`, `total_amount: Decimal`, `currency_code: str = "CAD"`, `receipt: ImporterReceiptData | None = None`, `ConfigDict(from_attributes=True)`, and field validators ensuring `description` is stripped and non-empty and `total_amount` is strictly non-zero.
  - `BaseImporter(ABC)` defining:
    - Abstract properties: `importer_id: str`, `display_name: str`, `description: str`, `input_type: ImporterInputType`.
    - Concrete properties with defaults: `source_name: str` (returns `self.importer_id`), `accepted_file_types: list[str]` (returns `[]`), `supports_mark_imported: bool` (returns `False`).
    - Abstract method: `async def fetch_and_parse(self, file_bytes: bytes | None = None, filename: str | None = None) -> list[ImportedTransactionData]`.
    - Concrete hook: `async def mark_as_imported(self, external_ids: list[str]) -> None` defaulting to a no-op (`return None`).
- Add unit tests in `api/tests/test_importer_framework.py` testing `ImportedTransactionData` validation rules and `BaseImporter` default properties and `mark_as_imported` no-op behavior.

### 2.2 Implement `BaseCsvImporter` shared CSV pipeline and parsing utilities
- Create `api/src/services/importers/csv_base.py` defining `BaseCsvImporter(BaseImporter)`:
  - Fixed properties: `input_type = ImporterInputType.FILE` and `accepted_file_types = [".csv"]`.
  - Class attributes: `REQUIRED_COLUMNS: tuple[str, ...] = ()` and `SKIP_ZERO_AMOUNT_ROWS: bool = True`.
  - Static helper `parse_amount(raw: str) -> Decimal`: strips currency prefixes/symbols (`$`, `CAD`, `USD`), commas, whitespace, and converts parenthetical negatives like `(12.34)` to `-12.34`. Raises `ValueError` on empty or unparseable values.
  - Static helper `parse_iso_or_common_date(raw: str) -> date`: parses `YYYY-MM-DD`, `MM/DD/YYYY`, `YYYY/MM/DD`, or ISO timestamps (`YYYY-MM-DDTHH:MM:SS...`). Raises `ValueError` on invalid dates.
  - Shared `async def fetch_and_parse(self, file_bytes: bytes | None = None, filename: str | None = None) -> list[ImportedTransactionData]`:
    1. Verifies `file_bytes` is non-empty; otherwise raises `ImporterValidationError("CSV file is required and must not be empty")`.
    2. Decodes `file_bytes` using `"utf-8-sig"` with fallback to `"latin-1"`.
    3. Parses via `csv.DictReader(io.StringIO(decoded_text))`, normalizes header names (`header.strip()`), and verifies all `REQUIRED_COLUMNS` are present; if any are missing, raises `ImporterValidationError(f"Missing required CSV columns: {', '.join(missing)}")`.
    4. Iterates rows (1-indexed starting at row 2) with normalized keys/values, calling `self.parse_row(row_dict, row_number) -> ImportedTransactionData | None`.
    5. Skips rows where `parse_row` returns `None` (including zero-amount rows when `SKIP_ZERO_AMOUNT_ROWS` is `True`).
    6. Wraps `ValueError` or `ValidationError` raised in `parse_row` as `ImporterValidationError(f"Row {row_number}: {err}")`.
- Add unit tests in `api/tests/test_importer_framework.py` using a test `BaseCsvImporter` subclass covering UTF-8 BOM handling, Latin-1 fallback, missing required columns, parenthetical/currency amount parsing, date formats, zero-amount skipping, and row-level error reporting.

### 2.3 Implement Importer Registry
- Create `api/src/services/importers/registry.py`:
  - Maintain a registry of `BaseImporter` instances indexed by `importer_id` and lookup helper by `source_name`.
  - Provide helper functions: `register_importer(importer: BaseImporter) -> None`, `list_importers() -> list[BaseImporter]`, `get_importer(importer_id: str) -> BaseImporter | None`, and `get_importer_by_source(source_name: str) -> BaseImporter | None`.
- Add unit tests in `api/tests/test_importer_framework.py` verifying importer registration, discovery, and lookup by both `importer_id` and `source_name`.

---

## Phase 3: Backend Importer & Staging API Endpoints
*Goal: Expose the REST API endpoints for listing and running importers, managing staged transactions and receipts, dismissing/restoring rows, and batch-accepting ready transactions into the Ledger.*

### 3.1 Define Pydantic schemas for importers and staged transactions
- Create `api/src/schemas/importer.py`:
  - `ImporterMetadataResponse`: `importer_id: str`, `source_name: str`, `display_name: str`, `description: str`, `input_type: ImporterInputType`, `accepted_file_types: list[str]`, `supports_mark_imported: bool`.
  - `ImporterRunResponse`: `importer_id: str`, `total_parsed: int`, `staged_count: int`, `skipped_duplicates: int`, `items: list[StagedTransactionResponse]`.
- Create `api/src/schemas/staging.py`:
  - `StagedAllocationItem`: `id: uuid.UUID | None = None`, `amount: Decimal` (non-zero validator), `is_personal: bool = False`, `company_id: uuid.UUID | None = None`.
  - `StagedAllocationResponse`: `id: uuid.UUID`, `staged_transaction_id: uuid.UUID`, `amount: Decimal`, `is_personal: bool`, `company_id: uuid.UUID | None`, `ConfigDict(from_attributes=True)`.
  - `StagedTransactionUpdate`: optional `date: datetime.date | None = None`, `description: str | None = None` (non-empty validator when provided), `total_amount: Decimal | None = None` (non-zero validator when provided), `allocations: list[StagedAllocationItem] | None = None`, `remove_receipt: bool = False`.
  - `StagedTransactionResponse`: `id: uuid.UUID`, `source: str`, `external_id: str | None`, `date: datetime.date`, `description: str`, `total_amount: Decimal`, `currency_code: str`, `receipt_file_path: str | None`, `status: str`, `is_marked_imported: bool`, `ledger_transaction_id: uuid.UUID | None`, `created_at: datetime.datetime`, `allocations: list[StagedAllocationResponse]`, `is_ready: bool`, `supports_mark_imported: bool`, `mark_imported_error: str | None = None`.
  - `PaginatedStagedTransactionsResponse`: `items: list[StagedTransactionResponse]`, `total: int`, `page: int`, `page_size: int`, `total_pages: int`.
  - `StagingAcceptRequest`: `staged_transaction_ids: list[uuid.UUID] | None = None`.
  - `StagingAcceptResponse`: `accepted_count: int`, `ledger_transaction_ids: list[uuid.UUID]`, `marked_imported_count: int`, `mark_imported_errors: list[str]`.
- Implement a shared readiness helper function `compute_staged_is_ready(staged_tx: StagedTransaction) -> bool` enforcing all rules in Section 2.3.3 of the spec (`status == "STAGED"`, `len(allocations) >= 1`, `sum(a.amount) == total_amount`, multi-split all `is_personal == False` with `company_id is not None`, single-split either personal with `company_id is None` or business with `company_id is not None`).
- Add unit tests for schema validation and readiness computation.

### 3.2 Implement importer discovery and execution endpoints (`api/src/routers/importers.py`)
- Create `api/src/routers/importers.py` with prefix `/api/importers`:
  - `GET /api/importers`: Returns `list[ImporterMetadataResponse]` from the importer registry.
  - `POST /api/importers/{importer_id}/run`:
    - Looks up importer by `importer_id` (`404 Not Found` if unknown).
    - If `importer.input_type == ImporterInputType.FILE`, extracts uploaded file from `multipart/form-data` (`400 Bad Request` if missing) and reads `file_bytes` and `filename`.
    - If `importer.input_type == ImporterInputType.NONE`, accepts empty body or JSON `{}` without requiring a file.
    - Calls `await importer.fetch_and_parse(file_bytes, filename)`, catching `ImporterValidationError` and returning `400 Bad Request` with the error message.
    - Deduplicates each `ImportedTransactionData` item with a non-null `external_id` against:
      1. Earlier items in the same import batch (`seen_external_ids`).
      2. Existing `StagedTransaction` rows matching `(importer.source_name, item.external_id)` across all statuses (`STAGED`, `ACCEPTED`, `DISMISSED`).
      3. Existing Ledger `Transaction` rows matching `(importer.source_name, item.external_id)`.
    - Increments `skipped_duplicates` for any duplicate match.
    - For each new item:
      - Generates `staged_id = uuid.uuid4()`.
      - If `item.receipt` is present, writes `item.receipt.content` to `settings.RECEIPT_STORAGE_DIR` as `{staged_id}_{sanitize_filename(item.receipt.filename)}` and sets `receipt_file_path`.
      - Inserts `StagedTransaction(id=staged_id, source=importer.source_name, status="STAGED", ...)`.
    - Commits atomically and returns `ImporterRunResponse`.
- Register `importers_router` in `api/src/main.py`.
- Add integration tests in `api/tests/test_importers_api.py` using test importers (`FILE` and `NONE` input types) covering `GET /api/importers`, `POST /api/importers/{importer_id}/run`, intra-batch deduplication, deduplication against `STAGED`/`ACCEPTED`/`DISMISSED` rows and existing `Transaction` rows, receipt attachment persistence from an importer, and `400`/`404` error responses.

### 3.3 Implement staging list, update, and receipt management endpoints (`api/src/routers/staging.py`)
- Create `api/src/routers/staging.py` with prefix `/api/staging`:
  - `GET /api/staging`:
    - Query parameters: `status: str | None = "STAGED"`, `source: str | None = None`, `page: int = 1` (`ge=1`), `page_size: int = 50` (`ge=1, le=100`).
    - Returns `PaginatedStagedTransactionsResponse` ordered by `StagedTransaction.date.desc(), StagedTransaction.id.desc()`, populating `is_ready` and `supports_mark_imported` (via registry lookup on `source`).
  - `PUT /api/staging/{staged_id}`:
    - Supports both `application/json` and `multipart/form-data` (for simultaneous metadata/allocations update and receipt upload/removal, matching `PUT /api/transactions/{id}`).
    - Returns `404 Not Found` if `staged_id` does not exist; returns `400 Bad Request` if `staged_tx.status != "STAGED"`.
    - If `allocations` is provided as an empty list `[]`, clears all `StagedAllocation` rows on the staged transaction (resetting `is_ready = False`).
    - If `allocations` is provided and non-empty, validates:
      - `sum(alloc.amount) == effective_total_amount`
      - If `len(allocations) > 1`, all splits have `is_personal == False`.
      - Every business split (`is_personal == False`) has a non-null `company_id` referencing an existing `Company`.
      - Personal splits (`is_personal == True`) have `company_id = None`.
    - If `total_amount` is updated without providing `allocations` while existing allocations are present, validates existing allocations still sum to `effective_total_amount`.
    - Handles optional receipt upload (`save_receipt_file` + `delete_receipt_file` for old receipt) or `remove_receipt=True` (`delete_receipt_file` + `receipt_file_path = None`).
  - `POST /api/staging/{staged_id}/receipt` and `DELETE /api/staging/{staged_id}/receipt`:
    - Validates `status == "STAGED"` (`400 Bad Request` otherwise).
    - Uploads/replaces or deletes the receipt file in `RECEIPT_STORAGE_DIR` and returns the updated `StagedTransactionResponse`.
- Register `staging_router` in `api/src/main.py`.
- Add integration tests in `api/tests/test_staging_api.py` covering pagination, status/source filtering, metadata and allocation updates (single business, personal, multi-company split, clearing allocations with `[]`, invalid balance/company errors), and receipt upload/replacement/deletion.

### 3.4 Implement staging dismiss, restore, and batch ledger acceptance endpoints (`api/src/routers/staging.py`)
- In `api/src/routers/staging.py`, implement:
  - `POST /api/staging/{staged_id}/dismiss`:
    - Validates `staged_tx.status == "STAGED"` (`400 Bad Request` otherwise).
    - Clears `staged_tx.allocations`, deletes any unaccepted receipt file on disk via `delete_receipt_file(staged_tx.receipt_file_path)` and sets `receipt_file_path = None`, sets `status = "DISMISSED"`, and commits.
    - If the source importer has `supports_mark_imported == True`, `external_id` is non-null, and `is_marked_imported == False`, calls `await importer.mark_as_imported([external_id])`, sets `is_marked_imported = True`, and commits. If `mark_as_imported` raises an exception, catches it without rolling back the dismissal and populates `mark_imported_error: str` on the returned `StagedTransactionResponse`.
  - `POST /api/staging/{staged_id}/restore`:
    - Validates `staged_tx.status == "DISMISSED"` (`400 Bad Request` otherwise).
    - Sets `status = "STAGED"` (with zero allocations / `"Unallocated"` and preserving `is_marked_imported`), commits, and returns `StagedTransactionResponse`.
  - `POST /api/staging/accept`:
    - Accepts `StagingAcceptRequest` (`staged_transaction_ids: list[uuid.UUID] | None = None`).
    - When `staged_transaction_ids` is provided: fetches the requested records, verifying all exist (`404` if any missing), have `status == "STAGED"`, and satisfy `is_ready == True` (`400 Bad Request` detailing the unready transaction if any check fails).
    - When `staged_transaction_ids` is omitted or `None`: selects all `StagedTransaction` records with `status == "STAGED"` that satisfy `is_ready == True`.
    - In a single atomic database transaction:
      - For each target `StagedTransaction`, creates a Ledger `Transaction` (`source`, `external_id`, `date`, `description`, `total_amount`, `currency_code`, `receipt_file_path`) and corresponding `Allocation` records (`amount`, `is_personal`, `company_id`, `is_locked=False`).
      - Updates `staged_tx.status = "ACCEPTED"` and `staged_tx.ledger_transaction_id = tx.id`.
      - Commits the database transaction.
    - Groups accepted `StagedTransaction` rows with non-null `external_id` and `is_marked_imported == False` by `source`:
      - Resolves the importer from the registry and calls `await importer.mark_as_imported(external_ids)`.
      - Updates `is_marked_imported = True` on the corresponding `StagedTransaction` rows (when `supports_mark_imported == True` or after the hook completes) and commits.
      - If `mark_as_imported` raises an exception for a source, catches it, appends the error message to `mark_imported_errors`, and preserves the committed Ledger transactions.
    - Returns `StagingAcceptResponse`.
- Add integration tests in `api/tests/test_staging_api.py` covering dismiss (including receipt file deletion, allocation clearing, tombstone deduplication, and `mark_as_imported` success/error handling), restore, and batch acceptance (explicit IDs, accept-all-ready, unready rejection, atomic Ledger `Transaction` + `Allocation` creation, and `mark_as_imported` hook execution and error resilience).

---

## Phase 4: Frontend Import & Staging Workflow UI
*Goal: Build the top-level Import & Staging View, Importer Runner Panel, Staging Review Table with inline allocation controls, Staged Transaction & Allocation Editor Dialog, and Batch Action Bar.*

### 4.1 Define frontend TypeScript interfaces and Pinia store for importers and staging
- Create `web/src/types/staging.ts` defining:
  - `ImporterInputType` (`"file" | "none"`), `ImporterMetadata`, `ImporterRunResponse`.
  - `StagedStatus` (`"STAGED" | "ACCEPTED" | "DISMISSED"`), `StagedAllocation`, `StagedAllocationInput`, `StagedTransaction`, `PaginatedStagedTransactions`, `StagedTransactionUpdatePayload`, `StagingAcceptResponse`.
- Create `web/src/stores/staging.ts` (`useStagingStore`) providing state and actions for:
  - `importers: ImporterMetadata[]`, `loadingImporters: boolean`, `fetchImporters()` (`GET /api/importers`).
  - `runImporter(importerId: string, file?: File | null): Promise<ImporterRunResponse>` (`POST /api/importers/{importer_id}/run`).
  - `stagedTransactions: StagedTransaction[]`, `total: number`, `page: number`, `pageSize: number`, `totalPages: number`, `statusFilter: StagedStatus`, `sourceFilter: string | null`, `loadingStaging: boolean`.
  - `fetchStagedTransactions(params?)` (`GET /api/staging`).
  - `updateStagedTransaction(stagedId: string, payload: StagedTransactionUpdatePayload, receiptFile?: File | null)` (`PUT /api/staging/{staged_id}`).
  - `uploadStagedReceipt(stagedId: string, file: File)` (`POST /api/staging/{staged_id}/receipt`) and `deleteStagedReceipt(stagedId: string)` (`DELETE /api/staging/{staged_id}/receipt`).
  - `dismissStagedTransaction(stagedId: string)` (`POST /api/staging/{staged_id}/dismiss`).
  - `restoreStagedTransaction(stagedId: string)` (`POST /api/staging/{staged_id}/restore`).
  - `acceptStagedTransactions(stagedTransactionIds?: string[] | null)` (`POST /api/staging/accept`).
- Add unit tests in `web/src/stores/__tests__/staging.spec.ts` verifying store actions and API calls.

### 4.2 Register `/import` navigation item and route
- Update `web/src/layouts/nav.ts` to include `{ name: "import", label: "Import", icon: "cloud_upload", path: "/import" }`.
- Update `web/src/router/routes.ts` to register the child route `path: "import"`, `name: "import"`, `component: () => import("../views/ImportView.vue")`, `meta: { requiresAuth: true }`.
- Add or update unit tests verifying the navigation item and route configuration.

### 4.3 Build Staged Transaction & Allocation Editor Dialog
- Create `web/src/components/stagedTransactionEdit.ts` and `web/src/components/StagedTransactionEditDialog.vue`:
  - Supports editing `date`, `description`, `total_amount`, draft allocations (single business, personal expense toggle, multi-company splits with real-time remainder balance validation, or clearing all allocations back to `"Unallocated"`), and receipt attachment/replacement/removal.
  - Submits updates via `useStagingStore().updateStagedTransaction(staged.id, payload, stagedReceiptFile)` and emits `saved`.
- Add unit tests in `web/src/components/__tests__/stagedTransactionEdit.spec.ts` testing state initialization (including unallocated rows with 0 splits), personal/business toggling, multi-company split validation, clearing allocations (`[]`), and payload generation.

### 4.4 Build Import & Staging View (`web/src/views/ImportView.vue`)
- Create `web/src/views/ImportView.vue` with:
  - **Importer Runner Panel**:
    - Importer select dropdown populated from `GET /api/importers` showing `display_name` and `description`.
    - Dynamic input control: renders a `q-file` picker restricted to `accepted_file_types.join(",")` when `input_type === "file"`, or hides the file picker and shows an integration source info badge when `input_type === "none"`.
    - Capability chip when `supports_mark_imported === true`: *"Automatically marks items as imported in source upon acceptance"*.
    - **"Run Importer"** button (disabled when no importer is selected or when `input_type === "file"` and no file is selected) that invokes `runImporter`, displays a toast summary (`"Imported X new transactions into staging (Y duplicates skipped)"`), and refreshes the Staging Table.
  - **Staging Review Table & Batch Action Bar**:
    - Filter controls for Status (`"STAGED"` default, `"DISMISSED"`, `"ACCEPTED"`) and Source.
    - Server-side pagination (`q-table`) displaying columns: Selection Checkbox (for ready `"STAGED"` rows), Date (`YYYY-MM-DD`), Description, Source, Amount, Allocation Status / Summary, Receipt, and Actions.
    - Allocation column: displays `"Unallocated"` warning badge when unallocated or positive badge (`"Personal"` or Company name(s)) when `is_ready === true`; for `"STAGED"` rows, provides an inline quick assignment selector (Personal or any Company, with clear option to reset to `"Unallocated"`) and an **"Edit / Split"** button opening `StagedTransactionEditDialog.vue`.
    - Receipt column: shows **"View Receipt"** button (opens receipt in a new tab using the authenticated receipt blob viewer) and replace/remove controls when present, or **"Attach Receipt"** button when absent on a `"STAGED"` row.
    - Actions column:
      - For `"STAGED"` rows: **"Edit / Split"** button and **"Dismiss"** button (`POST /api/staging/{id}/dismiss`, displaying a prominent warning notification if `mark_imported_error` is returned).
      - For `"DISMISSED"` rows: **"Restore"** button (`POST /api/staging/{id}/restore`).
    - Batch Action Bar: **"Accept Ready into Ledger (N)"** button that accepts selected ready staged transactions (or all ready staged transactions on the page/view), calls `POST /api/staging/accept`, displays a confirmation toast, alerts with a prominent warning notification if `mark_imported_errors` is non-empty, and refreshes the table.
- Add unit/component tests in `web/src/views/__tests__/importView.spec.ts` covering importer selection, dynamic file input vs. no-input rendering, inline allocation assignment, dismissal/restoration, and batch acceptance.
