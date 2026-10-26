---
status: Draft
subsystems:
  - Accounting Export
  - Ingestion & Importers
  - Platform & Shell
amendments: []
supersedes: null
superseded_by: null
---

# Monthly Bookkeeping Checklist & RBC Bank Feed Wave Sync

**Status:** Draft  
**Subsystems:** Accounting Export, Ingestion & Importers, Platform & Shell  
**Date:** 2026-10-26  

---

## 1. Goal & Architectural Overview

Monthly bookkeeping for **Michelle Dryden LTD** follows a repeatable sequence of steps across RBC Online Banking, Wave Accounting, Amazon Order History, and cash/dividend tracking. Previously, this workflow required manual CSV editing (concatenating RBC description columns and flipping Mastercard signs), manual tracking of date cutoffs across bank exports, manual corporate tax journal entries, and an external spreadsheet tracker to compute the monthly LOC Soft Cap and Maximum Safe Draw.

This specification introduces a dedicated **Monthly Checklist** subsystem in Wrangler tailored for **Michelle Dryden LTD** with:
1. **Month-by-Month Persistent State (`YYYY-MM`):** Tracks step completion, financial inputs, Wave sync statuses, and carry-forward LOC Soft Cap balances per month, defaulting to the previous calendar month (`YYYY-MM`).
2. **Account Cutoff Tracking:** Stores and displays the `last_chequing_tx_date` and `last_mastercard_tx_date` across uploads so the user knows the exact date range to pull from RBC Online Banking.
3. **Direct RBC CSV-to-Wave Synchronization (Steps 1 & 2):**
   - **Step 1 (Import Chequing Feed)** and **Step 2 (Import Mastercard Feed)** accept RBC CSV uploads directly inside the checklist step.
   - Normalizes RBC dates (`M/D/YYYY` -> `YYYY-MM-DD`), concatenates `Description 1` and `Description 2` (`"{Description 1} - {Description 2}"`), negates `MasterCard` amounts so charges post as withdrawals and payments post as deposits, auto-categorizes recurring known descriptions, and pushes all rows directly to Wave via `moneyTransactionCreate`.
4. **Integrated Corporate Tax Accrual (Step 8):**
   - Deep-links to the Wave Cash Flow report pre-populated with the first and last day of the checklist month.
   - Accepts **Net Cash from Operating Activities** and **Tax Rate (%)** (defaulted to `12%`), computes the **Tax Reserve**, and provides a 1-click **"Sync Tax Accrual to Wave"** button that posts the month-end accrual entry (Debit: *Corporate Tax Expense*, Credit: *Taxes Payable*).
