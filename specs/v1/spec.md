# Family Accounting App - Technical Specification

## 1. Project Overview
This application is a private, internal web tool used to review, allocate, and process financial transactions from various intake sources. Transactions can be split and assigned to either personal/home expenses or specific business entities. Approved business transactions are exported to a CSV format compatible with Wave (waveapps.com) for manual upload, featuring batch tracking, status reconciliation, and receipt file correlation.

~~Approved business transactions are subsequently synced to Wave (waveapps.com) via their API.~~ *(Superseded: Wave GraphQL API requires a paid tier. Pivoted to manual CSV export).*

### 1.1 Target Audience & Access
- The application is for internal family use only.
- It will not be exposed publicly to the internet.
- Access requires a single-user login mechanism.

## 2. Technical Stack
- **Frontend:** Vue 3.5.x, Vue Router, Quasar 2.30.x, Pinia 3.x, Fetch API
- **Backend:** Python 3.14.x, FastAPI, Uvicorn, Pydantic, Alembic
- **Database:** SQLite
- ~~**Wave API:** Wave GraphQL API~~ *(Superseded: Pivoted to CSV export).*
- **Accounting Export:** CSV formatted for manual Wave transaction import (`Date`, `Description`, `Amount`).

### 2.1 Tooling
- `uv` for managing Python and dependencies, along with formatting and linting
- `nvm` for managing Node.js and dependencies
- `prettier` for formatting and linting the frontend
- `pnpm` for frontend package management

## 3. Security & Authentication
- **Admin Credentials:** A single username and password must be configured via environment variables (e.g., `ADMIN_USERNAME`, `ADMIN_PASSWORD`).
- **Session Management:** The frontend will authenticate via a login screen, receiving a JWT (JSON Web Token) from the FastAPI backend.
- **Global Configuration:** The application requires the following environment variables:
  - `JWT_SECRET_KEY` and `JWT_ACCESS_TOKEN_EXPIRE_MINUTES` for session management.
  - ~~`WAVE_CLIENT_ID`, `WAVE_CLIENT_SECRET`, and `WAVE_REDIRECT_URI` for OAuth.~~ *(Superseded: OAuth flow dropped in favor of CSV export).*
  - `RECEIPT_STORAGE_DIR`: Absolute path for durable on-disk receipt storage.
- ~~**Wave API Credentials & Scopes:** Wave API tokens must be configurable *per company* and stored in the database. The OAuth flow must request the following scopes: `business:read`, `account:read`, `transaction:write`. To identify the company during the OAuth callback, the `company_id` must be passed as a signed JWT within the OAuth `state` parameter.~~ *(Superseded).*

## 4. Data Model
The database will be SQLite. The implementation agent should use an ORM (like SQLAlchemy or SQLModel).

### 4.1 Company
Represents a business entity.
- `id`: UUID / Primary Key
- `name`: String (Unique business name)
- ~~`wave_business_id`: String~~ *(Superseded)*
- ~~`wave_access_token`: String~~ *(Superseded)*
- ~~`wave_refresh_token`: String~~ *(Superseded)*
- ~~`wave_token_expires_at`: DateTime~~ *(Superseded)*
- ~~`wave_equity_account_id`: String (**REQUIRED** for Wave's double-entry accounting. This represents the offset/anchor account like 'Bank' or 'Owner's Equity' used to balance expenses).~~ *(Superseded)*

### 4.2 WaveCategory (Cached) — [SUPERSEDED]
> [!NOTE]
> **Superseded:** Category tracking and Wave account caching have been removed because Wave's free CSV transaction import does not support category assignments during import.
- ~~`id`: UUID~~
- ~~`company_id`: Foreign Key to Company~~
- ~~`wave_account_id`: String~~
- ~~`name`: String~~
- ~~*Note:* Fetching should filter only for applicable Expense/Asset/Income accounts to prevent users from allocating to invalid system accounts.~~

### 4.3 Transaction
Represents the top-level transaction imported from an intake source or manually entered.
- `id`: UUID / Primary Key
- `source`: String (e.g., "manual", "amazon")
- `external_id`: String (Nullable. Unique identifier from the source system. A Database Unique Constraint must be placed on `(source, external_id)` to prevent duplicate imports).
- `date`: Date
- `description`: String
- `total_amount`: Decimal / Float (Can be negative to support refunds/income).
- `currency_code`: String (Defaults to base currency, e.g., "USD").
- `receipt_file_path`: String (Nullable. Relative path to stored receipt file on disk).
- ~~`is_approved`: Boolean (Indicates ready for allocation/export).~~ *(Removed).*

