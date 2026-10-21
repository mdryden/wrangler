# Implementation Plan: Bulk Export Categorization

This implementation plan details the engineering deliverables required to deliver Bulk Export Categorization for Milestone v4, as defined in [`specs/12-bulk-export-categorization/spec.md`](file:///D:/src/personal/wrangler/specs/12-bulk-export-categorization/spec.md) and aligned with [`specs/ARCHITECTURE.md`](file:///D:/src/personal/wrangler/specs/ARCHITECTURE.md).

---

## Phase 1: Backend Bulk Category Assignment API

### 1.1 Bulk Category Request and Response Schemas
- **Target File:** [`api/src/schemas/allocation.py`](file:///D:/src/personal/wrangler/api/src/schemas/allocation.py)
- **Description:** Define Pydantic request and response schemas for bulk category assignment:
  - `BulkAllocationCategoryUpdateRequest`:
    - `allocation_ids: list[uuid.UUID]`
    - `wave_category_id: uuid.UUID`
    - `@field_validator("allocation_ids")`: Reject empty lists with a `ValueError("allocation_ids list cannot be empty")`.
  - `BulkAllocationCategoryUpdateResponse`:
    - `updated_count: int`
    - `allocation_ids: list[uuid.UUID]`

### 1.2 Bulk Category Endpoint Implementation
- **Target File:** [`api/src/routers/allocations.py`](file:///D:/src/personal/wrangler/api/src/routers/allocations.py)
- **Description:** Implement `POST /api/allocations/bulk-category` (`update_allocations_bulk_category`) adhering to the following invariants:
  1. Retrieve `WaveCategory` by `payload.wave_category_id`. If not found, raise HTTP 404 (`"WaveCategory with ID '{payload.wave_category_id}' not found"`).
  2. Query `Allocation` records matching `payload.allocation_ids`. If count does not match `len(payload.allocation_ids)`, raise HTTP 404 listing the missing IDs.
  3. Validate lock and entity ownership invariants across all queried allocations:
     - If any allocation is locked (`alloc.is_locked == True`), raise HTTP 400 (`"Allocation {alloc.id} is locked and cannot be modified"`).
     - If any allocation is personal (`alloc.is_personal == True`) or belongs to a different company (`alloc.company_id != category.company_id`), raise HTTP 400 (`"Allocation {alloc.id} does not belong to the category's company"`).
  4. Perform atomic update setting `alloc.wave_category_id = payload.wave_category_id` across all allocations and commit the transaction.
  5. Return `BulkAllocationCategoryUpdateResponse` with `updated_count` and list of updated `allocation_ids`.

### 1.3 Backend Bulk Category Pytest Suite
- **Target File:** [`api/tests/test_allocations.py`](file:///D:/src/personal/wrangler/api/tests/test_allocations.py)
- **Description:** Implement dedicated unit and integration tests for `POST /api/allocations/bulk-category`:
  - `test_bulk_category_success`: Provide multiple unlocked business allocations belonging to Company A and verify all receive the new `wave_category_id`.
  - `test_bulk_category_locked_allocation_rejected`: Include a locked allocation in the batch; verify HTTP 400 and ensure database state is unmutated.
  - `test_bulk_category_mismatched_company_rejected`: Provide an allocation belonging to Company B with a category belonging to Company A; verify HTTP 400.
  - `test_bulk_category_personal_allocation_rejected`: Include an allocation with `is_personal=True`; verify HTTP 400.
  - `test_bulk_category_invalid_category_id`: Non-existent `wave_category_id` returns HTTP 404.
  - `test_bulk_category_missing_allocations`: Non-existent allocation IDs return HTTP 404 detailing missing IDs.
  - `test_bulk_category_empty_list_rejected`: Empty `allocation_ids` payload returns HTTP 422 Unprocessable Entity.

---

## Phase 2: Frontend Data Layer & Export Manager Helpers

### 2.1 Wave & Allocation TypeScript Types
- **Target File:** [`web/src/types/wave.ts`](file:///D:/src/personal/wrangler/web/src/types/wave.ts)
- **Description:** Define TypeScript interfaces for bulk categorization payloads:
  - `BulkAllocationCategoryUpdateRequest`: `{ allocation_ids: string[]; wave_category_id: string }`
  - `BulkAllocationCategoryUpdateResponse`: `{ updated_count: number; allocation_ids: string[] }`

### 2.2 Export Manager Selection & Category Pure Helpers
- **Target File:** [`web/src/views/exportManager.ts`](file:///D:/src/personal/wrangler/web/src/views/exportManager.ts)
- **Description:** Implement and export pure utility functions for table selection, overwrite tracking, and sync readiness:
  - `isMasterHeaderChecked(visibleRowIds: string[], selectedRowIds: string[]): boolean`: Returns `true` if `visibleRowIds.length > 0` and every visible ID is present in `selectedRowIds`.
  - `isMasterHeaderIndeterminate(visibleRowIds: string[], selectedRowIds: string[]): boolean`: Returns `true` if some, but not all, visible IDs are present in `selectedRowIds` (`count > 0 && count < visibleRowIds.length`).
  - `countOverwrittenCategories(selectedRows: ExportAllocationRow[]): number`: Counts how many rows in `selectedRows` have a truthy `wave_category_id`.
  - `canSyncSelectedToWave(selectedRows: ExportAllocationRow[]): boolean`: Returns `true` if `selectedRows.length > 0` and every selected row has `!row.is_locked && Boolean(row.wave_category_id)`.

### 2.3 Transaction Store Batch Categorization Action
- **Target File:** [`web/src/stores/transactions.ts`](file:///D:/src/personal/wrangler/web/src/stores/transactions.ts)
- **Description:** Implement `bulkUpdateAllocationCategory` in Pinia transaction store:
  - Function signature: `async function bulkUpdateAllocationCategory(allocationIds: string[], waveCategoryId: string): Promise<BulkAllocationCategoryUpdateResponse>`.
  - Post request to `/api/allocations/bulk-category`.
  - On success, reactively update matching allocations in `transactions.value` with `wave_category_id = waveCategoryId`.
  - Manage error state and re-throw on failure.

### 2.4 Export Manager Helpers & Store Vitest Suite
- **Target File:** [`web/tests/exportManagerHelpers.test.ts`](file:///D:/src/personal/wrangler/web/tests/exportManagerHelpers.test.ts)
- **Description:** Add unit tests verifying:
  - `isMasterHeaderChecked`: Returns `true` when all visible unlocked rows are selected; `false` when none or subset selected; `false` when visible list is empty.
  - `isMasterHeaderIndeterminate`: Returns `true` for partial selections; `false` for empty or full selection.
  - `countOverwrittenCategories`: Accurately counts allocations with existing non-null `wave_category_id`.
  - `canSyncSelectedToWave`: Returns `true` only when all selected rows are unlocked and have a category assigned; `false` if any row is locked or uncategorized or selection is empty.
  - `bulkUpdateAllocationCategory`: Invokes API with expected payload and mutates matching in-memory allocations.

---

## Phase 3: Bulk Categorization Dialog Component

### 3.1 Bulk Categorization Dialog Component Implementation
- **Target File:** [`web/src/components/BulkCategorizeDialog.vue`](file:///D:/src/personal/wrangler/web/src/components/BulkCategorizeDialog.vue)
- **Description:** Create dialog matching the structural pattern of [`BulkAllocateDialog.vue`](file:///D:/src/personal/wrangler/web/src/components/BulkAllocateDialog.vue):
  - **Props:**
    - `modelValue: boolean`
    - `selectedRows: ExportAllocationRow[]`
    - `categories: WaveCategory[]`
  - **Emits:**
    - `update:modelValue(val: boolean)`
    - `applied(count: number)`
  - **Template & Controls:**
    - Card header with title `"Assign Category"` and subtitle `"Assign a Wave category to {N} selected transaction(s)."`.
    - Warning banner (`data-testid="banner-overwrite-warning"`, amber styling `bg-amber-1 text-amber-10`) conditionally rendered when `countOverwrittenCategories(selectedRows) > 0`: `"{M} of {N} selected transactions already have a category assigned which will be updated."`.
    - Category select `<q-select>` (`data-testid="select-bulk-category"`) with `dense`, `outlined`, `use-input`, `fill-input`, `hide-selected` to filter categories by name. Renders uncategorized system default account with distinct styling.
    - Actions:
      - Cancel button (`data-testid="btn-cancel-bulk-category"`): Closes dialog.
      - Apply button (`data-testid="btn-apply-bulk-category"`): Disabled when no category selected. Submits batch API call via `transactionStore.bulkUpdateAllocationCategory`, triggers success notification, emits `applied`, and closes dialog.

### 3.2 Bulk Categorize Dialog Vitest Suite
- **Target File:** [`web/tests/bulkCategorizeDialog.test.ts`](file:///D:/src/personal/wrangler/web/tests/bulkCategorizeDialog.test.ts)
- **Description:** Unit tests for `BulkCategorizeDialog.vue`:
  - Renders dialog header, item count, and searchable category options.
  - Overwrite banner visibility: Shown when `overwrittenCount > 0`, hidden when 0.
  - Form validation: Apply button is disabled when no category is selected.
  - Action dispatch: Selecting category and clicking Apply calls `bulkUpdateAllocationCategory`, notifies success, and emits `applied` and `update:modelValue(false)`.

---

## Phase 4: Export Manager View UI Integration

### 4.1 Decoupled Multi-Selection & Header Checkbox in ExportManagerView
- **Target File:** [`web/src/views/ExportManagerView.vue`](file:///D:/src/personal/wrangler/web/src/views/ExportManagerView.vue)
- **Description:** Decouple row checkbox selection from Wave category completeness:
  - Selection eligibility: Update row checkbox slot (`#body-cell-selection`) so any unlocked row (`props.row.is_locked === false`) is selectable, regardless of category assignment.
  - Header checkbox slot (`#header-cell-selection`):
    - Compute `visibleUnlockedRows = allocationRows.filter(r => !r.is_locked)`.
    - Bind header checkbox state to `isMasterHeaderChecked` and `isMasterHeaderIndeterminate`.
    - Disable header checkbox when `visibleUnlockedRows.length === 0`.
    - Clicking toggles between selecting all visible unlocked rows and deselecting visible rows on the current page.
  - Automatic selection reset: Clear `selectedRows` on pagination change (page or rowsPerPage), company change, or date filter updates.

### 4.2 Contextual Bulk Action Toolbar in ExportManagerView
- **Target File:** [`web/src/views/ExportManagerView.vue`](file:///D:/src/personal/wrangler/web/src/views/ExportManagerView.vue)
- **Description:** Replace standard action bar buttons with contextual bulk toolbar when `isWaveMode && selectedRows.length > 0`:
  - Selection count badge: `<q-chip color="primary" text-color="white" icon="check_circle" class="text-weight-bold" data-testid="chip-bulk-selected-count">N selected</q-chip>`.
  - Flexible spacer: `<q-space />`.
  - Assign Category button: `<q-btn unelevated color="primary" icon="label" label="Assign Category" data-testid="btn-bulk-assign-category" @click="showBulkCategorizeDialog = true" />`.
  - Sync to Wave button: `<q-btn unelevated color="primary" icon="cloud_upload" label="Sync to Wave" data-testid="btn-sync-to-wave" :disable="!canSyncSelectedToWave || syncingToWave" @click="onSyncToWave" />` with dynamic tooltips for categorized vs uncategorized selection states.
  - Mount `<BulkCategorizeDialog>` bound to `showBulkCategorizeDialog`, passing `selectedRows` and `cachedCategories`. On `applied`, show success toast, refresh allocation rows, and clear `selectedRows`.

### 4.3 Export Manager View Bulk Integration Vitest Suite
- **Target File:** [`web/tests/exportManagerViewBulk.test.ts`](file:///D:/src/personal/wrangler/web/tests/exportManagerViewBulk.test.ts)
- **Description:** Integration tests for `ExportManagerView.vue` testing:
  - Header checkbox 3-state rendering (checked, unchecked, indeterminate).
  - Unlocked uncategorized rows are selectable via checkbox.
  - Contextual toolbar renders count chip, Assign Category button, and Sync to Wave button when rows are selected in Wave mode.
  - "Assign Category" button opens `BulkCategorizeDialog`.
  - Sync to Wave button is disabled when selected rows contain uncategorized items, with appropriate tooltip.
  - Changing pages, page sizes, or filter controls resets `selectedRows`.
