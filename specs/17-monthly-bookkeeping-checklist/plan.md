# Implementation Plan: Monthly Bookkeeping Checklist & RBC Bank Feed Wave Sync

This implementation plan details the engineering tasks required to build the Monthly Bookkeeping Checklist subsystem in Wrangler tailored for Michelle Dryden LTD, including direct RBC CSV-to-Wave bank feed synchronization, Wave category caching enhancements, corporate tax accrual journal entry synchronization, and month-to-month soft cap carry-forward tracking.

---

## Phase 1: Database Models, Alembic Migration & Wave Integration Foundation

### 1.1 SQLAlchemy Models for Checklist Subsystem
- **File:** [`api/src/models/checklist.py`](file:///D:/src/personal/wrangler/api/src/models/checklist.py)
- **Description:** Implement the `ChecklistConfig` and `MonthlyChecklist` SQLAlchemy ORM models.
- **Details:**
  - Create `ChecklistConfig` inheriting from `database.Base`:
    - `id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)`
    - `company_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("companies.id", ondelete="SET NULL"), nullable=True)`
    - `chequing_wave_account_id: Mapped[str | None] = mapped_column(String, nullable=True)`
    - `chequing_wave_account_name: Mapped[str | None] = mapped_column(String, nullable=True)`
    - `mastercard_wave_account_id: Mapped[str | None] = mapped_column(String, nullable=True)`
    - `mastercard_wave_account_name: Mapped[str | None] = mapped_column(String, nullable=True)`
    - `tax_expense_wave_account_id: Mapped[str | None] = mapped_column(String, nullable=True)`
    - `tax_expense_wave_account_name: Mapped[str | None] = mapped_column(String, nullable=True)`
    - `tax_payable_wave_account_id: Mapped[str | None] = mapped_column(String, nullable=True)`
    - `tax_payable_wave_account_name: Mapped[str | None] = mapped_column(String, nullable=True)`
    - `wave_web_business_slug: Mapped[str] = mapped_column(String, nullable=False, default="d2977f10-6793-4504-a139-f0d6872b2628")`
    - `last_chequing_tx_date: Mapped[datetime.date | None] = mapped_column(Date, nullable=True)`
    - `last_mastercard_tx_date: Mapped[datetime.date | None] = mapped_column(Date, nullable=True)`
    - Relationship `company: Mapped[Company | None] = relationship("Company")`
  - Create `MonthlyChecklist` inheriting from `database.Base`:
    - `id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)`
    - `year_month: Mapped[str] = mapped_column(String(7), unique=True, index=True, nullable=False)`
    - `completed_steps_json: Mapped[str] = mapped_column(String, nullable=False, default="[]")`
    - `net_operating_cash: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)`
    - `tax_rate: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False, default=Decimal("12.00"))`
    - `tax_accrual_wave_tx_id: Mapped[str | None] = mapped_column(String, nullable=True)`
    - `prior_soft_cap: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, default=Decimal("17600.00"))`
    - `monthly_loc_reduction: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, default=Decimal("400.00"))`
    - `tax_liability: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)`
    - `actual_loc_balance: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)`
  - Add Python helper properties to `MonthlyChecklist`:
    - `completed_steps: list[str]` getter and setter with `json.loads` and `json.dumps`.
    - `tax_reserve_amount -> Decimal | None`:
      - Return `None` if `net_operating_cash is None`.
      - Return `Decimal("0.00")` if `net_operating_cash <= Decimal("0.00")`.
      - Otherwise return `(net_operating_cash * (tax_rate / Decimal("100"))).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)`.
    - `current_soft_cap -> Decimal`:
      - Return `(prior_soft_cap - monthly_loc_reduction).quantize(Decimal("0.01"))`.
    - `maximum_safe_draw -> Decimal | None`:
      - Return `None` if `tax_liability is None` or `actual_loc_balance is None`.
      - Otherwise return `(current_soft_cap - tax_liability - actual_loc_balance).quantize(Decimal("0.01"))`.
  - Add unit tests in [`api/tests/test_checklist_models.py`](file:///D:/src/personal/wrangler/api/tests/test_checklist_models.py) verifying initial defaults, JSON step serialization, and calculated properties.

### 1.2 Alembic Database Migration for Checklist Tables
- **File:** `api/alembic/versions/<revision_id>_add_monthly_checklist_tables.py`
- **Description:** Generate and execute an Alembic schema migration script creating `checklist_configs` and `monthly_checklists` tables.
- **Details:**
  - Set `down_revision = "d5c8e3f1a2b7"`.
  - In `upgrade()`:
    - Create table `checklist_configs` with all columns defined in 1.1 and foreign key to `companies.id` with `ondelete="SET NULL"`.
    - Create table `monthly_checklists` with all columns defined in 1.1 and unique index `ix_monthly_checklists_year_month` on `year_month`.
  - In `downgrade()`:
    - Drop index `ix_monthly_checklists_year_month` and table `monthly_checklists`.
    - Drop table `checklist_configs`.
  - Update [`api/alembic/env.py`](file:///D:/src/personal/wrangler/api/alembic/env.py) to import `ChecklistConfig` and `MonthlyChecklist` so Alembic tracks both models in autogenerate comparisons.
  - Verify migration upgrade and downgrade execution in [`api/tests/test_checklist_models.py`](file:///D:/src/personal/wrangler/api/tests/test_checklist_models.py).

### 1.3 Wave Client & Category Caching Enhancements
- **Files:** [`api/src/services/wave/client.py`](file:///D:/src/personal/wrangler/api/src/services/wave/client.py), [`api/src/routers/companies.py`](file:///D:/src/personal/wrangler/api/src/routers/companies.py)
- **Description:** Enhance Wave account discovery, categorization caching, and transaction creation to support liability accounts and deposit routing.
- **Details:**
  - In [`WaveAccountsResult`](file:///D:/src/personal/wrangler/api/src/services/wave/client.py#L26-L30):
    - Add `liability_accounts: list[WaveAccount] = field(default_factory=list)` (or default list parameter).
  - In `WaveClient.get_business_accounts`:
    - Collect all non-archived accounts with `type_val == "LIABILITY"` into `liability_accounts` so `Taxes Payable` can be selected in Checklist Settings.
    - Collect non-archived `REVENUE` / `INCOME` accounts where `subtype_val == "UNCATEGORIZED_INCOME"` into `expense_categories` with `is_uncategorized = True`, `type = type_val`, and `subtype = subtype_val`.
    - Ensure `anchor_accounts` includes eligible liability accounts with `subtype in ("CASH_AND_BANK", "CREDIT_CARD", "MONEY_MARKET", "DUE_TO_YOU_AND_OTHER_OWNERS", "LOANS_AND_LINE_OF_CREDIT")`.
  - In `WaveClient.create_money_transaction`:
    - Add optional parameters `anchor_direction: str | None = None` and `line_balance: str | None = None`.
    - When provided, use explicit values in the GraphQL `MoneyTransactionCreateInput` payload; when omitted, preserve existing sign-based deduction.
  - In [`api/src/routers/companies.py`](file:///D:/src/personal/wrangler/api/src/routers/companies.py):
    - In `_sync_categories_for_company`: ensure `UNCATEGORIZED_INCOME` accounts are cached into the `WaveCategory` table alongside `UNCATEGORIZED_EXPENSE`.
    - In `get_company_wave_categories`: add filter `WaveCategory.account_type == "EXPENSE"` to ensure `UNCATEGORIZED_INCOME` does not appear in standard expense category selection menus in Export Manager.
  - Add automated unit tests in [`api/tests/test_wave_client.py`](file:///D:/src/personal/wrangler/api/tests/test_wave_client.py) and [`api/tests/test_company_wave_config.py`](file:///D:/src/personal/wrangler/api/tests/test_company_wave_config.py) validating liability account returns, `UNCATEGORIZED_INCOME` caching, and direction override parameters.

---

## Phase 2: Backend Checklist Engine, Schemas & REST API Endpoints

### 2.1 Checklist Pydantic Schemas
- **File:** [`api/src/schemas/checklist.py`](file:///D:/src/personal/wrangler/api/src/schemas/checklist.py)
- **Description:** Define request and response Pydantic schemas for checklist configuration, grouped accounts, month state, and synchronization responses.
- **Details:**
  - `ChecklistConfigResponse`:
    - `company_id: uuid.UUID | None`
    - `company_name: str | None`
    - `is_wave_connected: bool`
    - `chequing_wave_account_id: str | None`
    - `chequing_wave_account_name: str | None`
    - `mastercard_wave_account_id: str | None`
    - `mastercard_wave_account_name: str | None`
    - `tax_expense_wave_account_id: str | None`
    - `tax_expense_wave_account_name: str | None`
    - `tax_payable_wave_account_id: str | None`
    - `tax_payable_wave_account_name: str | None`
    - `wave_web_business_slug: str`
    - `last_chequing_tx_date: datetime.date | None`
    - `last_mastercard_tx_date: datetime.date | None`
    - `model_config = ConfigDict(from_attributes=True)`
  - `ChecklistConfigUpdate`:
    - Optional fields matching `ChecklistConfigResponse` for updating settings.
  - `WaveAccountsGroupedResponse`:
    - `bank_and_cc_accounts: list[WaveAccountItem]`
    - `expense_accounts: list[WaveAccountItem]`
    - `liability_accounts: list[WaveAccountItem]`
  - `MonthlyChecklistResponse`:
    - `id: uuid.UUID`
    - `year_month: str`
    - `completed_steps: list[str]`
    - `net_operating_cash: Decimal | None`
    - `tax_rate: Decimal`
    - `tax_reserve_amount: Decimal | None`
    - `tax_accrual_wave_tx_id: str | None`
    - `prior_soft_cap: Decimal`
    - `monthly_loc_reduction: Decimal`
    - `current_soft_cap: Decimal`
    - `tax_liability: Decimal | None`
    - `actual_loc_balance: Decimal | None`
    - `maximum_safe_draw: Decimal | None`
    - `wave_cash_flow_url: str`
    - `model_config = ConfigDict(from_attributes=True)`
  - `MonthlyChecklistUpdate`:
    - Optional fields: `completed_steps: list[str] | None`, `net_operating_cash: Decimal | None`, `tax_rate: Decimal | None`, `prior_soft_cap: Decimal | None`, `monthly_loc_reduction: Decimal | None`, `tax_liability: Decimal | None`, `actual_loc_balance: Decimal | None`.
  - `RbcCsvSyncResponse`:
    - `total_rows: int`
    - `synced_count: int`
    - `failed_count: int`
    - `auto_categorized_count: int`
    - `uncategorized_count: int`
    - `latest_transaction_date: datetime.date | None`
    - `errors: list[str]`
  - `TaxAccrualSyncRequest`:
    - `net_operating_cash: Decimal | None = None`
    - `tax_rate: Decimal | None = None`

### 2.2 RBC CSV Parser & Auto-Categorization Engine
- **File:** [`api/src/services/checklist/rbc_parser.py`](file:///D:/src/personal/wrangler/api/src/services/checklist/rbc_parser.py)
- **Description:** Implement parsing, header validation, space collapsing, sign inversion, and auto-categorization matching for RBC Chequing and Mastercard exports.
- **Details:**
  - Define `NormalizedRbcRow`:
    - `date: datetime.date`
    - `raw_account_type: str`
    - `description: str`
    - `signed_amount: Decimal`
    - `row_index: int`
  - Define `parse_rbc_csv(content: bytes | str, expected_account_type: str) -> list[NormalizedRbcRow]`:
    - Decode content as UTF-8 (handling BOM if present).
    - Validate exact 8 header columns (case-insensitive, whitespace-trimmed): `Account Type`, `Account Number`, `Transaction Date`, `Cheque Number`, `Description 1`, `Description 2`, `CAD$`, `USD$`. Raise `ValueError` if header does not conform.
    - For each non-empty data row:
      - Strip all values.
      - Validate `row["Account Type"].lower() == expected_account_type.lower()`. Raise `ValueError` (`"File contains invalid Account Type '{actual}', expected '{expected_account_type}'"`) if any row fails.
      - Parse `Transaction Date` from `M/D/YYYY` (e.g. `7/2/2026`) or `YYYY-MM-DD` into `datetime.date`.
      - Normalize description: collapse runs of multiple spaces inside `Description 1` and `Description 2` to a single space. If `Description 2` is non-empty, merge as `f"{desc1} - {desc2}"`, else `desc1`.
      - Parse `CAD$` as Decimal:
        - If Chequing: preserve sign.
        - If Mastercard: negate amount (`signed_amount = -raw_cad`).
    - Sort parsed rows chronologically by date.
  - Define `resolve_category_for_row(row: NormalizedRbcRow, wave_categories: list[WaveCategory]) -> tuple[str, bool]`:
    - Hardcoded matching rules (case-insensitive):
      - `description.lower() == "activity fee"` -> `"Bank Service Charges"` (Chequing)
      - `description.lower() == "monthly fee"` -> `"Bank Service Charges"` (Chequing)
      - `description.lower() == "other loan - loan interest"` -> `"Interest Expense"` (Chequing)
      - `description.lower().startswith("purchase interest")` -> `"Interest Expense"` (Mastercard)
      - `description.lower() == "wave pro toronto"` -> `"Accounting Fees"` (Mastercard)
    - If description matches a hardcoded rule, search `wave_categories` for a category matching the target name (case-insensitive). If found, return `(matched_cat.wave_account_id, True)`.
    - If no rule matches or target category not found in `wave_categories`:
      - If `signed_amount < 0`: return `(uncategorized_expense_id, False)`.
      - If `signed_amount > 0`: return `(uncategorized_income_id or uncategorized_expense_id, False)`.
  - Include automated unit tests in [`api/tests/test_checklist.py`](file:///D:/src/personal/wrangler/api/tests/test_checklist.py) covering header checks, account type mismatch rejection, space collapsing, sign inversion, and auto-categorization mapping.

### 2.3 Checklist State Management & Wave Synchronization Service
- **File:** [`api/src/services/checklist/service.py`](file:///D:/src/personal/wrangler/api/src/services/checklist/service.py)
- **Description:** Implement checklist database queries, month-by-month soft cap carry-forward initialization, and direct Wave transaction orchestration.
- **Details:**
  - `get_or_create_config(db: Session) -> ChecklistConfig`:
    - Retrieve singleton row with `id = 1` or create with default values.
  - `update_config(db: Session, update_data: ChecklistConfigUpdate) -> ChecklistConfig`:
    - Update specified non-null fields and persist.
  - `get_or_create_monthly_checklist(db: Session, year_month: str, config: ChecklistConfig) -> MonthlyChecklist`:
    - Validate `year_month` matches `^\d{4}-(0[1-9]|1[0-2])$`.
    - If existing record found, return it.
    - Otherwise, find the latest record where `existing.year_month < year_month` ordered by `year_month DESC`.
    - If prior record exists:
      - `prior_soft_cap = prior_record.current_soft_cap`
      - `monthly_loc_reduction = prior_record.monthly_loc_reduction`
      - `tax_rate = prior_record.tax_rate`
    - If no prior record exists:
      - Use defaults: `prior_soft_cap = Decimal("17600.00")`, `monthly_loc_reduction = Decimal("400.00")`, `tax_rate = Decimal("12.00")`.
    - Create, persist, and return the newly initialized `MonthlyChecklist`.
  - `build_wave_cash_flow_url(slug: str, year_month: str) -> str`:
    - Extract year and month, calculate `last_day = calendar.monthrange(year, month)[1]`.
    - Return `f"https://next.waveapps.com/{slug}/reports/cash-flow?end={year_month}-{last_day:02d}&start={year_month}-01"`.
  - `sync_rbc_feed_to_wave(db: Session, year_month: str, account_type: str, file_bytes: bytes) -> RbcCsvSyncResponse`:
    - Verify `ChecklistConfig` has a valid `company_id`, company has `wave_api_token` and `wave_business_id`.
    - Resolve target anchor account ID (`chequing_wave_account_id` or `mastercard_wave_account_id`). Raise `HTTPException(400)` if unconfigured.
    - Parse CSV via `parse_rbc_csv`.
    - Fetch active `wave_categories` for the company.
    - Iterate chronologically through normalized rows:
      - Determine category via `resolve_category_for_row`.
      - Construct `external_id = f"wrangler_rbc_{account_type}_{row.date}_{row.row_index}_{abs(row.signed_amount)}"`.
      - Determine anchor direction and line item balance:
        - If `signed_amount < 0`: anchor `WITHDRAWAL`, lineItem `INCREASE`.
        - If `signed_amount > 0`: anchor `DEPOSIT`, lineItem `INCREASE` (or `DECREASE` if using uncategorized expense fallback).
      - Call `WaveClient.create_money_transaction(...)`.
    - On completion:
      - Update `checklist_config.last_chequing_tx_date` or `checklist_config.last_mastercard_tx_date` with `max(current, max_csv_date)`.
      - Append `"import_chequing"` or `"import_mastercard"` to `MonthlyChecklist.completed_steps` (deduplicating).
      - Commit and return `RbcCsvSyncResponse`.
  - `sync_tax_accrual_to_wave(db: Session, year_month: str, net_operating_cash: Decimal | None, tax_rate: Decimal | None) -> MonthlyChecklist`:
    - Verify `tax_expense_wave_account_id` and `tax_payable_wave_account_id` are configured.
    - Update `net_operating_cash` and `tax_rate` if overrides are provided.
    - Recompute `tax_reserve_amount`. If `tax_reserve_amount is None` or `<= Decimal("0.00")`, raise `HTTPException(400, "Tax reserve amount must be greater than $0.00 to post a journal entry")`.
    - Calculate last calendar day of `year_month`.
    - Call `WaveClient.create_money_transaction`:
      - `external_id = f"wrangler_tax_accrual_{company.id}_{year_month}"`
      - `date = f"{year_month}-{last_day:02d}"`
      - `description = f"Corporate Tax Accrual ({year_month})"`
      - `amount = tax_reserve_amount`
      - `anchor_account_id = config.tax_payable_wave_account_id`
      - `category_account_id = config.tax_expense_wave_account_id`
      - `anchor_direction = "WITHDRAWAL"`
      - `line_balance = "INCREASE"`
    - Record `tax_accrual_wave_tx_id = wave_tx_id`.
    - Append `"calculate_net_cash_and_tax"` to `MonthlyChecklist.completed_steps`.
    - Commit and return `MonthlyChecklist`.

### 2.4 Checklist API Router & Main App Registration
- **Files:** [`api/src/routers/checklist.py`](file:///D:/src/personal/wrangler/api/src/routers/checklist.py), [`api/src/main.py`](file:///D:/src/personal/wrangler/api/src/main.py)
- **Description:** Implement all checklist REST endpoints and register the router on the FastAPI application.
- **Details:**
  - Create router with `prefix="/api/checklist"`:
    - `GET /config` -> returns `ChecklistConfigResponse`.
    - `PUT /config` -> updates and returns `ChecklistConfigResponse`.
    - `GET /wave-accounts/{company_id}` -> returns `WaveAccountsGroupedResponse` (`bank_and_cc_accounts`, `expense_accounts`, `liability_accounts`).
    - `GET /months/{year_month}` -> returns `MonthlyChecklistResponse`.
    - `PATCH /months/{year_month}` -> updates editable fields, returns recomputed `MonthlyChecklistResponse`.
    - `POST /months/{year_month}/sync-rbc-csv` -> accepts `account_type: str = Form(...)`, `file: UploadFile = File(...)`, returns `RbcCsvSyncResponse`.
    - `POST /months/{year_month}/sync-tax-accrual` -> accepts optional `TaxAccrualSyncRequest`, returns `MonthlyChecklistResponse`.
  - Include router in [`api/src/main.py`](file:///D:/src/personal/wrangler/api/src/main.py):
    - `from routers.checklist import router as checklist_router`
    - `app.include_router(checklist_router)`

### 2.5 Backend Integration Test Suite
- **File:** [`api/tests/test_checklist.py`](file:///D:/src/personal/wrangler/api/tests/test_checklist.py)
- **Description:** Implement comprehensive test suite covering configuration, RBC parsing, Wave sync, month carry-forward, and corporate tax accrual.
- **Details:**
  - Test `GET /api/checklist/config` initializes singleton `id=1` with default slug and null accounts.
  - Test `PUT /api/checklist/config` saves Wave account IDs and manual high-water dates.
  - Test `GET /api/checklist/wave-accounts/{company_id}` groups accounts into bank/cc, expense, and liability accounts.
  - Test `GET /api/checklist/months/2026-09` initializes with initial soft cap `$17,600.00` and monthly reduction `$400.00`.
  - Test month-to-month soft cap carry-forward: request `GET /api/checklist/months/2026-10` and verify `prior_soft_cap == 17200.00` and `current_soft_cap == 16800.00`.
  - Test `PATCH /api/checklist/months/2026-09` updates `net_operating_cash`, `tax_rate`, and recalculates `tax_reserve_amount`.
  - Test `POST /api/checklist/months/2026-09/sync-rbc-csv`:
    - Chequing feed upload: merges descriptions (`"Other loan - Loan interest"`), collapses spaces (`"Mobile cheque deposit - 5318"`), auto-codes fees to `Bank Service Charges`, verifies `UNCATEGORIZED_INCOME` deposit and `UNCATEGORIZED_EXPENSE` withdrawal, asserts `last_chequing_tx_date` is updated, and confirms `import_chequing` is marked complete.
    - Mastercard feed upload: verifies positive charges are negated (`WITHDRAWAL`) and negative payments are negated (`DEPOSIT`), auto-codes `WAVE PRO TORONTO` and `PURCHASE INTEREST`, verifies `last_mastercard_tx_date` update, and confirms `import_mastercard` is marked complete.
    - Mismatch rejection: uploading Mastercard CSV to chequing step returns `400 Bad Request`.
  - Test `POST /api/checklist/months/2026-09/sync-tax-accrual`:
    - Fails with `400` if tax accounts are not configured or tax reserve is zero.
    - Executes `WaveClient.create_money_transaction` dated `2026-09-30` with `anchor.direction = "WITHDRAWAL"` on `tax_payable` and `lineItems[0].balance = "INCREASE"` on `tax_expense`.
    - Persists `tax_accrual_wave_tx_id` and marks `calculate_net_cash_and_tax` complete.
  - Test Step 9 Maximum Safe Draw arithmetic: `current_soft_cap - tax_liability - actual_loc_balance`.

---

## Phase 3: Frontend Pinia Store & TypeScript API Client

### 3.1 TypeScript Types & API Client Service
- **Files:** [`web/src/types/checklist.ts`](file:///D:/src/personal/wrangler/web/src/types/checklist.ts), [`web/src/services/api/checklist.ts`](file:///D:/src/personal/wrangler/web/src/services/api/checklist.ts)
- **Description:** Implement TypeScript interfaces and HTTP client functions wrapping the `/api/checklist` endpoints.
- **Details:**
  - Define interfaces in `web/src/types/checklist.ts`:
    - `ChecklistConfig`
    - `ChecklistConfigUpdatePayload`
    - `WaveAccountItem`
    - `WaveAccountsGrouped`
    - `MonthlyChecklist`
    - `MonthlyChecklistPatchPayload`
    - `RbcCsvSyncResult`
    - `TaxAccrualSyncPayload`
  - Implement client functions in `web/src/services/api/checklist.ts`:
    - `fetchChecklistConfig(): Promise<ChecklistConfig>`
    - `updateChecklistConfig(payload: ChecklistConfigUpdatePayload): Promise<ChecklistConfig>`
    - `fetchGroupedWaveAccounts(companyId: string): Promise<WaveAccountsGrouped>`
    - `fetchMonthlyChecklist(yearMonth: string): Promise<MonthlyChecklist>`
    - `patchMonthlyChecklist(yearMonth: string, payload: MonthlyChecklistPatchPayload): Promise<MonthlyChecklist>`
    - `syncRbcCsv(yearMonth: string, accountType: 'chequing' | 'mastercard', file: File): Promise<RbcCsvSyncResult>`
    - `syncTaxAccrual(yearMonth: string, payload?: TaxAccrualSyncPayload): Promise<MonthlyChecklist>`

### 3.2 Checklist Pinia Store
- **File:** [`web/src/stores/checklist.ts`](file:///D:/src/personal/wrangler/web/src/stores/checklist.ts)
- **Description:** Manage checklist application state, reactive month selection, step completions, and synchronization workflows.
- **Details:**
  - State:
    - `config: ChecklistConfig | null = null`
    - `currentMonth: MonthlyChecklist | null = null`
    - `selectedYearMonth: string`: initialize to previous calendar month in `YYYY-MM` format (e.g. if today is `2026-10-26`, defaults to `"2026-09"`).
    - `groupedWaveAccounts: WaveAccountsGrouped | null = null`
    - `isLoading: boolean = false`
    - `isSyncingCsv: boolean = false`
    - `isSyncingTax: boolean = false`
  - Getters:
    - `completedStepsCount: number`: `currentMonth?.completed_steps.length ?? 0`
    - `isStepCompleted: (stepKey: string) => boolean`
    - `isChequingConfigured: boolean`: whether `config?.chequing_wave_account_id` is truthy
    - `isMastercardConfigured: boolean`: whether `config?.mastercard_wave_account_id` is truthy
    - `canSyncTaxAccrual: boolean`: whether config has tax accounts, `tax_reserve_amount > 0`, and not already synced
  - Actions:
    - `fetchConfig()`
    - `updateConfig(payload: ChecklistConfigUpdatePayload)`
    - `fetchWaveAccounts(companyId: string)`
    - `fetchMonth(yearMonth: string)`
    - `updateMonth(yearMonth: string, payload: MonthlyChecklistPatchPayload)`
    - `toggleStep(stepKey: string, completed: boolean)`: optimistic local update of `completed_steps` followed by debounced `PATCH`
    - `syncRbcCsv(yearMonth: string, accountType: 'chequing' | 'mastercard', file: File)`: performs upload, refreshes config and month state
    - `syncTaxAccrual(yearMonth: string, netCash?: string, taxRate?: string)`: executes sync, updates `currentMonth`
    - `setSelectedYearMonth(yearMonth: string)`: updates month and invokes `fetchMonth`
    - `navigateMonth(offset: -1 | 1)`: increments/decrements calendar month and fetches new month state

### 3.3 Pinia Store Unit Tests
- **File:** [`web/tests/checklistStore.test.ts`](file:///D:/src/personal/wrangler/web/tests/checklistStore.test.ts)
- **Description:** Implement unit tests verifying Pinia store reactivity, default month calculation, and action dispatching.
- **Details:**
  - Test default `selectedYearMonth` evaluates to the previous calendar month.
  - Test `toggleStep` adds or removes step keys from `completed_steps` and issues PATCH request.
  - Test `fetchMonth` loads month state and derives `completedStepsCount`.
  - Test `syncRbcCsv` and `syncTaxAccrual` error handling and state loading flags.

---

## Phase 4: Frontend UI Components, Navigation & View Integration

### 4.1 Navigation Drawer & Route Configuration
- **Files:** [`web/src/layouts/nav.ts`](file:///D:/src/personal/wrangler/web/src/layouts/nav.ts), [`web/src/router/routes.ts`](file:///D:/src/personal/wrangler/web/src/router/routes.ts)
- **Description:** Add the Checklist navigation item to the sidebar and register the view route.
- **Details:**
  - In `web/src/layouts/nav.ts`:
    - Add entry to `navItems`: `{ name: "checklist", label: "Checklist", icon: "fact_check", path: "/checklist" }`.
  - In `web/src/router/routes.ts`:
    - Under the main layout route children, add `/checklist` mapping to `() => import("../views/ChecklistView.vue")` with `requiresAuth: true`.

### 4.2 Checklist Settings Dialog Component
- **File:** [`web/src/components/ChecklistSettingsDialog.vue`](file:///D:/src/personal/wrangler/web/src/components/ChecklistSettingsDialog.vue)
- **Description:** Implement settings modal for configuring target company entity, Wave account mappings, and date cutoffs.
- **Details:**
  - Dialog modal with `v-model` open state.
  - Form fields:
    - **Target Company:** `QSelect` of available companies. Selecting a company triggers `fetchWaveAccounts(companyId)`.
    - **Wave Chequing Account:** `QSelect` populated with `groupedWaveAccounts.bank_and_cc_accounts`.
    - **Wave Mastercard Account:** `QSelect` populated with `groupedWaveAccounts.bank_and_cc_accounts`.
    - **Corporate Tax Expense Account:** `QSelect` populated with `groupedWaveAccounts.expense_accounts`.
    - **Taxes Payable Liability Account:** `QSelect` populated with `groupedWaveAccounts.liability_accounts`.
    - **Wave Web Business Slug:** `QInput` with default value `"d2977f10-6793-4504-a139-f0d6872b2628"`.
    - **Manual Cutoff Date Overrides:** `QInput` (date) for `last_chequing_tx_date` and `last_mastercard_tx_date`.
  - Actions: Save button (`updateConfig`) and Cancel button with user notifications via Quasar `Notify`.

### 4.3 Monthly Bookkeeping Checklist View
- **File:** [`web/src/views/ChecklistView.vue`](file:///D:/src/personal/wrangler/web/src/views/ChecklistView.vue)
- **Description:** Implement the full 9-step monthly bookkeeping checklist view with reactive calculators and embedded Wave synchronization widgets.
- **Details:**
  - **Header Bar:**
    - Title: `"Monthly Bookkeeping Checklist — Michelle Dryden LTD"`.
    - Month selector: Previous Month (`<`), Month input/picker (`YYYY-MM`), Next Month (`>`).
    - Progress indicator: `QLinearProgress` + badge `"{completedCount} / 9 Completed"`.
    - "Configure Accounts" gear button opening `ChecklistSettingsDialog.vue`.
  - **Step Cards (Steps 1–9):**
    - **Step 1 (`import_chequing`) & Step 2 (`import_mastercard`):**
      - Checkbox, title, reminder description.
      - Info chip: **Last Synced Transaction Date:** `YYYY-MM-DD` (or `"Not yet synced"`).
      - Inline `QFile` picker (`accept=".csv"`, dense, outlined) and permanently visible "Sync to Wave" `QBtn` (`:disable="!file || !isAccountConfigured || isSyncing"`).
      - Summary banner displayed on completion displaying synced count and auto-categorized count.
    - **Step 3 (`allocate_loc_transfers`) & Step 4 (`reconcile_bank_accounts`):**
      - Checkbox, title, reminder description.
    - **Step 5 (`sync_external_data`):**
      - Bullet reminder regarding Amazon 2-month history export.
      - Action buttons:
        - "Open Amazon Order History" (`target="_blank"`, `icon="open_in_new"`).
        - "Go to Wrangler Import" (`to="/import"`, `icon="cloud_upload"`).
        - "Go to Export Manager" (`to="/export-manager"`, `icon="sync"`).
      - Checkbox.
    - **Step 6 (`scan_receipts`) & Step 7 (`merge_and_reimburse`):**
      - Checkbox, title, reminder description.
    - **Step 8 (`calculate_net_cash_and_tax`):**
      - Button: "Open Wave Cash Flow Report ({selectedYearMonth})" opening `currentMonth.wave_cash_flow_url` in a new tab.
      - Input row:
        - Net Cash from Operating Activities (`QInput`, prefix `"$"`).
        - Tax Rate (`QInput`, suffix `"%"`, default 12.00%).
        - Calculated Tax Reserve chip/box displaying `tax_reserve_amount`.
        - "Sync Tax Accrual to Wave" button (`:disable="!canSyncTaxAccrual || Boolean(currentMonth.tax_accrual_wave_tx_id)"`). Shows green `"Synced to Wave"` badge when `tax_accrual_wave_tx_id` exists.
      - Checkbox.
    - **Step 9 (`execute_dividends`):**
      - Button: "Open Wave Balance Sheet ({selectedYearMonth})" opening Wave balance sheet in a new tab.
      - Maximum Safe Draw Calculator grid:
        - Prior Soft Cap (`QInput`, prefix `"$"`, carried forward).
        - Monthly LOC Reduction (`QInput`, prefix `"$"`, default `$400.00`).
        - Current Soft Cap (read-only box: `prior_soft_cap - monthly_loc_reduction`).
        - Tax Liability (`QInput`, prefix `"$"`, from Wave Balance Sheet).
        - Actual LOC Balance (`QInput`, prefix `"$"`, from Wave Balance Sheet).
        - Maximum Safe Draw highlighted banner: `Current Soft Cap - Tax Liability - Actual LOC Balance` (green when positive, warning red when `<= 0`).
      - Checkbox.

### 4.4 Frontend View Integration & Component Tests
- **File:** [`web/tests/checklistView.test.ts`](file:///D:/src/personal/wrangler/web/tests/checklistView.test.ts)
- **Description:** Implement Vitest component tests verifying user interactions, dynamic formulas, persistent button affordances, and dialog workflows.
- **Details:**
  - Test `ChecklistView.vue` renders all 9 steps in order with titles and descriptions.
  - Test month selector defaults to the previous calendar month (`YYYY-MM`).
  - Test Step 8 dynamically updates Calculated Tax Reserve and Wave Cash Flow link when editing Net Cash from Operating Activities.
  - Test Step 9 dynamically updates Current Soft Cap and Maximum Safe Draw when editing Soft Cap and liability inputs.
  - Test persistent affordance invariants: "Sync to Wave" and "Sync Tax Accrual" buttons remain visible on screen and are disabled when prerequisites are missing.
  - Test opening and submitting `ChecklistSettingsDialog.vue`.