### 4.4 Allocation (Splits)
A transaction must be able to be split across personal expenses or business entities.
- `id`: UUID / Primary Key
- `transaction_id`: Foreign Key to `Transaction` (CASCADE on delete)
- `amount`: Decimal / Float
- `is_personal`: Boolean (True if personal expense; False if allocated to a business)
- `company_id`: Foreign Key to `Company` (Nullable; required if `is_personal` is False)
- ~~`wave_category_id`: Foreign Key to WaveCategory (Nullable)~~ *(Superseded)*
- `sync_status`: Enum (`PENDING`, `SYNCED` ~~, `FAILED`, `IGNORED`~~)
- ~~`wave_transaction_id`: String (Nullable)~~ *(Superseded)*

## 5. Backend Architecture (FastAPI)

### 5.1 Endpoints
- **Health Check:** `GET /api/health` (Unauthenticated, public probe for uptime/container monitoring).
  - Executes a lightweight `SELECT 1` query using the SQLAlchemy database session.
  - **Success (`200 OK`):**
    ```json
    {
      "status": "ok",
      "database": "healthy",
      "meta": {
        "database_path": "wrangler.db"
      }
    }
    ```
  - **Failure (`503 Service Unavailable`):** Triggered if SQLite is unreachable, locked, or query execution raises an exception:
    ```json
    {
      "status": "unhealthy",
      "database": "unhealthy",
      "meta": {
        "database_path": "wrangler.db",
        "error": "<error message>"
      }
    }
    ```
- **Auth:** `POST /api/login` (Returns JWT token)
- **Companies:**
  - `GET /api/companies` (List all companies)
  - `POST /api/companies` (Create company)
  - `PUT /api/companies/{id}` (Update company)
  - `DELETE /api/companies/{id}` (Delete company; restricted if linked to existing allocations)
- ~~**Wave OAuth:**~~ *(Superseded)*
  - ~~`GET /api/wave/oauth/authorize?company_id={id}`~~
  - ~~`GET /api/wave/oauth/callback`~~
- ~~**Wave Sync:**~~ *(Superseded)*
  - ~~`POST /api/companies/{id}/sync-categories`~~
- **Transactions:** 
  - `GET /api/transactions` (Must implement **server-side pagination**, filtering by source, company, and date range. ~~Approval filter~~ is superseded).
  - `POST /api/transactions` (Manual transaction creation with optional receipt file upload and initial split allocations):
    - **Payload:** Accepts `multipart/form-data` (when receipt file is uploaded) or `application/json`.
    - **Validation:**
      - `total_amount`: Numeric, strictly non-zero (supports positive for expenses, negative for returns/refunds).
      - `date`: Required valid ISO date string (`YYYY-MM-DD`).
      - `description`: Required, non-empty string.
      - `company_id`: Required UUID for manual business transaction attribution.
      - ~~`is_approved`: Boolean~~ *(Superseded).*
      - `allocations`: Optional list of splits. If provided, sum of `allocation.amount` must equal `total_amount`.
    - **Atomic Creation:** In a single database transaction:
      1. Creates the `Transaction` record with `source = "manual"`.
      2. If receipt is uploaded, saves to `RECEIPT_STORAGE_DIR` and populates `receipt_file_path`.
      3. Creates `Allocation` record(s): If splits are omitted in the request, automatically creates a single default business allocation (`amount = total_amount`, `company_id = payload.company_id`, `is_personal = false`, `sync_status = PENDING`).
    - **Response:** `201 Created` with created `TransactionResponse` including its allocations.
  - `PUT /api/transactions/{id}` (Update transaction details).
  - ~~`PUT /api/transactions/{id}/approve` (Mark transaction as approved).~~ *(Superseded: Approval endpoint removed).*
- **Allocations:**
  - `PUT /api/transactions/{id}/allocations` (Updates split allocations. **MUST** return a 400 error if any existing allocation is `SYNCED`).
  - `PUT /api/allocations/{id}/revert` (Reverts a single `SYNCED` allocation back to `PENDING`).
- **Receipts:**
  - `POST /api/transactions/{id}/receipt` (Uploads receipt file to `RECEIPT_STORAGE_DIR`).
  - `GET /api/receipts/{path}` (Downloads receipt file for user inspection and manual upload into Wave).
- ~~**Wave Push:**~~ *(Superseded)*
  - ~~`POST /api/sync/wave` (Must spawn a background task to process PENDING transactions to avoid 504 timeouts. Returns 202 Accepted).~~