5. **Integrated Maximum Safe Draw Calculator (Step 9):**
   - Replaces the external ShellCo spreadsheet tracker by carrying forward the LOC **Soft Cap** from month to month, subtracting the monthly LOC reduction payment (defaulted to `$400.00` or the prior month's value), and computing:
     $$\text{Maximum Safe Draw} = \text{Soft Cap} - \text{Tax Liability} - \text{Actual LOC Balance}$$

### 1.1 Architectural Scope & Isolation Invariant
Corporate bank feed CSVs (`shellco-chq.csv`, `shellco-mc.csv`) and Corporate Tax Accrual entries belong 100% to the target business entity. Therefore, they **bypass Wrangler's shared Personal/Business Staging (`staged_transactions`) and Ledger (`transactions`) tables**, streaming directly to Wave via the GraphQL client while recording checklist progress and high-water transaction dates in dedicated checklist tables.

---

## 2. End-to-End Workflow & Checklist Steps

Each monthly checklist instance (`YYYY-MM`) presents 9 ordered steps. Every step includes a **Step Number**, **Title**, **Reminder Description**, **Completion Checkbox**, and (where applicable) an embedded **Interactive Action Panel**:

| Step | Key | Title | Reminder Description | Embedded Action / Widget |
| :- | :--- | :--- | :--- | :--- |
| **1** | `import_chequing` | **Import Chequing Feed** | Pull RBC Chequing transactions into Wave. | Displays **Last Chequing Transaction Date**. File upload for RBC Chequing CSV (`shellco-chq.csv`) + **"Sync to Wave"** button. Auto-codes known recurring items and pushes the rest as Uncategorized. |
| **2** | `import_mastercard` | **Import Mastercard Feed** | Pull RBC Mastercard transactions into Wave. | Displays **Last Mastercard Transaction Date**. File upload for RBC Mastercard CSV (`shellco-mc.csv`) + **"Sync to Wave"** button. Reverses `CAD$` signs, auto-codes known recurring items, and pushes the rest as Uncategorized. |
| **3** | `allocate_loc_transfers` | **Allocate LOC Transfers** | Code Chequing transactions (`LOAN PAYMENT` and `LOAN CREDIT`) that moved to or from the LOC to establish the corresponding LOC ledger entries. | Checkbox only. |
| **4** | `reconcile_bank_accounts` | **Reconcile Bank Accounts** | Perform the official month-end reconciliation against the PDF bank statements and mark the imported transactions as reviewed. | Checkbox only. |
| **5** | `sync_external_data` | **Sync External Data** | Use the Amazon Order History Reporter extension to export transactions for the past 2 months (since Wrangler detects duplicates and Amazon does weird things with transactions, going back further ensures nothing is missed), then import into Wrangler and sync business allocations to Wave. | External button to [Amazon Order History](https://www.amazon.ca/gp/css/order-history?ref_=nav_orders_first) + quick navigation buttons to Wrangler's **Import** (`/import`) and **Export Manager** (`/export-manager`) views + Checkbox. |
| **6** | `scan_receipts` | **Scan Receipts** | Scan physical receipts directly into Wave, which will generate new, unreviewed transactions in your ledger. | Checkbox only. |
| **7** | `merge_and_reimburse` | **Merge and Reimburse** | Review the newly generated receipt transactions. Merge matches into the existing, reviewed bank transactions. For unmatched receipts, categorize the expense and assign the transaction to the Reimbursement account to log the personal card outlay. | Checkbox only. |
| **8** | `calculate_net_cash_and_tax` | **Calculate Net Cash & Accrue Corporate Tax** | Run the Wave Cash Flow report for the completed month to determine your final Net Cash from Operating Activities, then post a Journal Entry dated the last day of the month for the calculated Tax Reserve (Debit: Taxes - Corporate Tax; Credit: Taxes Payable). | Dynamic link button to Wave Cash Flow Report (`start=YYYY-MM-01`, `end=YYYY-MM-last-day`). Inputs for **Net Cash from Operating Activities** and **Tax Rate (%)** (default `12%`). Displays computed **Tax Reserve** + **"Sync Tax Accrual to Wave"** button + Checkbox. |
| **9** | `execute_dividends` | **Calculate Safe Draw & Execute Dividends** | Calculate the Maximum Safe Draw (`Soft Cap - Tax Liability - Actual LOC Balance`), execute the physical cash transfer to your personal account, and record it in Wave as a shareholder draw. | Inputs for **Prior Soft Cap** (carried forward), **Monthly LOC Reduction** (defaulted to prior month's value / `$400.00`), **Tax Liability**, and **Actual LOC Balance**. Displays computed **Current Soft Cap** and **Maximum Safe Draw** + Checkbox. |

---

## 3. RBC CSV Parsing, Transformation & Auto-Categorization Rules

### 3.1 Input Format Validation
Both RBC Chequing and RBC Mastercard CSV exports conform to the 8-column header:
```csv
Account Type,Account Number,Transaction Date,Cheque Number,Description 1,Description 2,CAD$,USD$
```
- Leading/trailing whitespace in headers and cell values must be stripped.
- Empty trailing lines must be ignored.
- **Step 1 (`import_chequing`) Validation:** Rejects the file with `400 Bad Request` if any non-empty data row has an `Account Type` (case-insensitive) other than `"Chequing"`.
- **Step 2 (`import_mastercard`) Validation:** Rejects the file with `400 Bad Request` if any non-empty data row has an `Account Type` (case-insensitive) other than `"MasterCard"`.

### 3.2 Field Normalization Rules
For each row in the uploaded CSV:
1. **Date (`Transaction Date`):**
   - Parse `M/D/YYYY` (e.g., `7/2/2026`, `10/22/2026`) or `YYYY-MM-DD` into a `datetime.date` object and format as ISO `YYYY-MM-DD`.
2. **Description (`Description 1` & `Description 2`):**
   - Collapse runs of multiple internal spaces within `Description 1` and `Description 2` into a single space (e.g., `"Mobile cheque deposit -     5318"` -> `"Mobile cheque deposit - 5318"`).
   - If `Description 2` is non-empty after stripping:
     $$\text{description} = \text{f"\{desc1\} - \{desc2\}"}$$
   - Otherwise:
     $$\text{description} = \text{desc1}$$
3. **Signed Amount (`CAD$`):**
   - Parse `CAD$` as `Decimal`.
   - For **Chequing (`Account Type == "Chequing"`)**: Retain the exact sign from `CAD$` (withdrawals/fees are negative; deposits/credits are positive).
   - For **Mastercard (`Account Type == "MasterCard"`)**: Negate the parsed amount (`signed_amount = -raw_cad`) so positive credit card charges become negative (`WITHDRAWAL`) and negative credit card payments/credits become positive (`DEPOSIT`).

### 3.3 Hardcoded Auto-Categorization Rules
When syncing a normalized row to Wave, Wrangler matches the normalized `description` (case-insensitively) against the following hardcoded rule map:

| Normalized Description Match (Case-Insensitive) | Target Wave Expense Category Name | Applies To |
| :--- | :--- | :--- |
| `description.lower() == "activity fee"` | `"Bank Service Charges"` | Chequing |
| `description.lower() == "monthly fee"` | `"Bank Service Charges"` | Chequing |
| `description.lower() == "other loan - loan interest"` | `"Interest Expense"` | Chequing |
| `description.lower().startswith("purchase interest")` | `"Interest Expense"` | Mastercard |
| `description.lower() == "wave pro toronto"` | `"Accounting Fees"` | Mastercard |

- **Category Lookup & Fallback:**
  - Wrangler looks up the target category name (case-insensitively) among the company's cached Wave categories (`wave_categories`).
  - If the description does not match any hardcoded rule (e.g., `LOAN PAYMENT`, `LOAN CREDIT`, `Mobile cheque deposit - 5318`, `e-Transfer sent - MAFCN`, `CPC HEALTHCARE FINGAL`), or if the named category does not exist in `wave_categories`:
    - When `signed_amount < 0` (withdrawal / charge): Fall back to the company's Wave **Uncategorized Expense** account (`subtype == "UNCATEGORIZED_EXPENSE"`).
    - When `signed_amount > 0` (deposit / payment / credit): Fall back to the company's Wave **Uncategorized Income** account (`subtype == "UNCATEGORIZED_INCOME"`).

### 3.4 Double-Entry Mapping in Wave (`moneyTransactionCreate`)
For each row in the uploaded CSV:
- **When `signed_amount < 0` (Withdrawal from Chequing / Charge on Mastercard):**
  - `anchor`: `{ "accountId": step_anchor_account_id, "amount": float(abs(signed_amount)), "direction": "WITHDRAWAL" }`
  - `lineItems`: `[{ "accountId": resolved_expense_or_uncat_expense_id, "amount": float(abs(signed_amount)), "balance": "INCREASE" }]`
- **When `signed_amount > 0` (Deposit into Chequing / Payment or Credit on Mastercard):**
  - `anchor`: `{ "accountId": step_anchor_account_id, "amount": float(abs(signed_amount)), "direction": "DEPOSIT" }`
  - `lineItems`: `[{ "accountId": uncategorized_income_account_id, "amount": float(abs(signed_amount)), "balance": "INCREASE" }]`
  *(Note: If `uncategorized_income_account_id` is unavailable in Wave, fallback to `uncategorized_expense_account_id` with `"balance": "DECREASE"`).*

### 3.5 Last Transaction Date Tracking
Upon successfully syncing all rows in an uploaded CSV:
- Let `max_csv_date = max(row.date for row in rows)`.
- For Step 1 (Chequing): Update `checklist_config.last_chequing_tx_date = max(checklist_config.last_chequing_tx_date, max_csv_date)` (or set to `max_csv_date` if previously `None`).
- For Step 2 (Mastercard): Update `checklist_config.last_mastercard_tx_date = max(checklist_config.last_mastercard_tx_date, max_csv_date)` (or set to `max_csv_date` if previously `None`).
- Automatically add `"import_chequing"` (or `"import_mastercard"`) to `monthly_checklist.completed_steps` for the active month.

---

## 4. Data Model & Database Migration

### 4.1 `ChecklistConfig` Model (`api/src/models/checklist.py`)
Stores the singleton configuration and cross-month high-water dates for the Michelle Dryden LTD checklist:

```python
class ChecklistConfig(Base):
    __tablename__ = "checklist_configs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    company_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("companies.id", ondelete="SET NULL"), nullable=True
    )
    chequing_wave_account_id: Mapped[str | None] = mapped_column(String, nullable=True)
    chequing_wave_account_name: Mapped[str | None] = mapped_column(String, nullable=True)
    mastercard_wave_account_id: Mapped[str | None] = mapped_column(String, nullable=True)
    mastercard_wave_account_name: Mapped[str | None] = mapped_column(String, nullable=True)
    tax_expense_wave_account_id: Mapped[str | None] = mapped_column(String, nullable=True)
    tax_expense_wave_account_name: Mapped[str | None] = mapped_column(String, nullable=True)
    tax_payable_wave_account_id: Mapped[str | None] = mapped_column(String, nullable=True)
    tax_payable_wave_account_name: Mapped[str | None] = mapped_column(String, nullable=True)
    wave_web_business_slug: Mapped[str] = mapped_column(
        String, nullable=False, default="d2977f10-6793-4504-a139-f0d6872b2628"
    )
    last_chequing_tx_date: Mapped[datetime.date | None] = mapped_column(Date, nullable=True)
    last_mastercard_tx_date: Mapped[datetime.date | None] = mapped_column(Date, nullable=True)
```

### 4.2 `MonthlyChecklist` Model (`api/src/models/checklist.py`)
Stores the month-by-month checklist state (`YYYY-MM`):

```python
class MonthlyChecklist(Base):
    __tablename__ = "monthly_checklists"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    year_month: Mapped[str] = mapped_column(String(7), unique=True, index=True, nullable=False)
    completed_steps_json: Mapped[str] = mapped_column(String, nullable=False, default="[]")

    # Step 8: Calculate Net Cash & Accrue Corporate Tax
    net_operating_cash: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    tax_rate: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False, default=Decimal("12.00"))
    tax_accrual_wave_tx_id: Mapped[str | None] = mapped_column(String, nullable=True)

    # Step 9: Calculate Safe Draw & Execute Dividends
    prior_soft_cap: Mapped[Decimal] = mapped_column(
        Numeric(12, 2), nullable=False, default=Decimal("17600.00")
    )
    monthly_loc_reduction: Mapped[Decimal] = mapped_column(
        Numeric(12, 2), nullable=False, default=Decimal("400.00")
    )
    tax_liability: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    actual_loc_balance: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
```

#### Computed Properties on `MonthlyChecklist`:
1. **`tax_reserve_amount` (`Decimal | None`):**
   - If `net_operating_cash is None`: returns `None`.
   - If `net_operating_cash <= Decimal("0.00")`: returns `Decimal("0.00")`.
   - Otherwise: ` (net_operating_cash * (tax_rate / Decimal("100"))).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)`.
2. **`current_soft_cap` (`Decimal`):**
   - `(prior_soft_cap - monthly_loc_reduction).quantize(Decimal("0.01"))`.
   - *(Note: With default initial seed `prior_soft_cap = 17600.00` and `monthly_loc_reduction = 400.00`, `current_soft_cap` evaluates to `17200.00`).*
3. **`maximum_safe_draw` (`Decimal | None`):**
   - If `tax_liability is None` or `actual_loc_balance is None`: returns `None`.
   - Otherwise: `(current_soft_cap - tax_liability - actual_loc_balance).quantize(Decimal("0.01"))`.

#### Month Initialization & Carry-Forward Logic:
When `GET /api/checklist/months/{year_month}` is requested for a `year_month` that does not yet exist in `monthly_checklists`:
1. Query the most recent existing `MonthlyChecklist` record where `existing.year_month < year_month` ordered by `year_month DESC`.
2. If a prior record exists:
   - Set `prior_soft_cap = prior_record.current_soft_cap` (i.e. `prior_record.prior_soft_cap - prior_record.monthly_loc_reduction`).
   - Set `monthly_loc_reduction = prior_record.monthly_loc_reduction`.
   - Set `tax_rate = prior_record.tax_rate`.
3. If no prior record exists:
   - Use defaults (`prior_soft_cap = Decimal("17600.00")`, `monthly_loc_reduction = Decimal("400.00")`, `tax_rate = Decimal("12.00")`).
4. Persist and return the newly initialized `MonthlyChecklist` record.

### 4.3 Wave Category Caching Enhancement (`api/src/services/wave/client.py`)
To support:
1. Selecting Liability accounts (e.g. `Taxes Payable`) in Checklist Settings, and
2. Routing positive bank statement deposits to Wave's system `Uncategorized Income` (`UNCATEGORIZED_INCOME`) account:

Update [`WaveClient.get_business_accounts`](file:///D:/src/personal/wrangler/api/src/services/wave/client.py#L170-L223) and [`_sync_categories_for_company`](file:///D:/src/personal/wrangler/api/src/routers/companies.py#L79-L112):
- In `WaveClient.get_business_accounts`:
  - Include all non-archived `LIABILITY` accounts in `anchor_accounts` (or return `liability_accounts: list[WaveAccount]`) so `Taxes Payable` can be selected as the Tax Payable liability account in Checklist Settings.
  - Include any non-archived `REVENUE` / `INCOME` account where `subtype.value == "UNCATEGORIZED_INCOME"` in `expense_categories` (with `is_uncategorized = True` and `type = "REVENUE"` / `"INCOME"`) so it is cached in `wave_categories` alongside `UNCATEGORIZED_EXPENSE`.
  - Ensure [`get_company_wave_categories`](file:///D:/src/personal/wrangler/api/src/routers/companies.py#L369-L384) and Export Manager category dropdowns filter to `WaveCategory.account_type == "EXPENSE"` so `Uncategorized Income` never clutters Expense category dropdowns in Export Manager.

### 4.4 Alembic Migration
Create a new migration in `api/alembic/versions/` revising current head `d5c8e3f1a2b7`:
- Create table `checklist_configs`.
- Create table `monthly_checklists` with unique index on `year_month`.

---

## 5. Backend REST API Specification (`api/src/routers/checklist.py`)

Register a new router `checklist_router` at prefix `/api/checklist` in [`api/src/main.py`](file:///D:/src/personal/wrangler/api/src/main.py).

### 5.1 `GET /api/checklist/config`
- **Action:** Retrieves the singleton `ChecklistConfig` (creating the default row `id=1` if not yet present).
- **Response (`200 OK`):**
  ```json
  {
    "company_id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
    "company_name": "Michelle Dryden LTD",
    "is_wave_connected": true,
    "chequing_wave_account_id": "QWNjb3VudDox",
    "chequing_wave_account_name": "RBC Chequing",
    "mastercard_wave_account_id": "QWNjb3VudDoy",
    "mastercard_wave_account_name": "RBC Mastercard",
    "tax_expense_wave_account_id": "QWNjb3VudDoz",
    "tax_expense_wave_account_name": "Taxes - Corporate Tax",
    "tax_payable_wave_account_id": "QWNjb3VudDo0",
    "tax_payable_wave_account_name": "Taxes Payable",
    "wave_web_business_slug": "d2977f10-6793-4504-a139-f0d6872b2628",
    "last_chequing_tx_date": "2026-09-28",
    "last_mastercard_tx_date": "2026-09-24"
  }
  ```

### 5.2 `PUT /api/checklist/config`
- **Request Body:**
  ```json
  {
    "company_id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
    "chequing_wave_account_id": "QWNjb3VudDox",
    "chequing_wave_account_name": "RBC Chequing",
    "mastercard_wave_account_id": "QWNjb3VudDoy",
    "mastercard_wave_account_name": "RBC Mastercard",
    "tax_expense_wave_account_id": "QWNjb3VudDoz",
    "tax_expense_wave_account_name": "Taxes - Corporate Tax",
    "tax_payable_wave_account_id": "QWNjb3VudDo0",
    "tax_payable_wave_account_name": "Taxes Payable",
    "wave_web_business_slug": "d2977f10-6793-4504-a139-f0d6872b2628",
    "last_chequing_tx_date": "2026-09-28",
    "last_mastercard_tx_date": "2026-09-24"
  }
  ```
- **Action:** Updates the singleton `ChecklistConfig` and returns `ChecklistConfigResponse`.

### 5.3 `GET /api/checklist/wave-accounts/{company_id}`
- **Action:** Queries `WaveClient.get_business_accounts(company.wave_api_token, company.wave_business_id)` for the selected company and returns all active Wave accounts grouped for the Checklist Settings dropdowns:
  - `bank_and_cc_accounts`: Accounts with `type in ("ASSET", "LIABILITY")` and `subtype in ("CASH_AND_BANK", "CREDIT_CARD", "MONEY_MARKET", "LOANS_AND_LINE_OF_CREDIT")`.
  - `expense_accounts`: Accounts with `type == "EXPENSE"`.
  - `liability_accounts`: Accounts with `type == "LIABILITY"`.

### 5.4 `GET /api/checklist/months/{year_month}`
- **Path Parameter:** `year_month` matching `^\d{4}-(0[1-9]|1[0-2])$`.
- **Action:** Retrieves (or initializes via carry-forward logic) the `MonthlyChecklist` for `year_month`.
- **Response (`200 OK`):**
  ```json
  {
    "id": "uuid",
    "year_month": "2026-09",
    "completed_steps": ["import_chequing", "import_mastercard"],
    "net_operating_cash": "4200.00",
    "tax_rate": "12.00",
    "tax_reserve_amount": "504.00",
    "tax_accrual_wave_tx_id": "VHJhbnNhY3Rpb246MTIz",
    "prior_soft_cap": "17600.00",
    "monthly_loc_reduction": "400.00",
    "current_soft_cap": "17200.00",
    "tax_liability": "1504.00",
    "actual_loc_balance": "11200.00",
    "maximum_safe_draw": "4496.00",
    "wave_cash_flow_url": "https://next.waveapps.com/d2977f10-6793-4504-a139-f0d6872b2628/reports/cash-flow?end=2026-09-30&start=2026-09-01"
  }
  ```

### 5.5 `PATCH /api/checklist/months/{year_month}`
- **Request Body (All fields optional):**
  ```json
  {
    "completed_steps": ["import_chequing"],
    "net_operating_cash": "4200.00",
    "tax_rate": "12.00",
    "prior_soft_cap": "17600.00",
    "monthly_loc_reduction": "400.00",
    "tax_liability": "1504.00",
    "actual_loc_balance": "11200.00"
  }
  ```
- **Action:** Updates the specified fields on the `MonthlyChecklist` for `year_month` and returns the updated `MonthlyChecklistResponse` with recomputed derived fields (`tax_reserve_amount`, `current_soft_cap`, `maximum_safe_draw`).

### 5.6 `POST /api/checklist/months/{year_month}/sync-rbc-csv`
- **Request Format:** `multipart/form-data`
  - `account_type`: `"chequing"` or `"mastercard"` (Form field)
  - `file`: Uploaded RBC `.csv` file
- **Pre-Flight Validation:**
  - Verify `ChecklistConfig` has a valid Wave-connected `company_id`.
  - If `account_type == "chequing"`, verify `chequing_wave_account_id` is configured (`400 Bad Request` otherwise).
  - If `account_type == "mastercard"`, verify `mastercard_wave_account_id` is configured (`400 Bad Request` otherwise).
  - Parse CSV and validate `Account Type` column matches `account_type` (`"Chequing"` vs `"MasterCard"`).
- **Execution:**
  - For each parsed row (ordered chronologically by date):
    1. Apply description merging and Mastercard sign reversal (Section 3.2).
    2. Resolve category via hardcoded rules or fallback to `UNCATEGORIZED_EXPENSE` / `UNCATEGORIZED_INCOME` (Section 3.3).
    3. Call `WaveClient.create_money_transaction` (or `create_bank_statement_transaction`) with `externalId = f"wrangler_rbc_{account_type}_{row_date}_{row_index}_{abs(amount)}"`.
  - Update `last_chequing_tx_date` or `last_mastercard_tx_date` to the maximum transaction date among successfully synced rows.
  - Mark `"import_chequing"` or `"import_mastercard"` as completed in `MonthlyChecklist.completed_steps`.
- **Response (`200 OK`):**
  ```json
  {
    "total_rows": 14,
    "synced_count": 14,
    "failed_count": 0,
    "auto_categorized_count": 5,
    "uncategorized_count": 9,
    "latest_transaction_date": "2026-09-28",
    "errors": []
  }
  ```

### 5.7 `POST /api/checklist/months/{year_month}/sync-tax-accrual`
- **Request Body (Optional overrides if not yet saved via PATCH):**
  ```json
  {
    "net_operating_cash": "4200.00",
    "tax_rate": "12.00"
  }
  ```
- **Pre-Flight Validation:**
  - Verify `ChecklistConfig` has `company_id`, `tax_expense_wave_account_id`, and `tax_payable_wave_account_id` configured (`400 Bad Request` otherwise).
  - Compute `tax_reserve_amount`. If `tax_reserve_amount is None` or `tax_reserve_amount <= 0`, return `400 Bad Request` (`"Tax reserve amount must be greater than $0.00 to post a journal entry"`).
- **Execution:**
  - Compute the last calendar day of `year_month` (e.g., `2026-09-30` for `"2026-09"` using `calendar.monthrange(year, month)[1]`).
  - Call `WaveClient.create_money_transaction`:
    - `business_id`: `company.wave_business_id`
    - `external_id`: `f"wrangler_tax_accrual_{company.id}_{year_month}"`
    - `date`: `f"{year_month}-{last_day:02d}"`
    - `description`: `f"Corporate Tax Accrual ({year_month})"`
    - `amount`: `tax_reserve_amount` (positive -> `anchor.direction = "WITHDRAWAL"` on `tax_payable_wave_account_id` [Credit Liability]; `lineItems[0].balance = "INCREASE"` on `tax_expense_wave_account_id` [Debit Expense]).
  - Save `tax_accrual_wave_tx_id = wave_tx_id` on `MonthlyChecklist` and add `"calculate_net_cash_and_tax"` to `completed_steps`.
- **Response (`200 OK`):** Updated `MonthlyChecklistResponse`.

---

## 6. Frontend UI & Pinia Architecture (`web/src/`)

### 6.1 Navigation Drawer (`web/src/layouts/nav.ts` & `web/src/router/index.ts`)
Add **Checklist** to `navItems` in [`web/src/layouts/nav.ts`](file:///D:/src/personal/wrangler/web/src/layouts/nav.ts):
```typescript
{ name: "checklist", label: "Checklist", icon: "fact_check", path: "/checklist" }
```
Register route `/checklist` -> `ChecklistView.vue` in `web/src/router/index.ts`.

### 6.2 Pinia Store (`web/src/stores/checklist.ts`)
Create `useChecklistStore` managing:
- `config: ChecklistConfig | null`
- `currentMonth: MonthlyChecklist | null`
- `selectedYearMonth: string` (Initialized to the **previous calendar month** in `YYYY-MM` format, e.g., when today is `2026-10-26`, defaults to `"2026-09"`).
- Actions:
  - `fetchConfig()`
  - `updateConfig(payload)`
  - `fetchWaveAccountsForCompany(companyId)`
  - `fetchMonth(yearMonth)`
  - `updateMonth(yearMonth, payload)`
  - `toggleStep(stepKey, completed)`
  - `syncRbcCsv(yearMonth, accountType, file)`
  - `syncTaxAccrual(yearMonth, netOperatingCash, taxRate)`

### 6.3 Checklist View (`web/src/views/ChecklistView.vue`)

#### 6.3.1 Top Header Bar
- **Title:** `"Monthly Bookkeeping Checklist — Michelle Dryden LTD"`
- **Month Picker Control:**
  - Previous Month (`<`) icon button, `YYYY-MM` month selector (`type="month"` or month/year picker), and Next Month (`>`) icon button.
- **Progress Indicator:**
  - `QLinearProgress` bar and badge showing `"{completedCount} / 9 Completed"`.
- **Checklist Settings Button:**
  - Gear icon button (`icon="settings"`, `label="Configure Accounts"`) that opens `ChecklistSettingsDialog.vue` (always visible in accordance with UI spatial stability standards).

#### 6.3.2 Checklist Step Cards (Steps 1–9)
Rendered as a vertical list of clean Quasar cards (`q-card flat bordered`). Each card has:
- Left: `QCheckbox` bound to whether `step.key` is in `currentMonth.completed_steps`.
- Main Content:
  - **Step Title** (`text-subtitle1 text-weight-bold`, struck through or muted when checked).
  - **Reminder Description** (`text-body2 text-grey-7`).
  - **Step-Specific Action Area:**
    - **Step 1 (`import_chequing`) & Step 2 (`import_mastercard`):**
      - Info chip displaying **Last Synced Transaction Date:** `YYYY-MM-DD` (or `"Not yet synced"`).
      - Inline `QFile` input (`accept=".csv"`, dense, outlined, label `"Select RBC Chequing CSV"` / `"Select RBC Mastercard CSV"`) + **"Sync to Wave"** `QBtn` (permanently visible, `:disable="!selectedFile || !isAccountConfigured || syncing"`).
      - Inline sync result summary banner showing rows synced and auto-categorized count.
    - **Step 5 (`sync_external_data`):**
      - Bullet reminder: *"Use Amazon Order History Reporter to export Transactions for past 2 months (since Wrangler detects duplicates and Amazon does weird things with transactions, going back further ensures you get everything)."*
      - Action buttons:
        1. **"Open Amazon Order History"** (`href="https://www.amazon.ca/gp/css/order-history?ref_=nav_orders_first"`, `target="_blank"`, icon `open_in_new`).
        2. **"Go to Wrangler Import"** (`to="/import"`, icon `cloud_upload`).
        3. **"Go to Export Manager"** (`to="/export-manager"`, icon `sync`).
    - **Step 8 (`calculate_net_cash_and_tax`):**
      - Button: **"Open Wave Cash Flow Report ({selectedYearMonth})"** opening `currentMonth.wave_cash_flow_url` in a new tab (`target="_blank"`).
      - Row of inputs:
        - **Net Cash from Operating Activities ($):** `QInput` (`type="number"`, `step="0.01"`, prefix `"$"`, saves on blur/change).
        - **Tax Rate (%):** `QInput` (`type="number"`, `step="0.1"`, suffix `"%"`, default `12.00`).
        - **Calculated Tax Reserve:** Read-only formatted display chip/box (`$504.00`).
        - **"Sync Tax Accrual to Wave" Button:** Permanently visible `QBtn`, `:disable="!canSyncTaxAccrual || Boolean(currentMonth.tax_accrual_wave_tx_id)"`. Shows a green `"Synced to Wave"` badge when `tax_accrual_wave_tx_id` is present.
    - **Step 9 (`execute_dividends`):**
      - Button: **"Open Wave Balance Sheet ({selectedYearMonth})"** opening `https://next.waveapps.com/${config.wave_web_business_slug}/reports/balance-sheet` in a new tab (`target="_blank"`) to quickly inspect the updated `Taxes Payable` liability and `LOC` balance.
      - Interactive **Maximum Safe Draw Calculator** grid:
        - **Prior Soft Cap ($):** `QInput` (`type="number"`, `step="100"`, prefix `"$"`, defaulted from previous month's ending Soft Cap, with `2026-09` ending at `$17,200.00` so `2026-10` starts with Prior Soft Cap `$17,200.00`).
        - **Monthly LOC Reduction ("Payment") ($):** `QInput` (`type="number"`, `step="50"`, prefix `"$"`, defaulted from previous month / `$400.00`).
        - **Current Soft Cap ($):** Read-only calculated field (`Prior Soft Cap - Monthly LOC Reduction`, e.g., `$17,200.00` for `2026-09`, `$16,800.00` for `2026-10`).
        - **Tax Liability ($):** `QInput` (`type="number"`, `step="0.01"`, prefix `"$"`).
        - **Actual LOC Balance ($):** `QInput` (`type="number"`, `step="0.01"`, prefix `"$"`).
        - **Maximum Safe Draw ($):** Highlighted summary box displaying `Current Soft Cap - Tax Liability - Actual LOC Balance` (styled in green when positive, red/warning if `<= 0`).
      - *(No Wave sync button is needed on Step 9, as the physical e-transfer draw is imported automatically via next month's Chequing CSV).*

### 6.4 Checklist Settings Dialog (`web/src/components/ChecklistSettingsDialog.vue`)
Allows configuring:
1. **Target Company:** `QSelect` of companies (e.g. *Michelle Dryden LTD*). Selecting a Wave-connected company automatically fetches its Wave accounts via `GET /api/checklist/wave-accounts/{company_id}`.
2. **Step 1 — Wave Chequing Account:** `QSelect` populated with `bank_and_cc_accounts`.
3. **Step 2 — Wave Mastercard Account:** `QSelect` populated with `bank_and_cc_accounts`.
4. **Step 8 — Corporate Tax Expense Account:** `QSelect` populated with `expense_accounts` (e.g., *Taxes - Corporate Tax*).
5. **Step 8 — Taxes Payable Liability Account:** `QSelect` populated with `liability_accounts` (e.g., *Taxes Payable*).
6. **Last Synced Dates (Optional Manual Override):** Date inputs for `last_chequing_tx_date` and `last_mastercard_tx_date` in case the user ever wants to manually seed or adjust the cutoff dates.

---

## 7. Verification Scenarios & Test Plan

### 7.1 Backend Tests (`api/tests/test_checklist.py`)
1. **RBC Chequing CSV Transformation & Sync:**
   - Upload sample [`shellco-chq.csv`](file:///C:/Users/mjdry/Downloads/shellco-chq.csv) to `POST /api/checklist/months/2026-09/sync-rbc-csv` with `account_type="chequing"`.
   - Verify `Description 1` and `Description 2` are joined (`"Other loan - Loan interest"`, `"e-Transfer sent - Dryden - Personal"`) and excess spaces collapsed (`"Mobile cheque deposit - 5318"`).
   - Verify `"Monthly fee"` and `"Activity fee"` resolve to the `"Bank Service Charges"` Wave account ID, and `"Other loan - Loan interest"` resolves to `"Interest Expense"`.
   - Verify `"LOAN CREDIT"`, `"LOAN PAYMENT"`, and `"Mobile cheque deposit - 5318"` remain uncategorized (`UNCATEGORIZED_INCOME` for positive deposits, `UNCATEGORIZED_EXPENSE` for negative withdrawals).
   - Verify `last_chequing_tx_date` updates to `2026-10-21` and `"import_chequing"` is marked complete.
2. **RBC Mastercard CSV Sign Reversal & Auto-Categorization:**
   - Upload sample [`shellco-mc.csv`](file:///C:/Users/mjdry/Downloads/shellco-mc.csv) with `account_type="mastercard"`.
   - Verify positive charges (`12.32`, `818.85`) are negated (`-12.32`, `-818.85`) and sent as `WITHDRAWAL` on the Mastercard anchor account.
   - Verify negative payment (`-1023.41` for `PAYMENT - THANK YOU / PAI EMENT - MERCI`) is negated to `+1023.41` and sent as `DEPOSIT` on the Mastercard anchor account.
   - Verify `"WAVE PRO TORONTO"` resolves to `"Accounting Fees"` and `"PURCHASE INTEREST 19.99%"` resolves to `"Interest Expense"`.
   - Verify uploading a Chequing CSV to the Mastercard step (or vice versa) returns `400 Bad Request`.
3. **Corporate Tax Accrual Sync (Step 8):**
   - Patch `net_operating_cash = 5000.00`, `tax_rate = 12.00` for `"2026-09"`.
   - Verify `tax_reserve_amount == Decimal("600.00")` and `wave_cash_flow_url` contains `start=2026-09-01` and `end=2026-09-30`.
   - Call `POST /api/checklist/months/2026-09/sync-tax-accrual`. Verify `WaveClient.create_money_transaction` is invoked with `date="2026-09-30"`, `anchor_account_id=tax_payable_wave_account_id` (`WITHDRAWAL`), and `category_account_id=tax_expense_wave_account_id` (`INCREASE`).
4. **Month-to-Month Soft Cap Carry-Forward & Safe Draw Math (Step 9):**
   - For `"2026-09"`: `prior_soft_cap = 17600.00`, `monthly_loc_reduction = 400.00` -> `current_soft_cap == 17200.00`.
   - Set `tax_liability = 1200.00`, `actual_loc_balance = 10500.00` -> `maximum_safe_draw == 5500.00`.
   - Request `GET /api/checklist/months/2026-10` -> verify it auto-initializes with `prior_soft_cap == 17200.00`, `monthly_loc_reduction == 400.00`, and `current_soft_cap == 16800.00`.

### 7.2 Frontend Tests (`web/tests/checklist.test.ts`)
1. Verify `ChecklistView.vue` defaults to the previous calendar month (`YYYY-MM`) and renders all 9 steps with persistent action controls.
2. Verify Step 8 dynamically updates the Calculated Tax Reserve and Wave Cash Flow link when switching months or editing Net Operating Cash.
3. Verify Step 9 dynamically updates Current Soft Cap and Maximum Safe Draw as inputs change.
