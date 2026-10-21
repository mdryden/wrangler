# Implementation Plan: Amendment 2 - Re-Syncing Unlocked Allocations to Wave

This implementation plan defines the deliverables required to allow re-synchronizing unlocked allocations to Wave by resetting `allocations.wave_transaction_id` on unlock, modernizing Wave sync validation guards, performing an Alembic data hygiene migration, and updating Export Manager UI selection and status chip presentation, as specified in [`specs/9-wave-integration/spec-amendment2.md`](file:///D:/src/personal/wrangler/specs/9-wave-integration/spec-amendment2.md).

Wrangler acts as an ingestion, deduplication, and entity attribution layer. In earlier iterations, allocations synced to Wave retained their `wave_transaction_id` permanently even when unlocked, blocking users from re-pushing corrected transactions. As defined in Amendment 2, once an allocation is unlocked, it can be re-synced to Wave. Unlocking clears the prior `wave_transaction_id`, allowing the allocation to be selected and re-submitted to Wave once any adjustments in Wave or Wrangler are complete. Furthermore, an Alembic data migration is provided to find and reset any pre-existing records currently in an inconsistent state (unlocked but retaining a Wave transaction ID).

The plan is divided into sequential, deliverable-driven phases with atomic implementation tasks in dependency order. Each task specifies concrete files, schemas, endpoints, or UI components along with automated test coverage adhering to development standards defined in [`AGENTS.md`](file:///D:/src/personal/wrangler/AGENTS.md) and architectural invariants in [`specs/ARCHITECTURE.md`](file:///D:/src/personal/wrangler/specs/ARCHITECTURE.md).

---

## Phase 1: Database Hygiene Migration

*Goal:* Implement an Alembic data migration to clear lingering `wave_transaction_id` values on pre-existing unlocked allocations in SQLite, ensuring schema invariants are satisfied across all existing records.

### 1.1 Create Alembic Data Migration to Reset Unlocked Wave Transaction IDs
- Create migration script in [`api/alembic/versions/`](file:///D:/src/personal/wrangler/api/alembic/versions/) revising current head `a1c4e9b8f3d2`:
  - **Down Revision:** `a1c4e9b8f3d2` (`rename wave_equity_account_id to wave_anchor_account_id`)
  - **Description:** `reset wave_transaction_id on unlocked allocations`
  - In `upgrade()`:
    - Execute SQL update statement:
      ```python
      op.execute(
          "UPDATE allocations SET wave_transaction_id = NULL WHERE is_locked = 0 AND wave_transaction_id IS NOT NULL"
      )
      ```
  - In `downgrade()`:
    - No-op (`pass`), as data hygiene reset is irreversible.
- Add migration test in [`api/tests/test_migrations.py`](file:///D:/src/personal/wrangler/api/tests/test_migrations.py):
  - In a new test `test_alembic_migration_reset_unlocked_wave_transaction_ids`:
    - Upgrade SQLite database to revision `a1c4e9b8f3d2`.
    - Insert sample transactions and allocations:
      - Allocation A: `is_locked = False`, `wave_transaction_id = "wave_tx_unlocked"`
      - Allocation B: `is_locked = True`, `wave_transaction_id = "wave_tx_locked"`
      - Allocation C: `is_locked = False`, `wave_transaction_id = None`
    - Run `command.upgrade(alembic_cfg, "head")`.
    - Verify Allocation A now has `wave_transaction_id IS NULL`.
    - Verify Allocation B retains `wave_transaction_id == "wave_tx_locked"`.
    - Verify Allocation C retains `wave_transaction_id IS NULL`.

---

## Phase 2: Backend Unlock Endpoints & Wave ID Reset

*Goal:* Update all allocation and transaction unlock mutation paths in the FastAPI backend to immediately clear `wave_transaction_id` when `is_locked` transitions to `False`.

### 2.1 Update Individual Allocation Unlock Endpoint
- In [`api/src/routers/allocations.py`](file:///D:/src/personal/wrangler/api/src/routers/allocations.py):
  - In `update_allocation_lock` (`PUT /api/allocations/{allocation_id}/lock`):
    - When `not payload.is_locked`:
      - Set `allocation.wave_transaction_id = None`.
- In [`api/tests/test_allocations.py`](file:///D:/src/personal/wrangler/api/tests/test_allocations.py):
  - In `test_lock_and_unlock_allocation_success`:
    - Seed an allocation with `is_locked = True` and `wave_transaction_id = "wave_sample_id"`.
    - Call `PUT /api/allocations/{id}/lock` with `{"is_locked": False}`.
    - Assert response contains `is_locked: false` and `wave_transaction_id: null`.
    - Refresh from `db_session` and assert database record has `allocation.wave_transaction_id is None`.

### 2.2 Update Parent Transaction Unlock Endpoint
- In [`api/src/routers/transactions.py`](file:///D:/src/personal/wrangler/api/src/routers/transactions.py):
  - In `update_transaction_lock` (`PUT /api/transactions/{transaction_id}/lock`):
    - When `not payload.is_locked`:
      - In the iteration over `transaction.allocations`, set `alloc.wave_transaction_id = None`.
- In [`api/tests/test_transactions.py`](file:///D:/src/personal/wrangler/api/tests/test_transactions.py):
  - In `test_transaction_lock_toggle`:
    - Seed a transaction whose child allocations have `is_locked = True` and populated `wave_transaction_id` values.
    - Call `PUT /api/transactions/{tx.id}/lock` with `{"is_locked": False}`.
    - Assert all child allocations in the response have `is_locked: false` and `wave_transaction_id: null`.
    - Refresh child allocations from database and assert `alloc.wave_transaction_id is None`.

### 2.3 Update Company Batch Unlock Allocations Endpoint
- In [`api/src/routers/companies.py`](file:///D:/src/personal/wrangler/api/src/routers/companies.py):
  - In `unlock_company_allocations` (`POST /api/companies/{company_id}/unlock-allocations`):
    - For each allocation in `allocations`:
      - Set `alloc.is_locked = False`.
      - Set `alloc.wave_transaction_id = None`.
      - Call `db.add(alloc)`.
- In [`api/tests/test_companies.py`](file:///D:/src/personal/wrangler/api/tests/test_companies.py):
  - In batch unlock tests (`test_unlock_allocations_all_locked_when_omitted_payload` and `test_unlock_allocations_specific_allocations`):
    - Seed allocations with `is_locked = True` and `wave_transaction_id = "wave_batch_id"`.
    - Call `POST /api/companies/{company_id}/unlock-allocations`.
    - Assert all returned allocations have `is_locked: false` and `wave_transaction_id: null`.
    - Refresh from database and verify `alloc.wave_transaction_id is None`.

---

## Phase 3: Wave Synchronization Re-Sync Validation Modernization

*Goal:* Update the backend Wave synchronization endpoint to permit re-syncing unlocked allocations regardless of prior sync history.

### 3.1 Modernize `POST /api/companies/{company_id}/sync-wave` Validation Guards
- In [`api/src/routers/companies.py`](file:///D:/src/personal/wrangler/api/src/routers/companies.py):
  - In `sync_wave` (`POST /api/companies/{company_id}/sync-wave`):
    - Remove the pre-flight `already_synced` query and HTTP 400 rejection (lines 437–451).
    - Remove the allocation loop check `if alloc.wave_transaction_id is not None: raise HTTPException(...)` (lines 479–484).
    - Retain unlocked eligibility filtering:
      ```python
      filters = [
          Allocation.company_id == company_id,
          Allocation.is_personal.is_(False),
          Allocation.is_locked.is_(False),
      ]
      ```
    - Retain atomic execution: upon successful `WaveClient.create_money_transaction`, update `alloc.is_locked = True` and `alloc.wave_transaction_id = wave_tx_id`, committing immediately to SQLite.
- In [`api/tests/test_wave_sync_api.py`](file:///D:/src/personal/wrangler/api/tests/test_wave_sync_api.py):
  - Replace `test_sync_wave_already_synced_safeguard` with `test_sync_wave_unlocked_re_sync`:
    - Seed an allocation with `is_locked = False` that previously had a sync history (or simulates a re-sync candidate).
    - Provide a mock `WaveClient.create_money_transaction` returning `"wave_re_sync_tx_id"`.
    - Call `POST /api/companies/{company.id}/sync-wave` with `allocation_ids=[alloc.id]`.
    - Assert response status is 200 with `synced_count: 1`, `failed_count: 0`.
    - Refresh allocation and assert `alloc.is_locked is True` and `alloc.wave_transaction_id == "wave_re_sync_tx_id"`.

---

## Phase 4: Frontend UI, Helper Modernization & Store Tests

*Goal:* Update Export Manager selection helpers, table columns, and status chip presentation to treat unlocked allocations as sync-eligible, eliminating the blocking `"Already in Wave"` badge.

### 4.1 Modernize Export Manager Helper Functions
- In [`web/src/views/exportManager.ts`](file:///D:/src/personal/wrangler/web/src/views/exportManager.ts):
  - Update `canSyncRowToWave`:
    ```typescript
    export function canSyncRowToWave(row: ExportAllocationRow): boolean {
      return Boolean(!row.is_locked && row.wave_category_id)
    }
    ```
  - Maintain `isWaveAlreadySynced` for backward compatibility:
    ```typescript
    export function isWaveAlreadySynced(row: ExportAllocationRow): boolean {
      return Boolean(!row.is_locked && row.wave_transaction_id)
    }
    ```
- In [`web/tests/waveUi.test.ts`](file:///D:/src/personal/wrangler/web/tests/waveUi.test.ts):
  - Update unit tests for `canSyncRowToWave`:
    - Assert `canSyncRowToWave` returns `true` for an unlocked row with an assigned `wave_category_id`, even if `wave_transaction_id` is present on a raw row object.
    - Assert `canSyncRowToWave` returns `false` when `row.is_locked === true` or `!row.wave_category_id`.

### 4.2 Update Export Manager View Table Checkbox & Status Chip Presentation
- In [`web/src/views/ExportManagerView.vue`](file:///D:/src/personal/wrangler/web/src/views/ExportManagerView.vue):
  - Update row checkbox `:disable` binding:
    ```html
    <q-checkbox
      :model-value="isRowSelected(props.row)"
      :disable="props.row.is_locked"
      dense
      :data-testid="`checkbox-row-${props.row.id}`"
      @update:model-value="() => toggleRowSelect(props.row)"
    />
    ```
  - Update `eligibleRows` computed property:
    ```typescript
    const eligibleRows = computed(() => allocationRows.value.filter(r => canSyncRowToWave(r)))
    ```
  - In `#body-cell-is_locked` template under Wave mode:
    - When `props.row.is_locked && props.row.wave_transaction_id`: render `"Synced to Wave"` badge (`data-testid="badge-synced-to-wave"`).
    - When `props.row.is_locked`: render `"Locked"` badge (`data-testid="badge-allocation-locked"`).
    - When `!props.row.is_locked`: render `"Unlocked"` badge (`data-testid="badge-allocation-unlocked"`).
    - Remove the `"Already in Wave"` warning badge (`data-testid="badge-already-in-wave"`).
- In [`web/tests/waveUi.test.ts`](file:///D:/src/personal/wrangler/web/tests/waveUi.test.ts):
  - Verify that for unlocked allocation rows, the checkbox is enabled (`:disable="false"`).
  - Verify that the `"Already in Wave"` badge is no longer rendered for unlocked allocations.
- In [`web/tests/waveStores.test.ts`](file:///D:/src/personal/wrangler/web/tests/waveStores.test.ts):
  - In `syncCompanyToWave` tests, verify that dispatching Wave sync for unlocked re-sync allocations passes their IDs to `/api/companies/{company_id}/sync-wave` and receives successful response data.
