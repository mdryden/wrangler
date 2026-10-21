# Implementation Plan: Removal of Multi-Currency Support (CAD Single-Currency Architecture)

This implementation plan details the engineering deliverables required to remove multi-currency support and transition Wrangler to a strict single-currency (CAD) architecture across the backend database, ORM models, Pydantic schemas, intake pipelines, FastMCP AI agent service, and Vue 3 frontend based on [`specs/v2/6-remove-multi-currency/spec.md`](file:///D:/src/personal/wrangler/specs/v2/6-remove-multi-currency/spec.md).

The plan is organized into sequential phases and atomic implementation tasks. Each task specifies concrete deliverables and automated test coverage in [`api/tests/`](file:///D:/src/personal/wrangler/api/tests/) or [`web/tests/`](file:///D:/src/personal/wrangler/web/tests/) adhering to project conventions and development standards defined in [`AGENTS.md`](file:///D:/src/personal/wrangler/AGENTS.md).

---

## Phase 1: Database Schema Migration & SQLAlchemy ORM Models

*Goal:* Drop the `currency_code` column from `transactions` and `staged_transactions` tables via an Alembic batch migration, and eliminate the `currency_code` attributes from SQLAlchemy ORM models.

### 1.1 Alembic Migration to Drop `currency_code`
- In [`api/alembic/versions/`](file:///D:/src/personal/wrangler/api/alembic/versions/):
  - Create migration script `d4a8e2b1c3f5_remove_currency_code.py` with `down_revision = "e8a1f2c3b4d5"`.
  - In `upgrade()`, use `op.batch_alter_table` to drop column `"currency_code"` from table `"transactions"` and table `"staged_transactions"`.
  - In `downgrade()`, use `op.batch_alter_table` to re-add column `currency_code` (`sa.Column("currency_code", sa.String(), nullable=False, server_default="CAD")`) to `"staged_transactions"` and `"transactions"`.
- Automated test coverage in [`api/tests/test_migrations.py`](file:///D:/src/personal/wrangler/api/tests/test_migrations.py):
  - Update `test_alembic_migrations_upgrade_and_downgrade` to assert `"currency_code"` is absent from `tx_cols` and `staged_tx_cols` at migration head.
  - Add test verifying that upgrading to head drops `currency_code` from both tables, and downgrading restores `currency_code` with default value `'CAD'`.

### 1.2 SQLAlchemy ORM Model Refactoring
- In [`api/src/models/transaction.py`](file:///D:/src/personal/wrangler/api/src/models/transaction.py):
  - Remove `currency_code: Mapped[str] = mapped_column(String, nullable=False, default="CAD")` from [`Transaction`](file:///D:/src/personal/wrangler/api/src/models/transaction.py#L13-L31).
- In [`api/src/models/staged_transaction.py`](file:///D:/src/personal/wrangler/api/src/models/staged_transaction.py):
  - Remove `currency_code: Mapped[str] = mapped_column(String, nullable=False, default="CAD")` from [`StagedTransaction`](file:///D:/src/personal/wrangler/api/src/models/staged_transaction.py#L13-L36).
- Automated test coverage in [`api/tests/test_models.py`](file:///D:/src/personal/wrangler/api/tests/test_models.py) and [`api/tests/test_schema.py`](file:///D:/src/personal/wrangler/api/tests/test_schema.py):
  - Update [`test_models.py`](file:///D:/src/personal/wrangler/api/tests/test_models.py) to remove `currency_code` assertions and keyword arguments from [`Transaction`](file:///D:/src/personal/wrangler/api/src/models/transaction.py) and [`StagedTransaction`](file:///D:/src/personal/wrangler/api/src/models/staged_transaction.py) instantiation tests.
  - Update [`test_schema.py`](file:///D:/src/personal/wrangler/api/tests/test_schema.py) to assert `"currency_code" not in tx_cols` and `"currency_code" not in staged_tx_cols`.

---

## Phase 2: Backend Schemas, Serializers & Router Endpoints

*Goal:* Remove `currency_code` from Pydantic request and response schemas, staging serializers, and transaction router handlers.

### 2.1 Pydantic Schemas & Serializers Refactoring
- In [`api/src/schemas/transaction.py`](file:///D:/src/personal/wrangler/api/src/schemas/transaction.py):
  - Remove `currency_code: str = "CAD"` from [`TransactionCreate`](file:///D:/src/personal/wrangler/api/src/schemas/transaction.py#L11-L63).
  - Remove `currency_code: str | None = None` from [`TransactionUpdate`](file:///D:/src/personal/wrangler/api/src/schemas/transaction.py#L65-L96).
  - Remove `currency_code: str` from [`TransactionResponse`](file:///D:/src/personal/wrangler/api/src/schemas/transaction.py#L98-L110).
- In [`api/src/schemas/staging.py`](file:///D:/src/personal/wrangler/api/src/schemas/staging.py):
  - Remove `currency_code: str` from [`StagedTransactionResponse`](file:///D:/src/personal/wrangler/api/src/schemas/staging.py#L69-L81).
  - In `to_response(staged_tx: StagedTransaction) -> StagedTransactionResponse`, remove `currency_code=staged_tx.currency_code`.
- Automated test coverage in [`api/tests/test_schema.py`](file:///D:/src/personal/wrangler/api/tests/test_schema.py):
  - Verify serialization and validation of [`TransactionCreate`](file:///D:/src/personal/wrangler/api/src/schemas/transaction.py#L11-L63), [`TransactionResponse`](file:///D:/src/personal/wrangler/api/src/schemas/transaction.py#L98-L110), and [`StagedTransactionResponse`](file:///D:/src/personal/wrangler/api/src/schemas/staging.py#L69-L81) succeed without `currency_code`.

### 2.2 Transactions & Staging Router Updates
- In [`api/src/routers/transactions.py`](file:///D:/src/personal/wrangler/api/src/routers/transactions.py):
  - In `create_transaction`: remove `currency_code=payload.currency_code` when instantiating [`Transaction`](file:///D:/src/personal/wrangler/api/src/models/transaction.py).
  - In `update_transaction`: update `scalar_fields = ("date", "description", "total_amount", "source", "external_id", "receipt_file_path")` to exclude `"currency_code"`.
- In [`api/src/routers/staging.py`](file:///D:/src/personal/wrangler/api/src/routers/staging.py):
  - In `accept_staged_transactions`: remove `currency_code=stx.currency_code` when creating ledger [`Transaction`](file:///D:/src/personal/wrangler/api/src/models/transaction.py) instances from accepted staged records.
- In [`api/transactions.http`](file:///D:/src/personal/wrangler/api/transactions.http):
  - Remove `"currency_code": "CAD"` from sample manual transaction creation request.
- Automated test coverage in [`api/tests/test_transactions.py`](file:///D:/src/personal/wrangler/api/tests/test_transactions.py), [`api/tests/test_staging_api.py`](file:///D:/src/personal/wrangler/api/tests/test_staging_api.py), and [`api/tests/test_transaction_flow.py`](file:///D:/src/personal/wrangler/api/tests/test_transaction_flow.py):
  - Remove `currency_code` from request payloads and response assertions across transaction CRUD test suites.
  - Verify `POST /api/staging/accept` converts staged records to ledger transactions without referencing `currency_code`.

---

## Phase 3: Intake Pipelines, CSV Importers & FastMCP AI Agent Service

*Goal:* Eliminate multi-currency handling from CSV ingestion, intake parsers, and the FastMCP `stage_transaction` tool signature and output formatting.

### 3.1 Importer Infrastructure & CSV Amount Parsing Updates
- In [`api/src/services/importers/base.py`](file:///D:/src/personal/wrangler/api/src/services/importers/base.py):
  - Remove `currency_code: str = "CAD"` from [`ImportedTransactionData`](file:///D:/src/personal/wrangler/api/src/services/importers/base.py#L27-L38).
- In [`api/src/services/intake.py`](file:///D:/src/personal/wrangler/api/src/services/intake.py):
  - Remove `currency_code: str = "CAD"` from [`ParsedTransaction`](file:///D:/src/personal/wrangler/api/src/services/intake.py#L9-L21).
  - In [`ManualIntakeParser.parse`](file:///D:/src/personal/wrangler/api/src/services/intake.py#L45-L78), remove `data.setdefault("currency_code", "CAD")` and `"currency_code": getattr(item, "currency_code", "CAD")`.
- In [`api/src/routers/importers.py`](file:///D:/src/personal/wrangler/api/src/routers/importers.py):
  - In `run_importer`: remove `currency_code=item.currency_code` when constructing [`StagedTransaction`](file:///D:/src/personal/wrangler/api/src/models/staged_transaction.py).
- In [`api/src/services/importers/csv_base.py`](file:///D:/src/personal/wrangler/api/src/services/importers/csv_base.py):
  - In [`BaseCsvImporter.parse_amount`](file:///D:/src/personal/wrangler/api/src/services/importers/csv_base.py#L28-L63):
    - Strip common currency symbols (`$`, `CA$`) and surrounding whitespace.
    - Remove multi-currency regex replacements (`re.sub(r"\b(?:CAD|USD)\b", "", ...)`).
    - Treat all extracted values as CAD.
    - Retain existing negative handling for parenthetical numbers `(12.34)` and explicit signs (`-`, `+`).
- In [`api/src/services/importers/amazon_csv.py`](file:///D:/src/personal/wrangler/api/src/services/importers/amazon_csv.py):
  - In `parse_row`, remove `currency_code="CAD"` when creating [`ImportedTransactionData`](file:///D:/src/personal/wrangler/api/src/services/importers/base.py#L27-L38).
- Automated test coverage in [`api/tests/test_intake.py`](file:///D:/src/personal/wrangler/api/tests/test_intake.py), [`api/tests/test_importer_framework.py`](file:///D:/src/personal/wrangler/api/tests/test_importer_framework.py), [`api/tests/test_amazon_csv_importer.py`](file:///D:/src/personal/wrangler/api/tests/test_amazon_csv_importer.py), and [`api/tests/test_importers_api.py`](file:///D:/src/personal/wrangler/api/tests/test_importers_api.py):
  - Update unit and integration tests to remove assertions checking `item.currency_code == "CAD"`.
  - Add tests in `test_importer_framework.py` verifying `BaseCsvImporter.parse_amount` parses `$12.50`, `CA$12.50`, `-$25.00`, and `(45.00)` to correct CAD `Decimal` values.

### 3.2 FastMCP AI Agent Service Refactoring
- In [`api/src/services/mcp.py`](file:///D:/src/personal/wrangler/api/src/services/mcp.py):
  - In [`stage_transaction`](file:///D:/src/personal/wrangler/api/src/services/mcp.py#L36-L59):
    - Remove `currency_code: str | None = None` parameter from tool function signature.
    - Update tool docstring to remove documentation for `currency_code`.
    - Remove `cleaned_currency` normalization logic.
    - Remove `currency_code` from [`StagedTransaction`](file:///D:/src/personal/wrangler/api/src/models/staged_transaction.py) construction.
    - Format return confirmation strings using standard currency notation without currency code suffixes:
      - Pending values: `amt_display = f"(${amount_decimal:.2f})" if amount_decimal is not None else "(amount pending)"`.
      - Complete transaction: `f"Successfully staged transaction: [mcp] {namespaced_external_id} - {formatted_description} (${amount_decimal:.2f})."`.
      - Incomplete transaction: `f"Successfully staged transaction: [mcp] {namespaced_external_id} - {desc_display} {amt_display}. Needs review in Wrangler: {', '.join(missing)}."`.
- In [`README.md`](file:///D:/src/personal/wrangler/README.md):
  - Update the `stage_transaction` parameters column in the MCP tools reference table to remove `currency_code`.
- Automated test coverage in [`api/tests/test_mcp_tools.py`](file:///D:/src/personal/wrangler/api/tests/test_mcp_tools.py), [`api/tests/test_mcp_staging_lifecycle.py`](file:///D:/src/personal/wrangler/api/tests/test_mcp_staging_lifecycle.py), and [`api/tests/test_mcp_transport.py`](file:///D:/src/personal/wrangler/api/tests/test_mcp_transport.py):
  - Remove `currency_code` parameter from all `stage_transaction` tool call invocations.
  - Delete tests that specifically test passing foreign currencies (`currency_code="USD"`).
  - Assert that tool return strings match the updated format without currency code suffixes.

---

## Phase 4: Frontend TypeScript Types, Currency Formatters & Views

*Goal:* Remove `currency_code` from TypeScript interfaces, unify formatting utilities to standard `$X,XXX.XX` representation, update Vue view templates, and update frontend unit test suites.

### 4.1 TypeScript Types & Export Manager Model Refactoring
- In [`web/src/types/transaction.ts`](file:///D:/src/personal/wrangler/web/src/types/transaction.ts):
  - Remove `currency_code?: string` from `TransactionCreate`.
  - Remove `currency_code?: string` from `TransactionUpdate`.
  - Remove `currency_code: string` from `Transaction`.
- In [`web/src/types/staging.ts`](file:///D:/src/personal/wrangler/web/src/types/staging.ts):
  - Remove `currency_code: string` from `StagedTransaction`.
- In [`web/src/views/exportManager.ts`](file:///D:/src/personal/wrangler/web/src/views/exportManager.ts):
  - Remove `currency_code: string` from `ExportAllocationRow`.
  - In `generateCompanyRows`: remove `currency_code: tx.currency_code || "CAD"`.
- Automated test coverage in [`web/tests/transaction.test.ts`](file:///D:/src/personal/wrangler/web/tests/transaction.test.ts) and [`web/tests/company.test.ts`](file:///D:/src/personal/wrangler/web/tests/company.test.ts):
  - Verify TypeScript compilation and unit tests pass with updated type definitions and fixtures.

### 4.2 Currency Formatting Utilities Refactoring
- In [`web/src/views/ledger.ts`](file:///D:/src/personal/wrangler/web/src/views/ledger.ts):
  - Refactor `formatCurrency(amount: string | number | null | undefined): string`:
    - Remove the `currencyCode` parameter.
    - If `amount` is `null`, `undefined`, or `""`, return `"$0.00"`.
    - Parse string amounts via `parseFloat`; if `Number.isNaN(num)`, return `"$0.00"`.
    - Format using `Math.abs(num).toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })`.
    - Return `${isNegative ? "-" : ""}$${absFormatted}`.
- In [`web/src/views/importView.ts`](file:///D:/src/personal/wrangler/web/src/views/importView.ts):
  - Refactor `formatStagedAmount(amount: string | number | null | undefined): string`:
    - Remove `currencyCode` parameter and non-CAD branches.
    - Delegate directly to `formatCurrency(amount)`.
- Automated test coverage in [`web/tests/ledger.test.ts`](file:///D:/src/personal/wrangler/web/tests/ledger.test.ts) and [`web/src/views/__tests__/importView.spec.ts`](file:///D:/src/personal/wrangler/web/src/views/__tests__/importView.spec.ts):
  - In `ledger.test.ts`: test `formatCurrency` with positive values (`45.99` -> `"$45.99"`), negative values (`-25.5` -> `"-$25.50"`), thousands (`"1250.50"` -> `"$1,250.50"`), zero (`0` -> `"$0.00"`), empty string (`""` -> `"$0.00"`), and null/invalid (`null` -> `"$0.00"`).
  - In `importView.spec.ts`: remove tests asserting retention of non-CAD currency codes (`USD 15.00`, `EUR 99.99`), and update assertions for `formatStagedAmount`.

### 4.3 Vue Component Templates & Unit Test Fixtures
- In [`web/src/views/LedgerView.vue`](file:///D:/src/personal/wrangler/web/src/views/LedgerView.vue):
  - Update total amount table cell: replace `{{ formatCurrency(props.row.total_amount, props.row.currency_code) }}` with `{{ formatCurrency(props.row.total_amount) }}`.
  - Update split allocation list amount cell: replace `{{ formatCurrency(alloc.amount, props.row.currency_code) }}` with `{{ formatCurrency(alloc.amount) }}`.
- In [`web/src/views/ImportView.vue`](file:///D:/src/personal/wrangler/web/src/views/ImportView.vue):
  - Update total amount table cell: replace `{{ formatStagedAmount(props.row.total_amount, props.row.currency_code) }}` with `{{ formatStagedAmount(props.row.total_amount) }}`.
- In [`web/src/views/ExportManagerView.vue`](file:///D:/src/personal/wrangler/web/src/views/ExportManagerView.vue):
  - Update row allocation amount cell: replace `{{ formatCurrency(props.row.amount, props.row.currency_code) }}` with `{{ formatCurrency(props.row.amount) }}`.
- Automated test coverage in [`web/src/views/__tests__/importView.spec.ts`](file:///D:/src/personal/wrangler/web/src/views/__tests__/importView.spec.ts), [`web/src/components/__tests__/stagedTransactionEdit.spec.ts`](file:///D:/src/personal/wrangler/web/src/components/__tests__/stagedTransactionEdit.spec.ts), [`web/src/stores/__tests__/staging.spec.ts`](file:///D:/src/personal/wrangler/web/src/stores/__tests__/staging.spec.ts), [`web/tests/ledger.test.ts`](file:///D:/src/personal/wrangler/web/tests/ledger.test.ts), and [`web/tests/transaction.test.ts`](file:///D:/src/personal/wrangler/web/tests/transaction.test.ts):
  - In `importView.spec.ts`: update template layout assertion to verify template contains `formatStagedAmount(props.row.total_amount)`.
  - Remove `currency_code` attributes from mock transaction and staged transaction test fixtures across all frontend test suites.
