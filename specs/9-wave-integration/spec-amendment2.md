---
status: Implemented
subsystems:
  - Accounting Export
  - Core Ledger & Allocations
amendments: []
supersedes: null
superseded_by: null
---

# Specification Amendment 2: Re-Syncing Unlocked Allocations to Wave

**Target Specification:** [`specs/9-wave-integration/spec.md`](file:///D:/src/personal/wrangler/specs/9-wave-integration/spec.md)  
**Status:** Implemented  
**Subsystems:** Accounting Export, Core Ledger & Allocations  
**Date:** 2026-10-21  

---

## 1. Context & Motivation

In the baseline Wave integration specification ([`specs/9-wave-integration/spec.md`](file:///D:/src/personal/wrangler/specs/9-wave-integration/spec.md), Sections 1.2 #7, 5.2, 6.3.2 #3, and 7.2), a strict defensive guard was established:
- Once an allocation was successfully synchronized to Wave, its Wave GraphQL transaction ID was saved to `allocations.wave_transaction_id`.
- If a user subsequently unlocked that allocation (`is_locked = False`), `wave_transaction_id` remained permanently attached.
- The backend synchronization endpoint ([`POST /api/companies/{id}/sync-wave`](file:///D:/src/personal/wrangler/api/src/routers/companies.py)) explicitly rejected any allocation where `wave_transaction_id is not None` with HTTP 400 (`"Allocation {id} was already synced to Wave"`).
- The Export Manager UI ([`ExportManagerView.vue`](file:///D:/src/personal/wrangler/web/src/views/ExportManagerView.vue)) rendered a blocking `"Already in Wave"` warning chip and disabled the row selection checkbox.

This design assumed users could never re-push a transaction from Wrangler. However, in standard user workflows:
1. A user unlocks a transaction in Wrangler to adjust splits, amounts, or receipts. Unlocking already presents an explicit warning modal:
   > *"If this transaction has already been imported into an external accounting system, you must also adjust or remove it there manually."*
2. The user heeds this warning and removes or adjusts the old transaction in Wave directly.
3. The user now needs to re-sync the revised, unlocked allocation from Wrangler back into Wave.
4. Currently, the system permanently blocks them from re-syncing because `wave_transaction_id` persists and trips the guard.

This amendment establishes that **once unlocked, nothing should stop a user from re-syncing**. When an allocation is unlocked, its `wave_transaction_id` is immediately cleared, resetting it to an active, selectable, and syncable state.

---

## 2. Summary of Changes

1. **`wave_transaction_id` Reset on Unlock:**
   - When an allocation is transitioned to unlocked (`is_locked = False`), `allocations.wave_transaction_id` is immediately reset to `None` (cleared).
   - This applies consistently across all unlock paths:
     - Individual allocation unlock via [`PUT /api/allocations/{id}/lock`](file:///D:/src/personal/wrangler/api/src/routers/allocations.py).
     - Entire transaction unlock via [`PUT /api/transactions/{id}/lock`](file:///D:/src/personal/wrangler/api/src/routers/transactions.py).
     - Batch company allocations unlock via [`POST /api/companies/{id}/unlock-allocations`](file:///D:/src/personal/wrangler/api/src/routers/companies.py).
2. **Backend Sync Validation Guard Update:**
   - In [`POST /api/companies/{id}/sync-wave`](file:///D:/src/personal/wrangler/api/src/routers/companies.py), remove the restriction that rejects unlocked allocations with existing `wave_transaction_id`s. Any unlocked allocation belonging to the company (`is_locked == False`) is eligible for Wave sync.
3. **Data Hygiene Migration:**
   - Create an Alembic data migration to clear `wave_transaction_id = NULL` for any pre-existing allocations in SQLite that currently have `is_locked = False` and `wave_transaction_id IS NOT NULL`.
4. **Export Manager UI & Helper Modernization:**
   - In [`web/src/views/exportManager.ts`](file:///D:/src/personal/wrangler/web/src/views/exportManager.ts):
     - Update `canSyncRowToWave(row)` to require only `!row.is_locked && Boolean(row.wave_category_id)`.
     - Deprecate or align `isWaveAlreadySynced(row)` so that unlocked rows are never marked as "Already Synced".
   - In [`web/src/views/ExportManagerView.vue`](file:///D:/src/personal/wrangler/web/src/views/ExportManagerView.vue):
     - Enable row checkboxes for all unlocked allocations (`:disable="props.row.is_locked"`).
     - Remove the blocking `"Already in Wave"` warning badge. Unlocked rows display the standard `"Unlocked"` badge.
     - Master "Select All" includes all unlocked, categorized allocations.
5. **Existing Warning Dialogue Preserved:**
   - The warning dialog in [`TransactionEditDialog.vue`](file:///D:/src/personal/wrangler/web/src/components/TransactionEditDialog.vue) ([`UNLOCK_WARNING_MESSAGE`](file:///D:/src/personal/wrangler/web/src/components/transactionEdit.ts)) remains the user safeguard reminding them to manually remove/adjust the transaction in Wave.

---

## 3. Data Model & Migration

### 3.1 Schema Invariants
- The `allocations` table schema remains structurally unchanged. The column `wave_transaction_id` remains `VARCHAR, nullable=True`.
- **New Invariant:** An allocation can only have a non-null `wave_transaction_id` if `is_locked == True`. If `is_locked == False`, `wave_transaction_id` must be `None` (`NULL`).

### 3.2 Data Hygiene Migration (Alembic)
To repair any legacy or transitional records created before this amendment where an allocation was unlocked while retaining its old `wave_transaction_id`:

- **Revision Script:** `api/alembic/versions/<revision>_reset_unlocked_wave_transaction_ids.py`
- **`upgrade()` Operations:**
  ```python
  def upgrade() -> None:
      op.execute(
          "UPDATE allocations SET wave_transaction_id = NULL WHERE is_locked = 0 AND wave_transaction_id IS NOT NULL"
      )
  ```
- **`downgrade()` Operations:**
  ```python
  def downgrade() -> None:
      # Data cleanup is irreversible; no-op on downgrade
      pass
  ```

---

## 4. Backend Service & API Specification

### 4.1 Allocation Lock Endpoint ([`api/src/routers/allocations.py`](file:///D:/src/personal/wrangler/api/src/routers/allocations.py))

#### `PUT /api/allocations/{allocation_id}/lock`
When `payload.is_locked == False`:
1. Update `allocation.is_locked = False`.
2. Clear `allocation.wave_transaction_id = None`.
3. Commit and refresh the record.

```python
@router.put("/{allocation_id}/lock", response_model=AllocationResponse)
def update_allocation_lock(
    allocation_id: uuid.UUID,
    payload: LockUpdateRequest,
    db: Annotated[Session, Depends(get_db)],
) -> Allocation:
    allocation = db.get(Allocation, allocation_id)
    if allocation is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Allocation with ID '{allocation_id}' not found",
        )

    allocation.is_locked = payload.is_locked
    if not payload.is_locked:
        allocation.wave_transaction_id = None

    db.add(allocation)
    db.commit()
    db.refresh(allocation)
    return allocation
```

### 4.2 Transaction Lock Endpoint ([`api/src/routers/transactions.py`](file:///D:/src/personal/wrangler/api/src/routers/transactions.py))

#### `PUT /api/transactions/{transaction_id}/lock`
When `payload.is_locked == False`:
1. Iterate across all child allocations in `transaction.allocations`.
2. Set `alloc.is_locked = False`.
3. Clear `alloc.wave_transaction_id = None`.
4. Commit and refresh the transaction.

```python
@router.put("/{transaction_id}/lock", response_model=TransactionResponse)
def update_transaction_lock(
    transaction_id: uuid.UUID,
    payload: LockUpdateRequest,
    db: Annotated[Session, Depends(get_db)],
) -> Transaction:
    stmt = select(Transaction).options(selectinload(Transaction.allocations)).where(Transaction.id == transaction_id)
    transaction = db.scalar(stmt)
    if transaction is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Transaction with ID '{transaction_id}' not found",
        )

    for alloc in transaction.allocations:
        alloc.is_locked = payload.is_locked
        if not payload.is_locked:
            alloc.wave_transaction_id = None
        db.add(alloc)

    db.add(transaction)
    db.commit()
    db.refresh(transaction)
    return transaction
```

### 4.3 Company Batch Unlock Endpoint ([`api/src/routers/companies.py`](file:///D:/src/personal/wrangler/api/src/routers/companies.py))

#### `POST /api/companies/{company_id}/unlock-allocations`
When batch unlocking company allocations:
1. For every targeted allocation:
   - Set `alloc.is_locked = False`.
   - Clear `alloc.wave_transaction_id = None`.
2. Commit and return the unlocked allocations.

```python
@router.post("/{company_id}/unlock-allocations", response_model=list[AllocationResponse])
def unlock_company_allocations(
    company_id: uuid.UUID,
    db: Annotated[Session, Depends(get_db)],
    payload: Annotated[CompanyLockBatchRequest | None, Body()] = None,
) -> list[Allocation]:
    company = db.get(Company, company_id)
    if company is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Company with ID '{company_id}' not found",
        )

    stmt = select(Allocation).where(
        Allocation.company_id == company_id,
        Allocation.is_personal.is_(False),
    )
    if payload is not None and payload.allocation_ids:
        stmt = stmt.where(Allocation.id.in_(payload.allocation_ids))
    else:
        stmt = stmt.where(Allocation.is_locked.is_(True))

    allocations = list(db.scalars(stmt).all())
    for alloc in allocations:
        alloc.is_locked = False
        alloc.wave_transaction_id = None
        db.add(alloc)

    db.commit()
    for alloc in allocations:
        db.refresh(alloc)

    return allocations
```

### 4.4 Wave Sync Endpoint ([`api/src/routers/companies.py`](file:///D:/src/personal/wrangler/api/src/routers/companies.py))

#### `POST /api/companies/{company_id}/sync-wave`
1. **Remove Pre-Flight `already_synced` Rejection:**
   Remove lines 437–451 and 480–484 which previously raised HTTP 400 when `Allocation.wave_transaction_id.is_not(None)`.
2. **Target Filtering:**
   The filter remains strictly:
   ```python
   filters = [
       Allocation.company_id == company_id,
       Allocation.is_personal.is_(False),
       Allocation.is_locked.is_(False),
   ]
   ```
   Any unlocked allocation is considered eligible. If an allocation somehow has a lingering `wave_transaction_id` (e.g. from prior unmigrated state), it is cleared/overwritten upon successful sync.
3. **Execution & Idempotency Key:**
   - Transaction payload generation retains `externalId = f"wrangler_{alloc.id}"`.
   - Upon successful Wave `moneyTransactionCreate`:
     - `alloc.is_locked = True`
     - `alloc.wave_transaction_id = wave_tx_id`
     - Commit immediately to SQLite.

---

## 5. Frontend UI & State Updates

### 5.1 Helper Functions ([`web/src/views/exportManager.ts`](file:///D:/src/personal/wrangler/web/src/views/exportManager.ts))

Update sync evaluation logic:

```typescript
/**
 * Determines whether a row is eligible to be selected and synced to Wave.
 * A row is eligible if it is unlocked and has an assigned Wave category.
 */
export function canSyncRowToWave(row: ExportAllocationRow): boolean {
  return Boolean(!row.is_locked && row.wave_category_id)
}

/**
 * Legacy check retained for backwards compatibility with tests.
 * Since unlocked rows have wave_transaction_id reset to null, this returns false.
 */
export function isWaveAlreadySynced(row: ExportAllocationRow): boolean {
  return Boolean(!row.is_locked && row.wave_transaction_id)
}
```

### 5.2 Export Manager View ([`web/src/views/ExportManagerView.vue`](file:///D:/src/personal/wrangler/web/src/views/ExportManagerView.vue))

1. **Row Selection Checkbox:**
   Update the `:disable` binding to depend only on lock status:
   ```html
   <q-checkbox
     :model-value="isRowSelected(props.row)"
     :disable="props.row.is_locked"
     dense
     :data-testid="`checkbox-row-${props.row.id}`"
     @update:model-value="() => toggleRowSelect(props.row)"
   />
   ```
2. **Lock / Sync Status Column:**
   Simplify status chip presentation under Wave mode:
   - **`props.row.is_locked && props.row.wave_transaction_id`**: Display `"Synced to Wave"` (green chip with `check_circle` icon).
   - **`props.row.is_locked`**: Display `"Locked"` (amber chip with `lock` icon).
   - **`!props.row.is_locked`**: Display `"Unlocked"` (positive/green chip).
   - Remove the `"Already in Wave"` warning chip (`badge-already-in-wave`).

---

## 6. Superseded Clauses in Base Specification

This amendment explicitly modifies and supersedes the following clauses of [`specs/9-wave-integration/spec.md`](file:///D:/src/personal/wrangler/specs/9-wave-integration/spec.md):

| Base Spec Section | Original Clause | Superseded Clause (Amendment 2) |
| :--- | :--- | :--- |
| **Section 1.2, Item 7** | *"re-syncing previously pushed allocations is blocked with an 'Already in Wave' warning badge, directing users to make adjustments in Wave manually."* | **Unlocked allocations are re-syncable.** Unlocking clears `wave_transaction_id` and allows re-synchronization once adjustments are made. |
| **Section 5.2 (Pre-Flight)** | *"Any allocation where `wave_transaction_id is not None` is rejected (`Allocation {id} was already synced to Wave`)."* | **Removed.** Unlocked allocations (`is_locked == False`) are valid sync candidates regardless of prior sync history. |
| **Section 6.3.2, Item 3** | *"If `allocation.is_locked == False` and `wave_transaction_id is not None`: Displays `Already in Wave` (warning chip)... (Row checkbox disabled)."* | **Removed.** Unlocked rows have `wave_transaction_id = None`, display standard `"Unlocked"` badge, and have checkboxes enabled. |
| **Section 7.2** | *"If a synced transaction is unlocked in Wrangler, `wave_transaction_id` remains stored on the allocation. The UI blocks re-syncing to prevent duplicate creation."* | **`wave_transaction_id` is reset to `None` on unlock.** The UI and backend allow re-syncing. User warning occurs during the unlock confirmation modal. |

---

## 7. Test Suite Updates & Acceptance Criteria

### 7.1 Backend Tests (`api/tests/`)

1. **[`test_allocations.py`](file:///D:/src/personal/wrangler/api/tests/test_allocations.py):**
   - Locking an allocation with `is_locked = False` via `PUT /api/allocations/{id}/lock` resets `wave_transaction_id` to `None`.
2. **[`test_transactions.py`](file:///D:/src/personal/wrangler/api/tests/test_transactions.py):**
   - Unlocking a transaction via `PUT /api/transactions/{id}/lock` resets `wave_transaction_id` to `None` across all child allocations.
3. **[`test_companies.py`](file:///D:/src/personal/wrangler/api/tests/test_companies.py):**
   - Batch unlocking allocations via `POST /api/companies/{id}/unlock-allocations` resets `wave_transaction_id` to `None`.
4. **[`test_wave_sync_api.py`](file:///D:/src/personal/wrangler/api/tests/test_wave_sync_api.py):**
   - Update `test_sync_wave_duplicate_safeguard`: An unlocked allocation is permitted to re-sync. Verify that when synced, it receives a new `wave_transaction_id` and is locked again.
   - Assert `POST /api/companies/{id}/sync-wave` successfully processes allocations that were previously synced, unlocked, and re-submitted.
5. **[`test_migrations.py`](file:///D:/src/personal/wrangler/api/tests/test_migrations.py):**
   - Verify the data hygiene migration clears `wave_transaction_id` on pre-existing unlocked allocations in SQLite.

### 7.2 Frontend Tests (`web/tests/`)

1. **[`waveUi.test.ts`](file:///D:/src/personal/wrangler/web/tests/waveUi.test.ts):**
   - Update tests for `canSyncRowToWave`: Assert returns `true` for unlocked rows with categories regardless of previous sync history.
   - Assert row selection checkbox is enabled when `!row.is_locked`.
   - Assert `"Already in Wave"` warning badge is absent.
2. **[`waveStores.test.ts`](file:///D:/src/personal/wrangler/web/tests/waveStores.test.ts):**
   - Assert re-syncing unlocked allocations dispatches `syncWaveCompanyTransactions` with selected allocation IDs and updates local state.
