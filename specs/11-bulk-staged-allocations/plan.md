# Implementation Plan: Staged Bulk Allocations & Actions

## Phase 1: Backend Schemas, Endpoints & Automated Pytest Suite

### 1.1 Request and Response Pydantic Schemas for Bulk Staging Actions
- **File:** [`api/src/schemas/staging.py`](file:///D:/src/personal/wrangler/api/src/schemas/staging.py)
- **Description:** Implement request and response Pydantic models for bulk allocate and bulk dismiss operations.
- **Details:**
  - Define `StagedBulkAllocateRequest(BaseModel)` with fields:
    - `staged_transaction_ids: list[uuid.UUID]`
    - `is_personal: bool = False`
    - `company_id: uuid.UUID | None = None`
    - `clear: bool = False`
  - Add `@model_validator(mode="after")` to `StagedBulkAllocateRequest` enforcing:
    - When `clear=True`, `is_personal` must be `False` and `company_id` must be `None`.
    - When `clear=False`, exactly one of `is_personal=True` or `company_id is not None` must be specified.
  - Define `StagedBulkAllocateResponse(BaseModel)` with fields:
    - `updated_count: int`
    - `staged_transaction_ids: list[uuid.UUID]`
  - Define `StagedBulkDismissRequest(BaseModel)` with field:
    - `staged_transaction_ids: list[uuid.UUID]`
  - Define `StagedBulkDismissResponse(BaseModel)` with fields:
    - `dismissed_count: int`
    - `staged_transaction_ids: list[uuid.UUID]`
    - `marked_imported_count: int`
    - `mark_imported_errors: list[str]`

### 1.2 Bulk Allocation Endpoint in Staging Router
- **File:** [`api/src/routers/staging.py`](file:///D:/src/personal/wrangler/api/src/routers/staging.py)
- **Description:** Implement the `POST /api/staging/bulk-allocate` endpoint to replace allocations atomically across multiple staged transactions.
- **Details:**
  - Route: `@router.post("/bulk-allocate", response_model=StagedBulkAllocateResponse)`
  - Validate that `payload.staged_transaction_ids` is non-empty; raise `HTTPException(status_code=400, detail="staged_transaction_ids must not be empty")` if empty.
  - If `payload.company_id is not None`, verify the company exists via `db.get(Company, payload.company_id)`; raise `HTTPException(status_code=400, detail="Company not found")` if missing.
  - Fetch matching `StagedTransaction` records using `select(StagedTransaction).options(selectinload(StagedTransaction.allocations)).where(StagedTransaction.id.in_(payload.staged_transaction_ids))` and filter to rows where `status == "STAGED"`.
  - For each qualifying staged transaction:
    - Clear existing allocations via `staged_tx.allocations.clear()`.
    - If `payload.clear is False`:
      - Validate `staged_tx.total_amount` is not None and not 0; raise `HTTPException(status_code=400, detail="Cannot allocate staged transaction without a total amount")` if missing or zero.
      - Instantiate and append a new `StagedAllocation(id=uuid.uuid4(), staged_transaction_id=staged_tx.id, amount=staged_tx.total_amount, is_personal=payload.is_personal, company_id=payload.company_id)`.
  - Commit the database session atomically.
  - Return `StagedBulkAllocateResponse(updated_count=len(qualifying_staged), staged_transaction_ids=[stx.id for stx in qualifying_staged])`.

### 1.3 Bulk Dismiss Endpoint in Staging Router
- **File:** [`api/src/routers/staging.py`](file:///D:/src/personal/wrangler/api/src/routers/staging.py)
- **Description:** Implement the `POST /api/staging/bulk-dismiss` endpoint to dismiss transactions and trigger external importer `mark_as_imported` hooks.
- **Details:**
  - Route: `@router.post("/bulk-dismiss", response_model=StagedBulkDismissResponse)`
  - Validate that `payload.staged_transaction_ids` is non-empty; raise `HTTPException(status_code=400, detail="staged_transaction_ids must not be empty")` if empty.
  - Fetch matching `StagedTransaction` records where `StagedTransaction.id.in_(payload.staged_transaction_ids)` and `StagedTransaction.status == "STAGED"`.
  - For each qualifying transaction:
    - Clear allocations: `staged_tx.allocations.clear()`.
    - Clean up unaccepted receipt: if `staged_tx.receipt_file_path` exists, invoke `delete_receipt_file(staged_tx.receipt_file_path)` and set `staged_tx.receipt_file_path = None`.
    - Set `staged_tx.status = "DISMISSED"`.
    - Add to session: `db.add(staged_tx)`.
  - Commit database changes atomically.
  - Group qualifying transactions that have non-null `external_id` and `is_marked_imported is False` by `source`.
  - For each source group:
    - Retrieve importer via `get_importer_by_source(source_name)`.
    - If importer exists and `importer.supports_mark_imported` is True, invoke `await importer.mark_as_imported(ext_ids)` inside a try/except block.
    - On success: set `row.is_marked_imported = True` for the group, commit to database, and increment `marked_imported_count`.
    - On error: rollback group flag update and append `f"{source_name}: {exc}"` to `mark_imported_errors`.
  - Return `StagedBulkDismissResponse(dismissed_count=len(qualifying_staged), staged_transaction_ids=[stx.id for stx in qualifying_staged], marked_imported_count=marked_imported_count, mark_imported_errors=mark_imported_errors)`.

### 1.4 Backend Automated Pytest Suite
- **File:** [`api/tests/test_staging_api.py`](file:///D:/src/personal/wrangler/api/tests/test_staging_api.py)
- **Description:** Add automated test cases to verify bulk allocation, bulk dismissal, validation logic, and importer hook integration.
- **Details:**
  - Test `test_bulk_allocate_personal`: Verifies that multiple staged transactions are allocated 100% to Personal, have `is_ready` dynamically computed as `True`, and previous splits are replaced.
  - Test `test_bulk_allocate_company`: Verifies that multiple staged transactions are allocated 100% to a specified company ID.
  - Test `test_bulk_allocate_clear`: Verifies that clearing allocations empties the `allocations` relationship and sets `is_ready` to `False`.
  - Test `test_bulk_allocate_overwrites_existing_splits`: Verifies that multi-split staged transactions are overwritten with a single 100% allocation.
  - Test `test_bulk_allocate_skips_non_staged`: Verifies that transactions with `ACCEPTED` or `DISMISSED` status are ignored/skipped during bulk allocation.
  - Test `test_bulk_allocate_validation_errors`: Verifies rejection of invalid payloads (empty list, specifying both personal and company, specifying clear with company/personal, omitting all entity fields, non-existent company ID, transactions with missing `total_amount`).
  - Test `test_bulk_dismiss`: Verifies status transitions to `DISMISSED`, unaccepted receipt files are removed, allocations cleared, and `mark_as_imported` is invoked for compatible sources.
  - Test `test_bulk_dismiss_handles_importer_error`: Verifies that errors during `mark_as_imported` are aggregated into `mark_imported_errors` while leaving transaction status as `DISMISSED`.

---

## Phase 2: Frontend Data Contracts & Store Methods

### 2.1 Frontend TypeScript Types
- **File:** [`web/src/types/staging.ts`](file:///D:/src/personal/wrangler/web/src/types/staging.ts)
- **Description:** Define TypeScript interfaces for the bulk allocate and bulk dismiss payloads and responses.
- **Details:**
  - Add `StagedBulkAllocateRequest`:
    ```typescript
    export interface StagedBulkAllocateRequest {
      staged_transaction_ids: string[]
      is_personal?: boolean
      company_id?: string | null
      clear?: boolean
    }
    ```
  - Add `StagedBulkAllocateResponse`:
    ```typescript
    export interface StagedBulkAllocateResponse {
      updated_count: number
      staged_transaction_ids: string[]
    }
    ```
  - Add `StagedBulkDismissRequest`:
    ```typescript
    export interface StagedBulkDismissRequest {
      staged_transaction_ids: string[]
    }
    ```
  - Add `StagedBulkDismissResponse`:
    ```typescript
    export interface StagedBulkDismissResponse {
      dismissed_count: number
      staged_transaction_ids: string[]
      marked_imported_count: number
      mark_imported_errors: string[]
    }
    ```

### 2.2 Staging Store Actions
- **File:** [`web/src/stores/staging.ts`](file:///D:/src/personal/wrangler/web/src/stores/staging.ts)
- **Description:** Implement `bulkAllocateStaged` and `bulkDismissStaged` actions in `useStagingStore`.
- **Details:**
  - Implement `bulkAllocateStaged(payload: StagedBulkAllocateRequest): Promise<StagedBulkAllocateResponse>` calling `POST /api/staging/bulk-allocate`.
  - Implement `bulkDismissStaged(stagedTransactionIds: string[]): Promise<StagedBulkDismissResponse>` calling `POST /api/staging/bulk-dismiss` with `{ staged_transaction_ids: stagedTransactionIds }`.
  - Ensure API error messages are captured into `error.value` and re-thrown.
  - Export both actions in the return object of `useStagingStore`.

---

## Phase 3: Bulk Allocation Dialog Component

### 3.1 Bulk Allocation Dialog Component & Logic
- **File:** [`web/src/components/BulkAllocateDialog.vue`](file:///D:/src/personal/wrangler/web/src/components/BulkAllocateDialog.vue)
- **Description:** Create the Quasar dialog component allowing users to set 100% allocation to Personal, a Company, or Clear across selected staged transactions.
- **Details:**
  - Component props:
    - `modelValue: boolean`
    - `selectedTransactions: StagedTransaction[]`
  - Component emits:
    - `(e: "update:modelValue", val: boolean): void`
    - `(e: "applied", count: number): void`
  - Dialog UI elements:
    - Title: "Bulk Allocate Transactions" with close button.
    - Subtitle: "Assign an entity to N selected staged transactions."
    - Notice Banner (conditional): Displayed with amber styling when any transaction in `selectedTransactions` has `allocations.length > 0` (`M of N transactions already have allocations or splits which will be overwritten`).
    - Entity Selector:
      - Radio options or select dropdown allowing selection of:
        - "Personal" (`is_personal: true`)
        - Active companies from `useCompanyStore().companies` (`company_id: string`)
        - "Unallocated / Clear" (`clear: true`)
    - Dialog actions:
      - "Cancel" button (`v-close-popup`, flat, grey).
      - "Apply Allocation" button (`unelevated`, primary, with loading state). Calls `stagingStore.bulkAllocateStaged()`, emits `applied`, notifies success, and closes dialog.

### 3.2 Bulk Allocation Dialog Automated Tests
- **File:** [`web/src/components/__tests__/BulkAllocateDialog.spec.ts`](file:///D:/src/personal/wrangler/web/src/components/__tests__/BulkAllocateDialog.spec.ts)
- **Description:** Write automated Vitest unit tests verifying the dialog behavior, entity choices, overwrite warning banner, and submit payloads.
- **Details:**
  - Verify that the overwrite notice banner is visible when at least one selected item has existing allocations, and hidden when all are unallocated.
  - Verify selecting Personal constructs payload with `is_personal: true, clear: false, company_id: null`.
  - Verify selecting a Company constructs payload with `is_personal: false, clear: false, company_id: '<selected_id>'`.
  - Verify selecting Unallocated constructs payload with `clear: true, is_personal: false, company_id: null`.
  - Verify clicking Apply dispatches `bulkAllocateStaged` with the expected payload and emits `applied`.
  - Verify clicking Cancel closes dialog without dispatching store action.

---

## Phase 4: Staging Table Selection & Contextual Bulk Action Bar in ImportView

### 4.1 Decoupled Selection & Master Header Checkbox
- **Files:**
  - [`web/src/views/ImportView.vue`](file:///D:/src/personal/wrangler/web/src/views/ImportView.vue)
  - [`web/src/views/importView.ts`](file:///D:/src/personal/wrangler/web/src/views/importView.ts)
- **Description:** Unlock row selection for all `STAGED` items and implement the master header selection checkbox.
- **Details:**
  - In `ImportView.vue` (`#body-cell-select`):
    - Remove the `!props.row.is_ready` condition from `:disable`. Row checkbox is enabled for any row with `props.row.status === 'STAGED'`.
    - Checkbox remains disabled only if `props.row.status !== 'STAGED'`.
  - In `ImportView.vue` (`#header-cell-select`):
    - Add header slot to `q-table` containing master `q-checkbox`.
    - Compute visible staged rows on the current page: `visibleStagedRows = stagedTransactions.filter(r => r.status === 'STAGED')`.
    - Compute `isHeaderChecked`: true when `visibleStagedRows.length > 0` and every visible staged row ID is in `selectedRowIds`.
    - Compute `isHeaderIndeterminate`: true when at least one (but not all) visible staged row ID is in `selectedRowIds`.
    - Bind `:disable="visibleStagedRows.length === 0"`.
    - Implement `toggleAllVisibleRows()`: if `isHeaderChecked` or `isHeaderIndeterminate` is true, uncheck all visible staged rows; otherwise add all visible staged row IDs to `selectedRowIds`.
  - Page/Filter Reset Logic:
    - Reset `selectedRowIds.value = []` when page number, page size, status filter, or source filter changes.

### 4.2 Contextual Bulk Action Toolbar & Dialog Integration
- **File:** [`web/src/views/ImportView.vue`](file:///D:/src/personal/wrangler/web/src/views/ImportView.vue)
- **Description:** Replace the single accept button with the contextual bulk action toolbar and connect the bulk allocation and dismissal flows.
- **Details:**
  - In `batch-action-bar`:
    - When `selectedRowIds.length === 0`:
      - Render default button: `[ Accept All Ready into Ledger (N) ]` where `N` is `readyAcceptCount`.
      - Tooltip: "Accept all N ready transactions on the current page into the Ledger".
      - Disabled when `N === 0`.
    - When `selectedRowIds.length > 0`:
      - Render selection count chip: `N selected` (`q-chip`, dense, color primary/blue-1, `data-testid="chip-selected-count"`).
      - Render `Bulk Allocate (N)` button (`q-btn`, primary, unelevated, `data-testid="btn-bulk-allocate"`). Opens `BulkAllocateDialog`.
      - Render `Accept Selected (K ready)` button (`q-btn`, positive, unelevated, `data-testid="btn-accept-selected"`). Where `K` is count of selected transactions with `is_ready === true`. Disabled if `K === 0` with tooltip "None of the selected transactions are ready to accept".
      - Render `Dismiss Selected (N)` button (`q-btn`, negative, flat or outline, `data-testid="btn-dismiss-selected"`). Prompts confirmation dialog via Quasar dialog plugin before dispatching `bulkDismissStaged`.
      - Render `Clear Selection` button (`q-btn`, flat, grey-7, label "Clear", `data-testid="btn-clear-selection"`). Clears `selectedRowIds.value = []`.
  - Wire actions:
    - Integrate `BulkAllocateDialog.vue`: pass `v-model="bulkAllocateDialogVisible"` and `selectedTransactions`. On `@applied`, refresh table and clear selection.
    - Wire `Accept Selected`: calls `onAcceptBatch()` targeting only selected ready transaction IDs.
    - Wire `Dismiss Selected`: prompts confirmation, calls `stagingStore.bulkDismissStaged(selectedRowIds.value)`, displays success/warning notifications, refreshes staging table, and resets selection.

### 4.3 Frontend Vitest Integration Tests
- **File:** [`web/tests/stagingBulkActions.test.ts`](file:///D:/src/personal/wrangler/web/tests/stagingBulkActions.test.ts)
- **Description:** Add comprehensive Vitest integration tests for selection behavior, contextual toolbar rendering, and bulk action triggers.
- **Details:**
  - Test header master checkbox states: checked when all visible staged rows selected, indeterminate when subset selected, unchecked when none selected, disabled when no staged rows visible.
  - Test row checkboxes: enabled for unallocated or ready STAGED items, disabled for ACCEPTED or DISMISSED items.
  - Test contextual action toolbar rendering: renders default `Accept All Ready into Ledger (N)` when `selectedRowIds` is empty, switches to bulk toolbar when rows are selected.
  - Test `Accept Selected (K ready)` button: correctly computes ready count `K`, disables when `K === 0`, and passes selected ready IDs upon click.
  - Test bulk dismiss confirmation dialog trigger and store dispatch.
  - Test selection reset on filter change and pagination request.
