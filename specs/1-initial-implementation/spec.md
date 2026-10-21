# Family Accounting App - Technical Specification

**Status:** Implemented

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
- `currency_code`: String (Defaults to base currency, e.g., "CAD").
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
- ~~`sync_status`: Enum (`PENDING`, `SYNCED`, `FAILED`, `IGNORED`)~~ *(Superseded: Replaced with `is_locked` boolean)*
- `is_locked`: Boolean (Defaults to `False`. Set to `True` automatically when exported via CSV or manually locked by the user).
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
      - `company_id`: Required UUID for manual business transaction attribution (when default allocation is used).
      - ~~`is_approved`: Boolean~~ *(Superseded).*
      - `allocations`: Required/optional list of splits. Sum of `allocation.amount` must equal `total_amount`.
    - **Atomic Creation:** In a single database transaction:
      1. Creates the `Transaction` record with `source = "manual"`.
      2. If receipt is uploaded, saves to `RECEIPT_STORAGE_DIR` and populates `receipt_file_path`.
      3. Creates `Allocation` record(s): If splits are omitted in the request, automatically creates a single default business allocation (`amount = total_amount`, `company_id = payload.company_id`, `is_personal = false`, `is_locked = false`).
    - **Response:** `201 Created` with created `TransactionResponse` including its allocations.
  - `PUT /api/transactions/{id}` (Unified update for transaction details, split allocations, and optional receipt replacement/removal):
    - **Payload:** Accepts `application/json` or `multipart/form-data` (for inline receipt file upload or removal via `remove_receipt: bool`).
    - **Lock Validation & Partial Lock Rules:**
      - A parent transaction is considered **Fully Locked** only when **all** of its existing allocations have `is_locked == True` (`len(allocations) > 0 and all(a.is_locked for a in allocations)`). If Fully Locked, modifying transaction metadata or allocations (`date`, `description`, `total_amount`, `allocations`) **MUST** return `400 Bad Request` (`"Cannot modify transaction: all allocations are locked"`).
      - If the transaction is **Partially Locked** (some allocations have `is_locked == True` and some have `is_locked == False`), the parent transaction remains unlocked so the user can edit or split the unlocked allocations without unlocking the already-exported ones. However:
        1. Every existing locked allocation (`is_locked == True`) **MUST** be preserved in the `allocations` payload with its original `id`, `amount`, `is_personal`, `company_id`, and `is_locked = True` untouched; attempting to modify or remove a locked allocation without unlocking it first returns `400 Bad Request`.
        2. Top-level `date` and `description` cannot be changed while any allocation is locked (`400 Bad Request`), or if `total_amount` is changed, the sum of all allocations (locked + unlocked) must equal the new `total_amount`.
      - **Personal vs. Business Split Validation:**
        - Only business transactions (`is_personal == False`) can be split into multiple allocations (`len(allocations) > 1`).
        - If `len(allocations) > 1`, any allocation with `is_personal == True` is rejected with `400 Bad Request` (`"Only business transactions can be split. Remove extra splits before marking as personal."`).
        - If `len(allocations) == 1` and `is_personal == True`, `company_id` is set to `None`.
        - For any allocation with `is_personal == False`, a valid existing `company_id` is required.
        - When `allocations` is provided (or when `total_amount` is updated), `sum(allocation.amount)` must strictly equal `Transaction.total_amount` (`400 Bad Request` if unbalanced).
    - **Receipt Handling in Edit:**
      - Receipt updates (`file` upload or `remove_receipt = True`) are permitted regardless of whether the transaction's allocations are locked.
      - Replacing or removing an existing receipt deletes the old file from `RECEIPT_STORAGE_DIR` on disk.
  - `DELETE /api/transactions/{id}` (Deletes a transaction, its allocations, and its on-disk receipt file):
    - **Lock Validation:** **MUST** return `400 Bad Request` if **any** allocation on the transaction has `is_locked == True` (`"Cannot delete transaction: transaction contains locked allocations"`). The user must unlock all locked allocations before deleting the transaction.
    - **File Cleanup:** If `transaction.receipt_file_path` is present, deletes the physical file from `RECEIPT_STORAGE_DIR` (ignoring `FileNotFoundError` if already absent) upon database commit.
    - **Response:** `204 No Content`.
  - `PUT /api/transactions/{id}/lock` (Intentional transaction-level lock/unlock):
    - **Payload:** `{ "is_locked": bool }`
    - Sets `is_locked = payload.is_locked` on all allocations belonging to `transaction_id` and returns the updated `TransactionResponse`.
  - ~~`PUT /api/transactions/{id}/approve` (Mark transaction as approved).~~ *(Superseded: Approval endpoint removed).*
