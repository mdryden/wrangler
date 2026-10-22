# Implementation Plan: Streamlined Staging Intake & Ledger Investigation URLs

This implementation plan details the engineering tasks required to streamline intake for personal staged transactions (relaxing staging readiness, automated fallback description on acceptance) and preserve investigation URLs across the staging-to-ledger lifecycle.

---

## Phase 1: Database Model, Alembic Migration & Core Backend Schemas

### 1.1 SQLAlchemy Model Update: Add `url` Column to `Transaction`
- **File:** [`api/src/models/transaction.py`](file:///D:/src/personal/wrangler/api/src/models/transaction.py)
- **Description:** Extend the permanent ledger `Transaction` ORM model to persist investigation URLs.
- **Details:**
  - Import `String` from `sqlalchemy` (already present).
  - Add column:
    ```python
    url: Mapped[str | None] = mapped_column(String, nullable=True)
    ```
  - Place `url` directly after `receipt_file_path` to mirror [`StagedTransaction.url`](file:///D:/src/personal/wrangler/api/src/models/staged_transaction.py#L24).

### 1.2 Alembic Database Migration for `transactions.url`
- **File:** `api/alembic/versions/<revision_id>_add_url_to_transactions.py`
- **Description:** Create an Alembic schema migration script that alters the `transactions` table to add the nullable `url` column.
- **Details:**
  - Set `down_revision = "c7b9e2d1f4a6"` (the current Alembic head).
  - In `upgrade()`:
    ```python
    with op.batch_alter_table("transactions") as batch_op:
        batch_op.add_column(sa.Column("url", sa.String(), nullable=True))
    ```
  - In `downgrade()`:
    ```python
    with op.batch_alter_table("transactions") as batch_op:
        batch_op.drop_column("url")
    ```

### 1.3 Transaction Pydantic Schemas Update
- **File:** [`api/src/schemas/transaction.py`](file:///D:/src/personal/wrangler/api/src/schemas/transaction.py)
- **Description:** Expose `url` in transaction creation, update, and serialized response schemas.
- **Details:**
  - In `TransactionCreate`: add optional `url: str | None = None`. Add an empty-string validator or pre-validator to normalize empty string to `None`.
  - In `TransactionUpdate`: add optional `url: str | None = None`. Add an empty-string validator or pre-validator to normalize empty string to `None`.
  - In `TransactionResponse`: add `url: str | None = None` so `ConfigDict(from_attributes=True)` includes `url` in JSON responses.

### 1.4 Source Friendly Names & Fallback Description Utilities
- **File:** [`api/src/services/importers/registry.py`](file:///D:/src/personal/wrangler/api/src/services/importers/registry.py)
- **Description:** Implement extensible mapping and helper functions to derive human-readable names and personal fallback descriptions from importer source identifiers.
- **Details:**
  - Define `SOURCE_FRIENDLY_NAMES: dict[str, str]`:
    ```python
    SOURCE_FRIENDLY_NAMES: dict[str, str] = {
        "amazon_csv": "Amazon",
        "receipt_parser": "Receipt",
        "ai_receipt": "Receipt",
        "mcp": "AI Assistant",
        "manual": "Manual",
        "wrangler_csv": "Wrangler",
        "google_groups": "Google Groups",
    }
    ```
  - Define `get_source_friendly_name(source: str) -> str`:
    ```python
    def get_source_friendly_name(source: str) -> str:
        """Return friendly display name for source, falling back to title-cased source name."""
        return SOURCE_FRIENDLY_NAMES.get(source, source.replace("_", " ").title())
    ```
  - Define `format_personal_fallback_description(source: str) -> str`:
    ```python
    def format_personal_fallback_description(source: str) -> str:
        """Generate clean fallback description for personal transactions."""
        return f"{get_source_friendly_name(source)}: Personal"
    ```
  - Export these utilities so they can be consumed by [`api/src/routers/staging.py`](file:///D:/src/personal/wrangler/api/src/routers/staging.py).

### 1.5 Staging Readiness Invariant Relaxation (`compute_staged_is_ready`)
- **File:** [`api/src/schemas/staging.py`](file:///D:/src/personal/wrangler/api/src/schemas/staging.py)
- **Description:** Relax the staging readiness calculation so that transactions allocated 100% to Personal do not require a non-empty `description`.
- **Details:**
  - In `compute_staged_is_ready(staged_tx: StagedTransaction) -> bool`:
    - Ensure `staged_tx.status == "STAGED"`.
    - Ensure `staged_tx.date is not None` and `staged_tx.total_amount is not None`.
    - Validate allocations exist and sum exactly to `staged_tx.total_amount`.
    - Check if the allocation is 100% Personal:
      `is_personal_allocation = len(allocs) == 1 and allocs[0].is_personal and allocs[0].company_id is None`.
    - For business transactions (`not is_personal_allocation`), strictly require `bool(staged_tx.description and staged_tx.description.strip())`.
    - For 100% Personal transactions, allow `description` to be `None` or empty whitespace.
    - Check entity attribution invariant: at most one split per entity (at most one personal split and at most one company split).

### 1.6 Staging Acceptance Endpoint Enhancement (`POST /api/staging/accept`)
- **File:** [`api/src/routers/staging.py`](file:///D:/src/personal/wrangler/api/src/routers/staging.py)
- **Description:** Implement fallback description resolution and investigation URL transfer when committing ready staged items to the permanent ledger.
- **Details:**
  - Import `format_personal_fallback_description` from [`.services.importers.registry`](file:///D:/src/personal/wrangler/api/src/services/importers/registry.py).
  - In `accept_staged_transactions`:
    - When iterating over `target_staged` to instantiate `Transaction`:
      - Resolve description:
        ```python
        resolved_description = (stx.description or "").strip()
        if not resolved_description:
            is_personal = len(stx.allocations) == 1 and stx.allocations[0].is_personal
            if is_personal:
                resolved_description = format_personal_fallback_description(stx.source)
            else:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Staged transaction '{stx.id}' is missing a description",
                )
        ```
      - Copy `url=stx.url` into `Transaction(...)`.
      - Populate allocations, mark `stx.status = "ACCEPTED"`, and link `stx.ledger_transaction_id = tx_id`.

### 1.7 Core Transactions CRUD Endpoints Enhancement
- **File:** [`api/src/routers/transactions.py`](file:///D:/src/personal/wrangler/api/src/routers/transactions.py)
- **Description:** Support investigation URLs during manual transaction creation and updates.
- **Details:**
  - In `create_transaction`:
    - In multipart/form-data parsing, include `"url"` in `clean_dict` (normalizing empty strings to `None`).
    - Pass `url=payload.url` when constructing `Transaction(...)`.
  - In `update_transaction`:
    - In multipart/form-data parsing, include `"url"` in `clean_dict`.
    - Add `"url"` to `scalar_fields = ("date", "description", "total_amount", "source", "external_id", "receipt_file_path", "url")`.
    - Allow updating `url` (including clearing to `None`) when `"url"` is provided in `update_data`.

### 1.8 Backend Pytest Automated Test Suite
- **Files:** [`api/tests/test_staging_api.py`](file:///D:/src/personal/wrangler/api/tests/test_staging_api.py), [`api/tests/test_transactions.py`](file:///D:/src/personal/wrangler/api/tests/test_transactions.py)
- **Description:** Add comprehensive automated unit and API integration tests covering readiness, description fallbacks, and URL propagation.
- **Details:**
  - In `test_staging_api.py`:
    - `test_staged_is_ready_relaxed_for_100_percent_personal`: Verify `is_ready == True` when `description = None` and allocated 100% to Personal.
    - `test_staged_is_ready_rejected_for_business_missing_description`: Verify `is_ready == False` when `description = None` and allocated to a company.
    - `test_staged_is_ready_rejected_for_unallocated_missing_description`: Verify `is_ready == False` when unallocated.
    - `test_accept_personal_staged_uses_fallback_description`: Stage an item with `description = None`, `source = "amazon_csv"`, and personal allocation; call `POST /api/staging/accept`; verify response is 200 and created `Transaction.description == "Amazon: Personal"`.
    - `test_accept_personal_staged_unknown_source_title_cased`: Stage an item with `source = "my_custom_source"` and `description = None`; verify created `Transaction.description == "My Custom Source: Personal"`.
    - `test_accept_retains_explicit_description`: Verify an explicit description is retained verbatim when accepted.
    - `test_accept_persists_staging_url_to_ledger_transaction`: Stage an item with `url = "https://www.amazon.ca/orders/123"`; accept into ledger; verify `Transaction.url` equals the source URL.
  - In `test_transactions.py`:
    - Verify `POST /api/transactions` saves `url`.
    - Verify `PUT /api/transactions/{id}` updates and clears `url`.
    - Verify `GET /api/transactions/{id}` returns `url`.

---

## Phase 2: Frontend Data Types, Utilities & Dialog Form States

### 2.1 Transaction TypeScript Interfaces Update
- **File:** [`web/src/types/transaction.ts`](file:///D:/src/personal/wrangler/web/src/types/transaction.ts)
- **Description:** Add the `url` property to client transaction models and payloads.
- **Details:**
  - In `TransactionCreatePayload`: add optional `url?: string | null`.
  - In `TransactionUpdatePayload`: add optional `url?: string | null`.
  - In `Transaction`: add optional `url?: string | null`.

### 2.2 Frontend Source Friendly Names Utility
- **File:** [`web/src/views/importView.ts`](file:///D:/src/personal/wrangler/web/src/views/importView.ts)
- **Description:** Implement frontend source friendly-name mapping and helper function matching backend source formatting.
- **Details:**
  - Define and export `SOURCE_FRIENDLY_NAMES: Record<string, string>`:
    ```typescript
    export const SOURCE_FRIENDLY_NAMES: Record<string, string> = {
      amazon_csv: "Amazon",
      receipt_parser: "Receipt",
      ai_receipt: "Receipt",
      mcp: "AI Assistant",
      manual: "Manual",
      wrangler_csv: "Wrangler",
      google_groups: "Google Groups",
    }
    ```
  - Define and export `getSourceFriendlyName(source: string): string`:
    ```typescript
    export function getSourceFriendlyName(source: string): string {
      return SOURCE_FRIENDLY_NAMES[source] || source.replace(/_/g, " ").replace(/\b\w/g, c => c.toUpperCase())
    }
    ```

### 2.3 Staged Transaction Edit Form Validation & Payload Preparation
- **File:** [`web/src/components/stagedTransactionEdit.ts`](file:///D:/src/personal/wrangler/web/src/components/stagedTransactionEdit.ts)
- **Description:** Update form submission guards to allow saving personal staged transaction edits without a description.
- **Details:**
  - In `canSaveStagedTransactionEdit(state: StagedTransactionEditFormState)`:
    - Compute `isPersonal = state.is_personal || (state.splits.length === 1 && state.splits[0].is_personal)`.
    - If `!isPersonal && (!state.description || !state.description.trim())`, return `false`.
    - Allow empty `description` when `isPersonal` is `true`.
  - In `prepareStagedTransactionEditPayload(state: StagedTransactionEditFormState)`:
    - Set `description: state.description.trim() || null` (or trimmed string) so empty strings do not trigger backend validation errors.

### 2.4 Ledger Transaction Edit State & Payload Management
- **File:** [`web/src/components/transactionEdit.ts`](file:///D:/src/personal/wrangler/web/src/components/transactionEdit.ts)
- **Description:** Manage `url` state within the ledger transaction editor.
- **Details:**
  - Add `url: string` to `TransactionEditFormState`.
  - In `createTransactionEditState(tx: Transaction, defaultCompanyId: string | null = null)`:
    - Initialize `url: tx.url || ""`.
  - In `prepareTransactionEditPayload(state: TransactionEditFormState)`:
    - Include `url: state.url.trim() || null` in the returned JSON `TransactionUpdatePayload`.
    - If `state.staged_receipt_file` is present (multipart form-data), append `"url"` to `FormData` (`fd.append("url", state.url.trim())`).

### 2.5 Staged Transaction Edit Dialog Dynamic Validation UI
- **File:** [`web/src/components/StagedTransactionEditDialog.vue`](file:///D:/src/personal/wrangler/web/src/components/StagedTransactionEditDialog.vue)
- **Description:** Adjust description field validation and labels dynamically based on personal expense toggle state.
- **Details:**
  - In `<q-input v-model="form.description">`:
    - Dynamically set label: `:label="form.is_personal ? 'Description / Payee (Optional)' : 'Description / Payee *'"`.
    - Dynamically bind validation rules: `:rules="form.is_personal ? [] : descriptionRules"`.
  - In `onPersonalToggle`:
    - When switched to Personal, reset form validation (`formRef.value?.resetValidation()`) to clear any prior "Description is required" error messages.

### 2.6 Ledger Transaction Edit Dialog Investigation URL Input
- **File:** [`web/src/components/TransactionEditDialog.vue`](file:///D:/src/personal/wrangler/web/src/components/TransactionEditDialog.vue)
- **Description:** Add an investigation URL input field to the ledger edit dialog matching the staging editor affordance.
- **Details:**
  - In the metadata controls section (underneath or alongside `description`), add:
    ```html
    <q-input
      v-model="form.url"
      dense
      outlined
      label="Investigation URL"
      placeholder="https://..."
      data-testid="input-ledger-url"
      class="q-mb-sm"
    >
      <template #prepend>
        <q-icon name="link" />
      </template>
      <template #append v-if="form.url && form.url.trim()">
        <q-btn
          flat
          round
          dense
          size="sm"
          icon="open_in_new"
          color="primary"
          :href="form.url.trim()"
          target="_blank"
          rel="noopener noreferrer"
          data-testid="btn-ledger-open-url"
          @click.stop
        >
          <q-tooltip>Open URL</q-tooltip>
        </q-btn>
      </template>
    </q-input>
    ```

---

## Phase 3: Staging and Ledger View UI Integration & Frontend Vitest Suite

### 3.1 Staging Table Unlabelled Personal Transaction Description Fallback
- **File:** [`web/src/views/ImportView.vue`](file:///D:/src/personal/wrangler/web/src/views/ImportView.vue)
- **Description:** Display an intuitive pending personal description in the staging table when `description` is null and allocations are personal.
- **Details:**
  - Import `getSourceFriendlyName` from `./importView`.
  - In `#body-cell-description="props"`:
    - If `props.row.description`: render `props.row.description`.
    - Else if `props.row.allocations && props.row.allocations.length === 1 && props.row.allocations[0].is_personal`:
      render `<span class="text-italic text-grey-7">{{ getSourceFriendlyName(props.row.source) }}: Personal (Pending)</span>`.
    - Else render `<span class="text-italic text-grey-6">Unlabeled transaction</span>`.
  - Verify that when the user selects "Personal" in the quick-assign dropdown, the row's `is_ready` status updates reactively, the green `check_circle` badge renders, and the row becomes selectable for batch acceptance.

### 3.2 Ledger Table Investigation URL External Link Affordance
- **File:** [`web/src/views/LedgerView.vue`](file:///D:/src/personal/wrangler/web/src/views/LedgerView.vue)
- **Description:** Display an inline external link button in the description cell when `props.row.url` is present.
- **Details:**
  - In `#body-cell-description="props"`:
    - Replace the plain text div with a flex container:
      ```html
      <div class="row items-center q-gutter-xs no-wrap">
        <span :class="getTextWeightClass(props.row)">{{ props.row.description }}</span>
        <q-btn
          v-if="props.row.url"
          flat
          round
          dense
          size="xs"
          icon="open_in_new"
          color="primary"
          :href="props.row.url"
          target="_blank"
          rel="noopener noreferrer"
          data-testid="btn-ledger-open-url"
          @click.stop
        >
          <q-tooltip>Open Source URL</q-tooltip>
        </q-btn>
      </div>
      ```

### 3.3 Frontend Vitest Automated Test Suite
- **Files:**
  - [`web/src/components/__tests__/stagedTransactionEdit.test.ts`](file:///D:/src/personal/wrangler/web/src/components/__tests__/stagedTransactionEdit.test.ts)
  - [`web/tests/transaction.test.ts`](file:///D:/src/personal/wrangler/web/tests/transaction.test.ts)
  - [`web/src/views/__tests__/importView.spec.ts`](file:///D:/src/personal/wrangler/web/src/views/__tests__/importView.spec.ts)
  - [`web/tests/ledger.test.ts`](file:///D:/src/personal/wrangler/web/tests/ledger.test.ts)
- **Description:** Implement unit tests verifying personal description validation relaxation, URL form state preservation, and UI link affordances.
- **Details:**
  - In `stagedTransactionEdit.test.ts`:
    - Test `canSaveStagedTransactionEdit` returns `true` when `description == ""` and `is_personal == true`.
    - Test `canSaveStagedTransactionEdit` returns `false` when `description == ""` and `is_personal == false`.
    - Test `prepareStagedTransactionEditPayload` normalizes empty description for personal transactions.
  - In `transaction.test.ts`:
    - Test `createTransactionEditState` initializes `url` from `tx.url`.
    - Test `prepareTransactionEditPayload` includes `url` in JSON payload and FormData.
  - In `importView.spec.ts`:
    - Test `getSourceFriendlyName` maps `"amazon_csv"` to `"Amazon"`, `"receipt_parser"` to `"Receipt"`, and unknown sources to title-cased strings.
    - Test that selecting Personal for an unlabelled staged transaction updates `is_ready` to `true`.
  - In `ledger.test.ts`:
    - Verify description cell formatting and link presence logic for transactions with and without `url`.