- **Export & Sync Management:**
  - `GET /api/companies/{id}/export-transactions` (Generates and downloads a CSV of business allocations. Query param `status`: defaults to `PENDING`, optional `SYNCED`).
  - `POST /api/companies/{id}/mark-synced` (Marks business allocations for this company as `SYNCED`. Accepts optional list of allocation IDs in payload; if omitted, marks all currently `PENDING` allocations for the company).
  - `POST /api/companies/{id}/revert-synced` (Reverts business allocations for this company back to `PENDING`. Accepts optional list of allocation IDs in payload; if omitted, reverts all `SYNCED` allocations).

### 5.2 Abstraction Layer for Intake Sources
The backend must include an abstraction layer for parsing transaction sources, enforcing the extraction of `external_id` for duplicate prevention.

## 6. Frontend UI Requirements (Vue 3 + Quasar)

### 6.1 Layout
Persistent navigation drawer: **Ledger**, **Manual Entry**, **Export Manager** (replacing ~~Sync Manager~~), and **Settings**.

### 6.2 Ledger View
- **Data Table:** Displays top-level `Transactions` using server-side pagination.
- **Sync Status & Immutability:** Transactions with `SYNCED` allocations must be visually indicated with a badge and locked from allocation editing. Locked transactions can be unlocked by reverting their synced allocations to `PENDING`.
- **Receipt Downloads:** Direct download button/link for transactions with attached receipts so the user can easily download files when preparing manual Wave uploads.

### 6.3 Manual Entry View
A dedicated form accessible via the persistent navigation drawer (`/manual-entry`) optimized for rapid, keyboard-driven manual business expense intake.

- **Scope & Constraints:**
  - Exclusively for business expenses; personal expenses are never manually entered here.
  - Every manual entry must be attributed to a business entity (`Company`).
- **Form Controls & Required Fields:**
  - **Date:** Required input starting empty (no default date). Utilizes a Quasar datepicker (`q-date` / `q-popup-proxy`) configured with `today-btn=true` for one-click selection of the current date.
  - **Description / Payee:** Required text input (e.g., vendor, supplier, or invoice memo).
  - **Total Amount:** Required numeric input formatted to two decimal places. Must be strictly non-zero (negative amounts denote returns/refunds).
  - **Company:** Required select dropdown populated from active `Company` records.
  - **Receipt Attachment:** Optional file dropzone/picker accepting PDF, PNG, and JPEG.
  - ~~**Approval Toggle:** Optional toggle (`is_approved`), defaults to `true`.~~ *(Superseded).*
- **Inline Allocation Splitter (All-in-One):**
  - Allows completing the ledger allocation directly within the entry form.
  - Defaults to a single split assigning 100% of `Total Amount` to the selected `Company` (`is_personal = false`, `sync_status = PENDING`).
  - Supports adding additional splits across different businesses for multi-company receipts.
  - Enforces that all allocations are business splits (`is_personal = false` with a selected `company_id`).
  - Real-time balance validation: Unallocated remainder (`Total Amount - sum(splits)`) must be `0.00`. Form submission is disabled while unbalanced.
- **Keyboard Navigation & Rapid Continuous Entry:**
  - **Global Shortcut:** Pressing `Ctrl + Enter` from anywhere within the form immediately submits the entry.
  - **Post-Submission Reset:** Upon successful creation (`201 Created`):
    1. Displays a success toast notification.
    2. Completely resets the form: Clears the date field (returns to empty), clears description, clears amount, clears receipt, and restores a single 100% default allocation to the selected company.
    3. **Auto-focuses the first field (Date)** so the user can immediately type the next receipt without touching the mouse.

### 6.4 Allocation Editor (Transaction Splitter)
- Modal or expandable panel allowing user to split a parent transaction into `Allocations`.
- Controls:
  - Personal toggle (`is_personal`).
  - Business Company select dropdown (disabled if `is_personal` is True).
  - ~~Category select~~ *(Superseded: Categories removed).*
  - Amount input per split, with validation ensuring sum of allocations equals `Transaction.total_amount`.
- Editing is locked if any allocation has `sync_status == SYNCED`.

### 6.5 Export Manager UI (Supersedes Sync Manager UI)
Dedicated view replacing the legacy automated Sync Manager:
- **Pending Exports Summary:** Table or card list grouped by `Company`, showing:
  - Company Name
  - Count of `PENDING` allocations
  - Total dollar amount of pending allocations