- **Allocations:**
  - `PUT /api/transactions/{id}/allocations` (Updates split allocations):
    - Enforces the same partial/full lock rules and personal/business split validation as `PUT /api/transactions/{id}`: returns `400 Bad Request` if all allocations are locked or if any existing locked allocation is modified/removed, and validates that `sum(amount) == transaction.total_amount`.
  - `PUT /api/allocations/{id}/lock` (Replaces ~~`PUT /api/allocations/{id}/revert`~~):
    - **Payload:** `{ "is_locked": bool }`
    - Locks or unlocks a single allocation (`Allocation.is_locked = payload.is_locked`) and returns `AllocationResponse`.
- **Receipts:**
  - `POST /api/transactions/{id}/receipt` (Uploads or replaces a receipt file in `RECEIPT_STORAGE_DIR`):
    - Permitted even when the transaction's allocations are locked (`is_locked == True`).
    - If the transaction already had a `receipt_file_path` and the old file differs, removes the previous file from disk.
  - `DELETE /api/transactions/{id}/receipt` (Removes an attached receipt from a transaction):
    - Permitted even when the transaction's allocations are locked (`is_locked == True`).
    - Deletes the file on disk from `RECEIPT_STORAGE_DIR` and sets `transaction.receipt_file_path = None`.
    - Returns updated `TransactionResponse`.
  - `GET /api/receipts/{path}` (Streams receipt file from `RECEIPT_STORAGE_DIR` with inline content disposition and detected media type (`application/pdf`, `image/png`, `image/jpeg`) for viewing in a new browser tab or downloading).
- ~~**Wave Push:**~~ *(Superseded)*
  - ~~`POST /api/sync/wave` (Must spawn a background task to process PENDING transactions to avoid 504 timeouts. Returns 202 Accepted).~~
- **Export & Lock Management:**
  - `GET /api/companies/{id}/export-transactions` (Generates and downloads a Wave-formatted CSV of business allocations for the company and **automatically locks** all exported allocations):
    - **Query Parameters:**
      - `include_locked`: Boolean (Defaults to `False`. When `False`, queries only unlocked business allocations `is_locked == False`. When `True`, includes both unlocked and already-locked business allocations).
      - `start_date`: Optional ISO Date (`YYYY-MM-DD`, inclusive filter on `Transaction.date`).
      - `end_date`: Optional ISO Date (`YYYY-MM-DD`, inclusive filter on `Transaction.date`).
    - **Automatic Locking Side-Effect:** All matched allocations with `is_locked == False` are atomically updated to `is_locked = True` and committed to the database when the CSV export is generated.
  - `POST /api/companies/{id}/lock-allocations` (Replaces ~~`POST /api/companies/{id}/mark-synced`~~):
    - Locks business allocations (`is_locked = True`) for this company. Accepts optional `allocation_ids` list in payload; if omitted, locks all currently unlocked allocations for the company.
  - `POST /api/companies/{id}/unlock-allocations` (Replaces ~~`POST /api/companies/{id}/revert-synced`~~):
    - Unlocks business allocations (`is_locked = False`) for this company. Accepts optional `allocation_ids` list in payload; if omitted, unlocks all locked allocations for the company.

### 5.2 Abstraction Layer for Intake Sources
The backend must include an abstraction layer for parsing transaction sources, enforcing the extraction of `external_id` for duplicate prevention.

## 6. Frontend UI Requirements (Vue 3 + Quasar)

### 6.1 Layout
Persistent navigation drawer: **Ledger**, **Manual Entry**, **Export Manager** (replacing ~~Sync Manager~~), and **Settings**.

### 6.2 Ledger View
- **Data Table:** Displays top-level `Transactions` using server-side pagination, sorting, and filtering (`source`, `company_id`, `start_date`, `end_date`).
- **Visual Lock Indicators (Transaction & Allocation Level):**
  - Each allocation displays its lock status visually (e.g., lock icon/badge when `allocation.is_locked == true`).
  - A parent transaction row is visually indicated as **Fully Locked** when all of its allocations have `is_locked == true`, or **Partially Locked** when a subset of its splits are locked.
