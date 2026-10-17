# Amazon Transactions CSV Importer Specification

> [!WARNING]
> **STATUS: INCOMPLETE / DRAFT — PENDING AMAZON CSV COLUMN MAPPING & FILTERING DETAILS**
> This specification defines the architectural adapter contract and `BaseCsvImporter` integration for the Amazon Transactions CSV Importer, but intentionally leaves the exact Amazon CSV column headers, multi-item order aggregation rules, and row filtering criteria incomplete for future refinement.

---

## 1. Goal & Overview
The **Amazon Transactions CSV Importer** (`AmazonCsvImporter`) is a file-based importer that subclasses [`BaseCsvImporter`](file:///D:/src/personal/wrangler/specs/v2/1-importer-framework/spec.md) to read exported Amazon transaction CSV files and stage them in Wrangler for allocation and receipt attachment.

By inheriting from `BaseCsvImporter`, `AmazonCsvImporter` reuses all common CSV file validation, UTF-8/BOM decoding, header verification, date/amount parsing helpers, and row-level error reporting defined in the Importer Framework.

---

## 2. Importer Adapter Contract (`api/src/services/importers/amazon_csv.py`)

### 2.1 Class Metadata & Capabilities
- **Class Name:** `AmazonCsvImporter(BaseCsvImporter)`
- **`importer_id`:** `"amazon_csv"`
- **`source_name`:** `"amazon_csv"`
- **`display_name`:** `"Amazon Transactions CSV"`
- **`description`:** `"Imports orders and refunds from an exported Amazon transactions CSV file."`
- **`input_type`:** `ImporterInputType.FILE` (inherited from `BaseCsvImporter`)
- **`accepted_file_types`:** `[".csv"]` (inherited from `BaseCsvImporter`)
- **`supports_mark_imported`:** `False` (inherits the default no-op `mark_as_imported` implementation from `BaseImporter`)

### 2.2 Integration with `BaseCsvImporter` & Framework
1. **Shared CSV Infrastructure:**
   - Uses `BaseCsvImporter.fetch_and_parse(file_bytes, filename)` for BOM-safe decoding (`utf-8-sig`), `csv.DictReader` streaming, and `REQUIRED_COLUMNS` validation.
   - Uses `BaseCsvImporter.parse_amount` and `BaseCsvImporter.parse_iso_or_common_date` to normalize currency strings and dates.
2. **Receipts:**
   - Amazon CSV files do not embed receipt files (`ImportedTransactionData.receipt = None`). Users can attach PDF/image invoices to staged Amazon transactions in the Staging View (`POST /api/staging/{id}/receipt` or `PUT /api/staging/{id}`).
3. **Persistent Deduplication (`external_id`):**
   - Because users frequently export overlapping date ranges from Amazon CSV reports, `AmazonCsvImporter` extracts a deterministic `external_id` per transaction row.
   - Wrangler's `staged_transactions` (including `STAGED`, `ACCEPTED`, and `DISMISSED` records) and `transactions` tables prevent previously imported or dismissed Amazon rows from appearing again when overlapping CSV files are uploaded.

---

## 3. Open / Incomplete Sections (To Be Refined)

> [!IMPORTANT]
> The following sections must be completed before implementing `AmazonCsvImporter`:

### 3.1 Target Amazon CSV Format & Required Columns — **[TBD]**
- **Exact CSV Export Type:** Specify which Amazon export format is used (e.g., Amazon Consumer "Request My Data" `Retail.OrderHistory.csv`, Amazon Payments / Transactions report, or Amazon Business Order History CSV).
- **`REQUIRED_COLUMNS` Definition:** Specify the exact header names required in the CSV file (e.g., `Order ID`, `Order Date`, `Title` / `Description`, `Total Owed` / `Amount`, `Currency`).

### 3.2 Row Mapping & `external_id` Construction — **[TBD]**
- **Unique Identifier (`external_id`):** Determine whether `Order ID` alone is unique per row, or if multi-shipment / multi-item rows share an `Order ID` and require a composite `external_id` (or pre-aggregation by `Order ID` + charge date).
- **Description Formatting:** Define how item titles, quantities, or order IDs should be formatted into `ImportedTransactionData.description`.

### 3.3 Refunds, Promotions & Skipped Row Rules — **[TBD]**
- **Refunds / Credits:** Confirm how refunds or returns are represented in the CSV (negative amount vs. transaction type column) so they map to negative `total_amount` values.
- **Filtered / Ignored Rows:** Specify any rows that `parse_row` should skip by returning `None` (e.g., `"Cancelled"` order status, `$0.00` gift card redemptions, or pending/unshipped orders).
