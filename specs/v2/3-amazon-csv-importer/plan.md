# Implementation Plan: Amazon Transactions CSV Importer

This implementation plan details the engineering deliverables required to implement the Amazon Transactions CSV Importer based on [`specs/v2/3-amazon-csv-importer/spec.md`](file:///D:/src/personal/wrangler/specs/v2/3-amazon-csv-importer/spec.md).

The plan is organized into sequential phases and atomic implementation tasks. Each task includes automated test coverage in [`api/tests/`](file:///D:/src/personal/wrangler/api/tests/) adhering to project guidelines in [`AGENTS.md`](file:///D:/src/personal/wrangler/AGENTS.md).

---

## Phase 1: Importer Framework Updates for Nullable Fields

*Goal:* Update the core importer data structure [`ImportedTransactionData`](file:///D:/src/personal/wrangler/api/src/services/importers/base.py) to support nullable fields (`date`, `description`, `total_amount`) so that intake adapters can stage rows needing user review and completion without discarding malformed entries.

### 1.1 Update `ImportedTransactionData` Model and Field Validators
- Modify [`ImportedTransactionData`](file:///D:/src/personal/wrangler/api/src/services/importers/base.py#L26-L52) in [`api/src/services/importers/base.py`](file:///D:/src/personal/wrangler/api/src/services/importers/base.py):
  - Change `date` type annotation from `date` to `date | None = None`.
  - Change `description` type annotation from `str` to `str | None = None`.
  - Change `total_amount` type annotation from `Decimal` to `Decimal | None = None`.
  - Update description validator using `mode="before"`:
    - If input value is `None`, return `None`.
    - Strip whitespace using `str(v).strip()`.
    - Return stripped string if non-empty, otherwise return `None`.
  - Update total amount validator using `mode="before"`:
    - If input value is `None`, return `None`.
    - Convert to `Decimal(str(v))`.
    - If `dec == Decimal("0")`, return `None`.
    - Return `dec`.
- Ensure internal module imports in [`api/src/services/importers/base.py`](file:///D:/src/personal/wrangler/api/src/services/importers/base.py) remain relative and follow formatting guidelines.

### 1.2 Update Framework Unit Tests for Nullable Transaction Data
- Update unit tests in [`api/tests/test_importer_framework.py`](file:///D:/src/personal/wrangler/api/tests/test_importer_framework.py):
  - Adjust existing tests in `test_imported_transaction_data_validation_errors` that previously asserted `ValidationError` for whitespace-only descriptions or zero amounts.
  - Add test assertions verifying that:
    - `description="   "` normalizes to `None`.
    - `description=None` is accepted and remains `None`.
    - `total_amount=Decimal("0.00")` or `total_amount="0"` normalizes to `None`.
    - `total_amount=None` is accepted and remains `None`.
    - `date=None` is accepted and remains `None`.
    - Invalid non-numeric strings (e.g., `total_amount="invalid"`) still raise `ValidationError` / `InvalidOperation`.
  - Verify all existing importer framework tests pass without regressions.

---

## Phase 2: Amazon CSV Importer Implementation

*Goal:* Implement the [`AmazonCsvImporter`](file:///D:/src/personal/wrangler/api/src/services/importers/amazon_csv.py) class subclassing [`BaseCsvImporter`](file:///D:/src/personal/wrangler/api/src/services/importers/csv_base.py) with row parsing, sign inversion, blank descriptions, unparseable fallbacks, and repeated header filtering.

### 2.1 Implement `AmazonCsvImporter` Intake Adapter
- Create [`api/src/services/importers/amazon_csv.py`](file:///D:/src/personal/wrangler/api/src/services/importers/amazon_csv.py) containing `AmazonCsvImporter(BaseCsvImporter)`:
  - Class attributes & metadata:
    - `importer_id: str = "amazon_csv"`
    - `source_name: str = "amazon_csv"`
    - `display_name: str = "Amazon Transactions CSV"`
    - `description: str = "Imports Amazon orders and refunds from an exported Amazon transactions CSV file."`
    - `input_type: ImporterInputType = ImporterInputType.FILE`
    - `accepted_file_types: list[str] = [".csv"]`
    - `supports_mark_imported: bool = False`
    - `REQUIRED_COLUMNS: tuple[str, ...] = ("date", "order ids", "order urls", "vendor", "card_details", "amount")`
    - `SKIP_ZERO_AMOUNT_ROWS: bool = False`
  - Implement `parse_row(self, row: dict[str, str], row_number: int) -> ImportedTransactionData | None`:
    - **Duplicate Header Row Detection**:
      - Inspect `row.get("date", "").strip().lower()` and `row.get("order ids", "").strip().lower()`.
      - If either equals `"date"` or `"order ids"`, return `None` to skip the row.
    - **External ID (`external_id`)**:
      - Extract `raw_order_id = row.get("order ids", "").strip()`.
      - Set `external_id = raw_order_id if raw_order_id else None` (preserving digital IDs, multiple order IDs, and placeholders).
    - **Date Parsing (`date`)**:
      - Extract `raw_date = row.get("date", "").strip()`.
      - If empty, set `tx_date = None`.
      - Otherwise, wrap call to `self.parse_iso_or_common_date(raw_date)` in a `try...except ValueError` block; on error, set `tx_date = None` without raising.
    - **Description (`description`)**:
      - Always set to `None`.
    - **Amount Inversion (`total_amount`)**:
      - Extract `raw_amount = row.get("amount", "").strip()`.
      - If empty, set `total_amount = None`.
      - Otherwise, wrap call to `self.parse_amount(raw_amount)` in a `try...except ValueError` block; on error, set `total_amount = None`.
      - If parsed successfully:
        - If parsed value equals `Decimal("0")`, set `total_amount = None`.
        - Otherwise, multiply by `-1` (`total_amount = (-parsed_amount).quantize(Decimal("0.01"))`).
    - **Currency & Receipt**:
      - Set `currency_code = "CAD"`.
      - Set `receipt = None`.
    - Return `ImportedTransactionData(external_id=external_id, date=tx_date, description=None, total_amount=total_amount, currency_code="CAD", receipt=None)`.

### 2.2 Add Unit Tests for Amazon CSV Row Parsing and Pipeline
- Create [`api/tests/test_amazon_csv_importer.py`](file:///D:/src/personal/wrangler/api/tests/test_amazon_csv_importer.py) with unit tests testing `AmazonCsvImporter`:
  - **Metadata check**: verify `importer_id`, `source_name`, `display_name`, `input_type`, `accepted_file_types`, and `supports_mark_imported`.
  - **Required column validation**:
    - File missing any of `("date", "order ids", "order urls", "vendor", "card_details", "amount")` raises [`ImporterValidationError`](file:///D:/src/personal/wrangler/api/src/services/importers/base.py#L9-L10).
  - **Repeated header row handling**:
    - Embedded rows matching header names return `None` from `parse_row` and are omitted from `fetch_and_parse` results.
  - **Amount sign inversion**:
    - Negative charge `"-96.04"` inverts to `Decimal("96.04")`.
    - Positive refund `"15.00"` inverts to `Decimal("-15.00")`.
    - Currency and comma formatted values (e.g., `"-$1,234.56"`, `"+$50.00"`) invert correctly.
  - **Blank description rule**:
    - Confirm all parsed items have `description is None`.
  - **Fallback resilience (no dropped rows)**:
    - Malformed or blank date parses to `date = None`.
    - Malformed, blank, or `0.00` amount parses to `total_amount = None`.
    - Multi-order string (e.g., `"D01-0626645-1689808, ??"`) is preserved as `external_id`.
    - Blank `order ids` sets `external_id = None`.

---

## Phase 3: Importer Registration & API Integration

*Goal:* Register [`AmazonCsvImporter`](file:///D:/src/personal/wrangler/api/src/services/importers/amazon_csv.py) in the application registry and verify end-to-end HTTP intake, deduplication, and staging readiness.

### 3.1 Register `AmazonCsvImporter` in Registry
- Update [`api/src/services/importers/registry.py`](file:///D:/src/personal/wrangler/api/src/services/importers/registry.py):
  - Import `AmazonCsvImporter` from `.amazon_csv`.
  - Register default instance upon module import: `register_importer(AmazonCsvImporter())`.
- Verify that `list_importers()` includes `amazon_csv` and `get_importer("amazon_csv")` returns the registered instance.

### 3.2 Implement End-to-End API Integration & Staging Acceptance Tests
- Add integration tests in [`api/tests/test_amazon_csv_importer.py`](file:///D:/src/personal/wrangler/api/tests/test_amazon_csv_importer.py):
  - **Discovery**: `GET /api/importers` returns `amazon_csv` with metadata matching Section 6.2 of the spec.
  - **Import Execution (`POST /api/importers/amazon_csv/run`)**:
    - Upload multipart CSV containing sample data from Section 2.2 of the spec.
    - Assert `200 OK` and response fields (`total_parsed`, `staged_count`, `skipped_duplicates`, `items`).
    - Verify created [`StagedTransaction`](file:///D:/src/personal/wrangler/api/src/models/staged_transaction.py) records in the database with inverted amounts, `description=None`, `source="amazon_csv"`, and `is_ready=False`.
  - **Deduplication**:
    - Test intra-batch duplicate `external_id` (only the first instance is staged; subsequent rows increment `skipped_duplicates`).
    - Test cross-table deduplication against existing `staged_transactions` across all statuses (`STAGED`, `ACCEPTED`, `DISMISSED`) and ledger [`Transaction`](file:///D:/src/personal/wrangler/api/src/models/transaction.py) records.
    - Test that rows with `external_id = None` bypass deduplication and are always staged.
    - Re-uploading the same CSV yields `staged_count = 0` and `skipped_duplicates == total_parsed`.
  - **Staging Readiness & Acceptance Guard**:
    - Verify that staged Amazon records cannot be accepted via `POST /api/staging/accept` while `description` or `total_amount` is `None`.
    - Verify that after updating description, total amount, and allocations via `PUT /api/staging/{id}`, the record transitions to `is_ready = True` and can be accepted into the Ledger.