- **Actions per Company:**
  - **"Export CSV" button:** Triggers CSV file download formatted for Wave import.
  - **"Mark as Synced" button:** Becomes primary action after export, allowing the user to mark the exported allocations as `SYNCED`.
- **Reconciliation & History Section:**
  - Tab or expandable view showing `SYNCED` allocations per company.
  - **"Revert to Pending" button:** Allows reverting allocations back to `PENDING` if an import into Wave was aborted, rejected, or needs correction.

~~**Legacy Sync Manager UI (Superseded):**~~
- ~~Dedicated view for Wave synchronization.~~
- ~~Displays `PENDING` and `FAILED` business allocations.~~
- ~~Actions: "Sync to Wave" and "Retry Failed".~~
- ~~UI should poll the backend to display background sync progress.~~

### 6.6 Company Management & Settings UI
- CRUD interface for `Company` records (add, rename, delete businesses).
- Displays total allocated transaction count per company.
- ~~Configures `wave_equity_account_id` per company.~~ *(Superseded)*
- ~~Connect to Wave (OAuth flow) button and token status indicator.~~ *(Superseded)*

## 7. Export & Integration Details

### 7.1 CSV Export & Reconciliation Details (Active)

#### 7.1.1 Wave CSV Format Specification
Wave's transaction import accepts standard 3-column CSV files. The exported CSV must conform to RFC 4180:
- **Columns & Header:** `Date,Description,Amount`
- **Field Formatting:**
  - `Date`: ISO 8601 formatted date string (`YYYY-MM-DD`). Derived from parent `Transaction.date`.
  - `Description`: Text string escaping commas and quotes properly. Derived from parent `Transaction.description`.
  - `Amount`: Numeric string with two decimal places (e.g., `12.50`). Refunds and negative transactions are represented with a leading negative sign (e.g., `-50.00`). Derived from `Allocation.amount`.
- **Row Mapping:**
  - Each business `Allocation` (`is_personal == False`) linked to the requested `company_id` produces exactly one row in the CSV.
  - Personal allocations are excluded from company CSV exports.

#### 7.1.2 Sync State Lifecycle & Rules
- **States:** `PENDING` and `SYNCED`.
- **Creation:** All new business allocations default to `PENDING`.
- **Marking as Synced:** Completed manually by the user via the Export Manager after generating the CSV and importing it into Wave.
- **Reversion:** Users can revert `SYNCED` allocations back to `PENDING`. This unlocks the parent transaction for editing or reallocation if an error occurred during Wave import.
- **Transaction Safety:** Allocation modifications (`PUT /api/transactions/{id}/allocations`) remain strictly prohibited while any allocation in the transaction is `SYNCED`.

### 7.2 Wave GraphQL API Integration Details (Superseded)
> [!NOTE]
> **Superseded (2026-09-06):** The automated Wave GraphQL integration has been retired because Wave requires a paid subscription tier for API access. The active design uses manual CSV export (Section 7.1). Historical integration specifications are preserved below for reference.

- ~~**Double-Entry Requirement:** Wave requires an offset account. The system will use the `Company.wave_equity_account_id` as the anchor account for all synced transactions.~~
- ~~**Transaction Grouping:** Multiple allocations for the *same* company from a single parent `Transaction` must be grouped into a **single Wave transaction with multiple line items**.~~
- ~~**Cross-Company Receipts:** If a receipt is attached to a parent transaction split across *two different* companies, the receipt must be uploaded separately to *each* company's Wave workspace.~~
- ~~**Immutability & Refunds:** Synced transactions are read-only. Negative amounts represent refunds and must flip debits/credits in the Wave GraphQL mutation.~~

#### ~~7.2.1 Legacy Implementation Steps for Wave API (Superseded)~~
1. ~~Identify the Wave `businessId` and `wave_equity_account_id` from the `Company` record.~~
2. ~~Verify token validity (`wave_token_expires_at`). If expired, use `wave_refresh_token` to get new tokens before proceeding.~~
3. ~~Authenticate using the valid `wave_access_token`.~~
4. ~~**Receipts (Multipart Note):** Wave's GraphQL API requires the Apollo GraphQL multipart request specification for file uploads. The developer must use `httpx` with `multipart/form-data` for the `documentCreate` mutation.~~
5. ~~Execute transaction mutation using `wave_category_id` (line item) and `wave_equity_account_id` (anchor account).~~
6. ~~Wrap the local DB updates (`sync_status = SYNCED` and `wave_transaction_id`) in a local database transaction to prevent orphan states if the local commit fails.~~
