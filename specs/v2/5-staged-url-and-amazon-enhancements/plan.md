# Implementation Plan: Staged Transaction URL & Amazon Importer Enhancements

This implementation plan details the engineering deliverables required to implement the Staged Transaction URL and Amazon CSV Importer Enhancements based on [`specs/v2/5-staged-url-and-amazon-enhancements/spec.md`](file:///D:/src/personal/wrangler/specs/v2/5-staged-url-and-amazon-enhancements/spec.md).

The plan is organized into sequential phases and atomic implementation tasks. Each task includes automated test coverage in [`api/tests/`](file:///D:/src/personal/wrangler/api/tests/) or [`web/src/`](file:///D:/src/personal/wrangler/web/src/) adhering to project conventions and development standards defined in [`AGENTS.md`](file:///D:/src/personal/wrangler/AGENTS.md).

---

## Phase 1: Database Model, Migration & Staging API URL Support

*Goal:* Add the staging-scoped nullable `url` column to `staged_transactions`, generate and apply the Alembic migration, update the importer framework item model, and extend the staging API schemas and update route.

### 1.1 Database Model & Alembic Migration for Staged Transaction URL
- In [`api/src/models/staged_transaction.py`](file:///D:/src/personal/wrangler/api/src/models/staged_transaction.py):
  - Add nullable `url` column: `url: Mapped[str | None] = mapped_column(String, nullable=True)`.
  - Maintain immutability rule: ledger [`Transaction`](file:///D:/src/personal/wrangler/api/src/models/transaction.py) remains unchanged without a `url` column.
- In [`api/alembic/versions/`](file:///D:/src/personal/wrangler/api/alembic/versions/):
  - Create migration script `e8a1f2c3b4d5_add_url_to_staged_transactions.py` with `down_revision = "b7d3e5f29a10"`.
  - In `upgrade()`, use `op.batch_alter_table("staged_transactions")` to add column `sa.Column("url", sa.String(), nullable=True)`.
  - In `downgrade()`, use `op.batch_alter_table("staged_transactions")` to drop column `"url"`.
- Automated test coverage in [`api/tests/test_staging.py`](file:///D:/src/personal/wrangler/api/tests/test_staging.py):
  - Verify `StagedTransaction` can be instantiated and persisted in SQLite with `url="https://amazon.ca/orders/123"`.
  - Verify default `url` is `None` when omitted.

### 1.2 Importer Framework & Execution Pipeline URL Ingestion
- In [`api/src/services/importers/base.py`](file:///D:/src/personal/wrangler/api/src/services/importers/base.py):
  - Add `url: str | None = None` to [`ImportedTransactionData`](file:///D:/src/personal/wrangler/api/src/services/importers/base.py#L27-L56).
  - Add `@field_validator("url", mode="before")` method `clean_url(cls, v: Any) -> str | None` that strips surrounding whitespace, single quotes, and double quotes, returning `None` if the resulting string is empty.
- In [`api/src/routers/importers.py`](file:///D:/src/personal/wrangler/api/src/routers/importers.py#L122-L136):
  - In `run_importer`, pass `url=item.url` when constructing [`StagedTransaction`](file:///D:/src/personal/wrangler/api/src/models/staged_transaction.py) instances from `parsed_items`.
- Automated test coverage in [`api/tests/test_importer_framework.py`](file:///D:/src/personal/wrangler/api/tests/test_importer_framework.py):
  - Verify `ImportedTransactionData` URL validator normalizes whitespace, quotes, and empty strings.
  - Verify existing importers ([`WranglerCsvImporter`](file:///D:/src/personal/wrangler/api/src/services/importers/wrangler_csv.py), [`GoogleGroupsImporter`](file:///D:/src/personal/wrangler/api/src/services/importers/google_groups.py)) default to `url=None`.

### 1.3 Staging Schemas & Staging Router URL Support
- In [`api/src/schemas/staging.py`](file:///D:/src/personal/wrangler/api/src/schemas/staging.py):
  - Add `url: str | None = None` to [`StagedTransactionResponse`](file:///D:/src/personal/wrangler/api/src/schemas/staging.py#L60-L79).
  - Add `url: str | None = None` to [`StagedTransactionUpdate`](file:///D:/src/personal/wrangler/api/src/schemas/staging.py#L35-L58) with a validator that strips whitespace and converts empty strings to `None`.
  - In `serialize_staged_transaction`, include `url=staged_tx.url`.
- In [`api/src/routers/staging.py`](file:///D:/src/personal/wrangler/api/src/routers/staging.py):
  - In `update_staged_transaction` (`PUT /api/staging/{staged_id}`):
    - When `"url" in update_data`, update `staged_tx.url = payload.url.strip() if payload.url else None`.
  - In `accept_staged_transactions` (`POST /api/staging/accept`):
    - Confirm ledger transaction creation remains unchanged and `url` is not propagated to ledger records.
- Automated test coverage in [`api/tests/test_staging.py`](file:///D:/src/personal/wrangler/api/tests/test_staging.py):
  - Test `GET /api/staging` returns serialized `url` field on staged transactions.
  - Test `PUT /api/staging/{id}` updates `url` to a new URL and allows clearing it to `null`.
  - Test `POST /api/staging/accept` accepts staged transactions with a URL and successfully creates ledger records without error.

---

## Phase 2: Amazon CSV Importer Enhancements

*Goal:* Update [`AmazonCsvImporter`](file:///D:/src/personal/wrangler/api/src/services/importers/amazon_csv.py) to skip intake of rows where the `vendor` column contains `"PrimeVideo"` or `"Audible"`, and parse comma-separated `order urls` to extract the primary order link.

### 2.1 Amazon CSV Importer Vendor Filtering & URL Extraction
- In [`api/src/services/importers/amazon_csv.py`](file:///D:/src/personal/wrangler/api/src/services/importers/amazon_csv.py):
  - In `parse_row(self, row: dict[str, str], row_number: int) -> ImportedTransactionData | None`:
    - **Vendor Filtering:**
      - Read `raw_vendor = row.get("vendor", "")`.
      - If `"PrimeVideo" in raw_vendor or "Audible" in raw_vendor`: return `None` immediately, skipping row completely prior to deduplication or staging.
    - **Order URL Extraction:**
      - Read `raw_urls = row.get("order urls", "").strip()`.
      - If non-empty:
        - Split candidate string by comma: `raw_urls.split(",")[0]`.
        - Strip surrounding whitespace, single quotes, and double quotes.
        - If cleaned candidate string is non-empty, assign to `parsed_url`; otherwise `None`.
    - Set `url=parsed_url` on the returned [`ImportedTransactionData`](file:///D:/src/personal/wrangler/api/src/services/importers/base.py#L27-L56).

### 2.2 Unit & Integration Tests for Amazon CSV Importer
- In [`api/tests/test_amazon_csv_importer.py`](file:///D:/src/personal/wrangler/api/tests/test_amazon_csv_importer.py):
  - **Vendor filtering tests:**
    - Test row with `vendor="PrimeVideo"` returns `None`.
    - Test row with `vendor="Amazon PrimeVideo CA"` returns `None`.
    - Test row with `vendor="Audible"` returns `None`.
    - Test row with `vendor="Audible.ca"` returns `None`.
    - Test row with `vendor="Amazon.ca"` or `vendor="AMZN Mktp CA"` parses normally.
    - Test row with `vendor="primevideo"` (case-sensitive) is not skipped and parses normally.
  - **URL extraction tests:**
    - Test single URL extracts cleanly.
    - Test comma-separated URLs (`"https://amazon.ca/order1, https://amazon.ca/order2"`) extracts `"https://amazon.ca/order1"`.
    - Test quoted URLs (`'"https://amazon.ca/order1", "https://amazon.ca/order2"'`) extracts `"https://amazon.ca/order1"`.
    - Test empty or whitespace-only URL sets `url=None`.
  - **Pipeline intake & deduplication tests:**
    - Test CSV upload via `POST /api/importers/amazon_csv/run` verifies `url` is persisted to `staged_transactions`.
    - Test skipped vendor rows are not counted in `staged_count` or tracked in deduplication keys.

---

## Phase 3: Frontend Type Definitions & Edit Dialog URL Support

*Goal:* Update frontend TypeScript types and the staged transaction edit state and dialog component to view, edit, and link to the investigation URL.

### 3.1 Frontend Staging Types & Form State URL Integration
- In [`web/src/types/staging.ts`](file:///D:/src/personal/wrangler/web/src/types/staging.ts):
  - Add `url: string | null` to `StagedTransaction`.
  - Add `url?: string | null` to `StagedTransactionUpdatePayload`.
- In [`web/src/components/stagedTransactionEdit.ts`](file:///D:/src/personal/wrangler/web/src/components/stagedTransactionEdit.ts):
  - Add `url: string` to `StagedTransactionEditFormState`.
  - In `createStagedTransactionEditState(staged: StagedTransaction)`: initialize `url: staged.url || ""`.
  - In `prepareStagedTransactionEditPayload(state: StagedTransactionEditFormState)`: include `url: state.url?.trim() || null` in returned payload.
- Automated test coverage in [`web/src/components/__tests__/stagedTransactionEdit.spec.ts`](file:///D:/src/personal/wrangler/web/src/components/__tests__/stagedTransactionEdit.spec.ts):
  - Verify `createStagedTransactionEditState` initializes `url` from staged transaction.
  - Verify `prepareStagedTransactionEditPayload` trims and outputs `url` or `null`.

### 3.2 Staged Transaction Edit Dialog URL Input Field
- In [`web/src/components/StagedTransactionEditDialog.vue`](file:///D:/src/personal/wrangler/web/src/components/StagedTransactionEditDialog.vue):
  - Update `form` ref initial state to include `url: ""`.
  - Add `q-input` for Investigation URL in dialog template below total amount / personal toggle:
    - `v-model="form.url"`, `dense`, `outlined`, `label="Investigation URL"`, `placeholder="https://..."`, `data-testid="input-staged-url"`, `class="q-mb-sm"`.
    - Prepend template with `<q-icon name="link" />`.
    - Append template with `<q-btn v-if="form.url" flat round dense size="sm" icon="open_in_new" :href="form.url" target="_blank" />`.
- Automated test coverage in [`web/src/components/__tests__/stagedTransactionEdit.spec.ts`](file:///D:/src/personal/wrangler/web/src/components/__tests__/stagedTransactionEdit.spec.ts):
  - Verify state updates and URL form handling.

---

## Phase 4: Responsive Staging Review Table Redesign (~1200px Viewport)

*Goal:* Consolidate and streamline [`web/src/views/ImportView.vue`](file:///D:/src/personal/wrangler/web/src/views/ImportView.vue) to eliminate horizontal scrolling at desktop widths down to ~1200px by embedding source and external ID with an inline external link button in Description, replacing text action buttons with compact icon buttons and tooltips, removing duplicate split buttons, and removing redundant `"CA$"` prefixes.

### 4.1 Staging Currency Formatting & Table Column Definitions
- In [`web/src/views/ImportView.vue`](file:///D:/src/personal/wrangler/web/src/views/ImportView.vue) (or store helper):
  - Define `formatStagedAmount(amount: string | number | null | undefined, currencyCode = "CAD"): string`:
    - Format amount using standard numeric currency formatting.
    - For CAD transactions (`currencyCode === 'CAD'`), drop redundant `"CA$"` prefix (rendering e.g. `"$96.04"` or `-$15.00`).
    - For non-CAD transactions, retain standard currency identifier (e.g. `USD 15.00`).
  - Update `columns: QTableColumn[]`:
    - Drop standalone `source` column.
    - Set explicit widths/classes:
      - `select`: align `"center"`, width ~48px.
      - `date`: align `"left"`, width ~95px.
      - `description`: align `"left"`, min-width ~280px.
      - `total_amount`: align `"right"`, width ~95px.
      - `allocations`: align `"left"`, width ~260px.
      - `receipt`: align `"center"`, width ~80px.
      - `actions`: align `"right"`, width ~80px.

### 4.2 Staging Review Table Column Slot Redesign
- In [`web/src/views/ImportView.vue`](file:///D:/src/personal/wrangler/web/src/views/ImportView.vue):
  - **Description Slot (`#body-cell-description`):**
    - Render primary line: `props.row.description || 'Unlabeled transaction'`.
    - Render metadata secondary line (`row items-center q-gutter-xs text-caption`):
      - Source chip: `<q-chip dense size="xs" color="blue-1" text-color="primary" class="text-weight-bold">{{ props.row.source }}</q-chip>`.
      - External ID caption: `<span v-if="props.row.external_id" class="text-grey-6">ID: {{ props.row.external_id }}</span>`.
      - Investigation URL Link Button: If `props.row.url` is present, render `<q-btn flat round dense size="xs" icon="open_in_new" color="primary" :href="props.row.url" target="_blank" rel="noopener noreferrer" data-testid="btn-open-url"><q-tooltip>Open order in Amazon</q-tooltip></q-btn>`.
  - **Amount Slot (`#body-cell-total_amount`):**
    - Use `formatStagedAmount(props.row.total_amount, props.row.currency_code)`.
  - **Allocations Slot (`#body-cell-allocations`):**
    - Render compact allocation badge.
    - For `STAGED` rows, render inline quick-assign `q-select` (`dense outlined options-dense style="min-width: 150px"`).
    - Render split icon button: `<q-btn flat round dense size="sm" icon="call_split" color="primary" data-testid="btn-split-allocations" @click="openEditDialog(props.row)"><q-tooltip>Split Allocations</q-tooltip></q-btn>`.
    - Remove redundant `"Edit / Split"` label.
  - **Receipt Slot (`#body-cell-receipt`):**
    - Standardize icon buttons (`size="sm" round dense`):
      - View: `icon="receipt" color="primary"`.
      - Replace: `icon="upload_file" color="grey-7"`.
      - Remove: `icon="delete_outline" color="negative"`.
      - Attach (when empty): `icon="attach_file" color="grey-8"` with `<q-tooltip>Attach Receipt</q-tooltip>`.
  - **Actions Slot (`#body-cell-actions`):**
    - Replace text buttons with compact icon-only buttons:
      - Edit button: `<q-btn flat round dense size="sm" icon="edit" color="primary" data-testid="btn-action-edit" @click="openEditDialog(props.row)"><q-tooltip>Edit Transaction</q-tooltip></q-btn>`.
      - Dismiss button: `<q-btn flat round dense size="sm" icon="block" color="negative" data-testid="btn-action-dismiss" @click="onDismissRow(props.row)"><q-tooltip>Dismiss Transaction</q-tooltip></q-btn>`.
      - Restore button: `<q-btn flat round dense size="sm" icon="restore" color="primary" data-testid="btn-action-restore" @click="onRestoreRow(props.row)"><q-tooltip>Restore Transaction</q-tooltip></q-btn>`.

### 4.3 Frontend Unit Tests for Staging Review Table Redesign
- In [`web/src/views/__tests__/ImportView.spec.ts`](file:///D:/src/personal/wrangler/web/src/views/__tests__/ImportView.spec.ts):
  - Verify `columns` does not include standalone `source` column.
  - Verify CAD currency amounts render without `"CA$"` prefix (e.g. `"$96.04"`, `"-$15.00"`).
  - Verify non-CAD currency amounts retain currency code.
  - Verify Description metadata line includes source chip and external ID.
  - Verify `open_in_new` link button renders when `url` is present with `target="_blank"` and tooltip, and is omitted when `url` is null.
  - Verify Allocations column renders `call_split` icon button with tooltip.
  - Verify Actions column renders compact `edit`, `block`, and `restore` icon buttons with respective tooltips.