- **Intentional Lock / Unlock Controls & Warning:**
  - Users can intentionally **Lock** an unlocked transaction (or individual allocation) directly from the UI without exporting (supporting the workflow where a user adjusts a transaction locally, fixes it manually in Wave, and locks it so it won't be exported again).
  - Users can intentionally **Unlock** a locked transaction or allocation.
  - **Unlock Warning Confirmation:** Clicking **Unlock** on a locked transaction or allocation **MUST** display a confirmation warning dialog before unlocking:
    > *"If this transaction has already been imported into an external accounting system, you must also adjust or remove it there manually."*
- **Receipt Viewing (Open in New Tab):**
  - Transactions with an attached receipt (`receipt_file_path != null`) display an interactive receipt icon button in the Receipt column.
  - Clicking the receipt button fetches the file via the authenticated `apiClient` (`GET /api/receipts/{path}` with `responseType: "blob"`), generates a browser object URL (`URL.createObjectURL(blob)`), and opens the receipt in a **new browser tab** (`window.open(blobUrl, "_blank")`).
- **Row Actions (Edit, Lock/Unlock, Delete):**
  - **Edit Button:** Opens the **Unified Edit Transaction Dialog** (Section 6.4). If **all** allocations on the transaction are locked (`Fully Locked`), transaction metadata and allocation editing are disabled until unlocked, though the user can still upload, replace, or remove the receipt (or click **Edit** disabled / **Manage Receipt**).
  - **Lock / Unlock Toggle Button:** Locks all allocations on the transaction, or prompts with the external-system warning to unlock them.
  - **Delete Button:**
    - Disabled if **any** allocation on the transaction has `is_locked == true` (with a tooltip explaining that locked allocations must be unlocked before deleting).
    - When enabled and clicked, prompts the user with a confirmation dialog before calling `DELETE /api/transactions/{id}` and refreshing the table.

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
  - Defaults to a single split assigning 100% of `Total Amount` to the selected `Company` (`is_personal = false`, `is_locked = false`).
  - Supports adding additional splits across different businesses for multi-company receipts.
  - Enforces that all allocations are business splits (`is_personal = false` with a selected `company_id`).
  - Real-time balance validation: Unallocated remainder (`Total Amount - sum(splits)`) must be `0.00`. Form submission is disabled while unbalanced.
- **Keyboard Navigation & Rapid Continuous Entry:**
  - **Global Shortcut:** Pressing `Ctrl + Enter` from anywhere within the form immediately submits the entry.
  - **Post-Submission Reset:** Upon successful creation (`201 Created`):
    1. Displays a success toast notification.
    2. Completely resets the form: Clears the date field (returns to empty), clears description, clears amount, clears receipt, and restores a single 100% default allocation to the selected company.
    3. **Auto-focuses the first field (Date)** so the user can immediately type the next receipt without touching the mouse.

### 6.4 Unified Transaction & Allocation Editor Dialog (`TransactionEditDialog.vue`)
A unified modal dialog invoked from the Ledger View allowing the user to edit transaction metadata, manage receipt attachments, and split/edit allocations in one place.

- **Transaction Metadata Controls:**
  - **Date (`YYYY-MM-DD`):** Required input with Quasar datepicker (`today-btn=true`). Disabled if any allocation is locked (`is_locked == true`).
  - **Description / Payee:** Required text input. Disabled if any allocation is locked (`is_locked == true`).
  - **Total Amount:** Required non-zero numeric input formatted to two decimal places. Disabled if all allocations are locked.
- **Receipt Management (Always Editable — Does Not Require Unlocking):**
  - Displays current receipt status:
    - If a receipt is attached (`receipt_file_path`), provides a **"View Receipt"** button (opens in a new tab), a **"Replace Receipt"** file picker (`.pdf`, `.png`, `.jpg`, `.jpeg`), and a **"Remove Receipt"** button.
    - If no receipt is attached, provides an **"Upload Receipt"** file picker.
  - Receipt changes can be saved even when the transaction's allocations are locked.
- **Personal vs. Business & Split Allocation Controls:**
  - **Personal Expense Toggle (`is_personal`):**
    - **Rule:** Only business transactions (`is_personal == false`) can be split.
    - If `splits.length > 1`, the `is_personal` toggle is **disabled** with a tooltip/message: *"Remove extra splits before marking this transaction as personal."*
    - When `is_personal` is toggled to `true` (only allowed when `splits.length === 1` and the allocation is unlocked):
      - The single allocation's `company_id` is cleared (`null`) and its amount is locked to `100%` of `Total Amount`.
      - The Company select dropdown and **"Add Split"** button are disabled.
  - **Business Splits (`is_personal == false`):**
    - Each split row displays:
      1. **Company Select Dropdown** (required).
      2. **Split Amount Input** (readonly if `splits.length === 1`, editable when `splits.length > 1`).
      3. **Allocation Lock Indicator & Toggle (`is_locked`):** Shows whether this specific split is locked (`is_locked == true`) or unlocked (`is_locked == false`). Users can lock an unlocked split, or click to unlock a locked split (which triggers the external-system warning confirmation).
      4. **Remove Split Button:** Enabled when `splits.length > 1` and `!split.is_locked`.
    - **Partial Lock Editing Behavior:**
      - If a transaction is split across Company A (`is_locked == true`) and Company B (`is_locked == false`), the parent dialog remains open for editing: Company A's row inputs (`company_id`, `amount`, remove button) are disabled, while Company B's row can be freely edited or further split across additional companies as long as `Total Amount - sum(splits) == 0.00`.
    - **Real-Time Balance Validation:**
      - Displays the live remainder badge (`Balanced ($0.00 remaining)`, `Unallocated`, or `Overallocated`).
      - Saving metadata/allocation changes is disabled whenever `remainderCents !== 0`.

### 6.5 Export Manager UI (Supersedes Sync Manager UI)
Dedicated view (`/export-manager`) for reviewing and generating Wave-compatible CSV exports per company:
- **Filter Bar:**
  - **Company Select Dropdown (`company_id`):** Starts empty (`null`). Selecting a company loads the matching business allocations for preview and export.
  - **Optional Date Range Filter (`start_date`, `end_date`):** Allows scoping the preview and CSV export (or re-export) to a specific period.
  - **"Include locked transactions" Toggle (`include_locked`):** Boolean toggle defaulting to `false`. When `false`, displays and exports only unlocked (`is_locked == false`) business allocations for the selected company. When `true`, includes both unlocked and already-locked (`is_locked == true`) business allocations.
- **Export Action Bar (Below Filter Bar, Above Allocations Table):**
  - **"Export CSV" Button:** Disabled when no company is selected. When clicked, calls `GET /api/companies/{id}/export-transactions` (with `include_locked`, `start_date`, `end_date` query params), triggers the browser CSV download, automatically locks (`is_locked = true`) all exported allocations on the backend, and refreshes the allocations table and company statistics.
- **Company Allocations Preview Table:**
  - Displays the business allocations (`is_personal == false`) for the selected company matching the active filter criteria so the user can review what is being exported.
  - **Pagination:** Default page size of `50` items (`rowsPerPage: 50`).
  - **Columns:**
    - **Date:** Parent transaction date (`YYYY-MM-DD`).
    - **Description:** Parent transaction description.
    - **Amount:** Allocation split amount formatted as currency.
    - **Lock Status:** Visual badge indicating whether the allocation is `Locked` (`is_locked == true`) or `Unlocked` (`is_locked == false`).
    - **Receipt:** Interactive receipt icon button (when `receipt_file_path != null`) that opens the receipt in a new browser tab.
    - **Ledger Link:** Link/button that opens the parent transaction in the Ledger view (`/ledger?transaction_id={transaction_id}`) in a **new browser tab** (`target="_blank"`).

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

#### 7.1.2 Lock State Lifecycle & Rules (`Allocation.is_locked`)
- **State Representation:** Boolean `is_locked` on `Allocation` (replaces legacy `sync_status` enum).
- **Creation:** All new allocations default to `is_locked = False`.
- **Automatic Locking on Export:** Exporting business allocations for a company via `GET /api/companies/{id}/export-transactions` automatically sets `is_locked = True` on all exported allocations for that company.
- **Re-Exporting Locked Allocations:** Passing `include_locked=true` (and optional `start_date` / `end_date`) to `GET /api/companies/{id}/export-transactions` includes already-locked allocations in the generated CSV.
- **Intentional Manual Lock & Unlock:**
  - Users can manually lock any unlocked allocation/transaction (e.g., after manually adjusting an entry in both Wrangler and Wave so it will be excluded from the next default CSV export).
  - Users can manually unlock any locked allocation/transaction after acknowledging the external-system warning.
- **Transaction Edit & Delete Safety:**
  - **Partial Lock:** If a transaction has both locked (`is_locked == True`) and unlocked (`is_locked == False`) allocations, the parent transaction remains editable for the unlocked allocations, while the locked allocations cannot be modified or removed without unlocking them first.
  - **Full Lock:** If **all** allocations on a transaction have `is_locked == True`, modifying transaction metadata or allocations is prohibited (`400 Bad Request`) until unlocked.
  - **Deletion:** Deleting a transaction (`DELETE /api/transactions/{id}`) is prohibited (`400 Bad Request`) if **any** of its allocations has `is_locked == True`.
  - **Receipt Independence:** Uploading, replacing, or removing a receipt (`POST /api/transactions/{id}/receipt` or `DELETE /api/transactions/{id}/receipt`) is always allowed regardless of `is_locked`.

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
