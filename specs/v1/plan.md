# Implementation Plan for Family Accounting App

This document outlines the step-by-step implementation plan based on `spec.md`. The plan is divided into logical, human-testable phases with atomic tasks in dependency order.

Each task is numbered by its phase and sequence number (e.g., Task 2.1). Checkboxes and progress tracking are managed separately in `tasks.md`.

---

## Phase 1: Backend Foundation and Database Setup
*Goal: Initialize the FastAPI project, set up configuration, create the database schema, and implement the health check endpoint.*

### 1.1 Initialize Python environment and dependencies
- Set up Python 3.14.x compatible virtual environment.
- Install backend dependencies: `FastAPI`, `Uvicorn`, `SQLAlchemy` or `SQLModel`, `Pydantic`, and `Alembic`.

### 1.2 Set up project structure
- Create backend directory layout: `routers/`, `models/`, `schemas/`, `services/`, `core/` (config & security), and `database.py` (engine and session management).

### 1.3 Create configuration module for environment variables
- Implement configuration loader (e.g., using `pydantic-settings`) to read:
  - `ADMIN_USERNAME`, `ADMIN_PASSWORD`
  - `JWT_SECRET_KEY`, `JWT_ACCESS_TOKEN_EXPIRE_MINUTES`
  - `WAVE_CLIENT_ID`, `WAVE_CLIENT_SECRET`, `WAVE_REDIRECT_URI`
  - `RECEIPT_STORAGE_DIR` (resolve absolute path)

### 1.4 Initialize SQLite database connection and ORM setup
- Configure SQLite connection with WAL mode and foreign key enforcement enabled.
- Set up ORM sessionmaker and declarative base.

### 1.5 Define Company ORM model
- Attributes:
  - `id`: UUID primary key
  - `name`: String
  - `wave_business_id`: String (nullable until linked)
  - `wave_access_token`: String (nullable until linked)
  - `wave_refresh_token`: String (nullable until linked)
  - `wave_token_expires_at`: DateTime (nullable until linked)
  - `wave_equity_account_id`: String (required for double-entry offset)

### 1.6 Define WaveCategory ORM model
- Attributes:
  - `id`: UUID primary key
  - `company_id`: Foreign Key to `Company`
  - `wave_account_id`: String
  - `name`: String

### 1.7 Define Transaction ORM model
- Attributes:
  - `id`: UUID primary key
  - `source`: String (e.g., "manual", "amazon")
  - `external_id`: String (nullable)
  - `date`: Date
  - `description`: String
  - `total_amount`: Decimal / Float (supports negative values for refunds)
  - `currency_code`: String (default base currency)
  - `receipt_file_path`: String (nullable)
  - ~~`is_approved`: Boolean (default False)~~ *(Superseded: Approval removed)*
- Enforce unique constraint on `(source, external_id)`.

### 1.8 Define Allocation ORM model
- Attributes:
  - `id`: UUID primary key
  - `transaction_id`: Foreign Key to `Transaction`
  - `amount`: Decimal / Float
  - `is_personal`: Boolean (default False)
  - `company_id`: Foreign Key to `Company` (nullable)
  - `wave_category_id`: Foreign Key to `WaveCategory` (nullable)
  - `sync_status`: Enum (`PENDING`, `SYNCED`, `FAILED`, `IGNORED`)
  - `wave_transaction_id`: String (nullable)

### 1.9 Set up Alembic and apply initial migrations
- Initialize Alembic, configure `env.py` with model metadata and target database URL.
- Generate initial schema migration and execute `alembic upgrade head`.

### 1.10 Ensure receipt storage directory creation
- Add an application startup event or utility ensuring the path defined in `RECEIPT_STORAGE_DIR` exists on the filesystem.

### 1.11 Implement SQLite health check endpoint
- Update `GET /api/health` as an unauthenticated, public probe for uptime and container monitoring.
- Inject the SQLAlchemy database session dependency (`get_db`) and execute a lightweight `SELECT 1` query against SQLite.
- On success, return HTTP `200 OK` with payload:
  ```json
  {
    "status": "ok",
    "database": "healthy",
    "meta": {
      "database_path": "wrangler.db"
    }
  }
  ```
- If SQLite is unreachable, locked, or query execution raises an exception, return HTTP `503 Service Unavailable` with payload:
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

---

## Phase 2: Authentication & Security (Backend)
*Goal: Secure the API and issue JWTs for the single admin user.*

### 2.1 Implement JWT utilities
- Implement functions to generate and decode JWT tokens with expiration using `JWT_SECRET_KEY` and `JWT_ACCESS_TOKEN_EXPIRE_MINUTES`.

### 2.2 Implement admin credential verification
- Implement secure comparison for incoming username and password against `ADMIN_USERNAME` and `ADMIN_PASSWORD`.

### 2.3 Create `POST /api/login` endpoint
- Accepts credentials payload, validates against admin settings, and returns `{ "access_token": "...", "token_type": "bearer" }`.

 ### 2.4 Implement automatic authentication middleware & route protection
- Implement `AuthenticationMiddleware` intercepting all incoming requests to ensure all endpoints are secure by default regardless of router.
- Support opt-in anonymous routes (`/api/health`, `/api/login`, and API docs), rejecting all other unauthenticated requests with HTTP `401 Unauthorized`.
- Implement `get_current_user` dependency to extract `request.state.current_user` for endpoints requiring the caller's identity.

---

## Phase 3: Company Management & Wave OAuth (Backend)
*Goal: Manage company records and establish API access to Wave via OAuth.*

### 3.1 Create Company CRUD endpoints
- Implement `GET /api/companies`, `POST /api/companies`, `PUT /api/companies/{id}`, and `DELETE /api/companies/{id}`.
- Support configuring company name and `wave_equity_account_id`.

### 3.2 Create Wave API client utility
- Set up HTTP client utility for Wave GraphQL and OAuth endpoints.

### 3.3 Implement `GET /api/wave/oauth/authorize` endpoint
- Validates `company_id` exists.
- Generates a signed JWT containing `company_id` placed inside the OAuth `state` query parameter.
- Returns redirect URL to Wave requesting scopes: `business:read`, `account:read`, `transaction:write`.

### 3.4 Implement `GET /api/wave/oauth/callback` endpoint
- Validates and unpacks the signed `state` parameter to identify the target `company_id`.
- Exchanges authorization code for `access_token`, `refresh_token`, and expiration timestamp.
- Updates the corresponding `Company` record with the tokens.

### 3.5 Implement Wave token refresh logic
- In the Wave client, verify `wave_token_expires_at` before making requests; refresh tokens automatically using `wave_refresh_token` and persist the new token set to the database.

---

## Phase 4: Wave Chart of Accounts Sync
*Goal: Pull down and cache valid categories from Wave.*

### 4.1 Implement Wave Chart of Accounts GraphQL query
- Implement GraphQL query fetching accounts for a given business ID, filtering only for applicable Expense, Asset, and Income accounts.

### 4.2 Create `POST /api/companies/{id}/sync-categories` endpoint
- Retrieves company credentials, calls Wave GraphQL API, and parses returned categories.

### 4.3 Implement upsert logic for `WaveCategory`
- Insert new accounts and update existing ones in `WaveCategory` table scoped to `company_id`.

---

## Phase 5: Transaction & Allocation Management (Backend)
*Goal: Handle the core financial data model, split allocations, and receipt uploads.*

### 5.1 Implement intake source parser abstraction
- Define an abstract base class/interface for transaction intake parsing, requiring extraction of `external_id`, `date`, `description`, `total_amount`, `currency_code`, and `source`.
- Implement default manual parser.

### 5.2 Create `POST /api/transactions` endpoint
- Support manual transaction creation with optional initial receipt file upload.

### 5.3 Create `GET /api/transactions` endpoint with server-side pagination
- Support pagination parameters (`page`, `page_size`), sort parameters, and return total count, page metadata, and transaction items with allocations.

### 5.4 Create `PUT /api/transactions/{id}` and ~~`PUT /api/transactions/{id}/approve`~~ endpoints
- Update transaction metadata. (Approval endpoint superseded and removed).

### 5.5 Create `PUT /api/transactions/{id}/allocations` endpoint
- Accept a list of split allocations for a transaction, replacing or updating the allocations in the database.

### 5.6 Enforce immutability validation on allocations
- In `PUT /api/transactions/{id}/allocations`, check if any existing allocation has `sync_status == SYNCED`. Return HTTP 400 Bad Request if any synced allocation exists.

### 5.7 Implement receipt upload and retrieval endpoints
- `POST /api/transactions/{id}/receipt`: Save uploaded multipart file into `RECEIPT_STORAGE_DIR` and save path to `Transaction.receipt_file_path`.
- `GET /api/receipts/{path}`: Safely stream/serve receipt file from `RECEIPT_STORAGE_DIR`.

---

## Phase 6: Frontend Foundation
*Goal: Initialize the frontend application, layout, authentication, and API client.*

### 6.1 Initialize Vue 3 + Typescript + Quasar project with Pinia
- Set up frontend project with Vue 3.5.x, Quasar 2.30.x, and Pinia 3.x.

### 6.2 Configure Vue Router and navigation guards
- Configure routes for Login, Ledger, Manual Entry, Sync Manager, and Settings.
- Implement global navigation guard checking Pinia auth state for a valid JWT.

### 6.3 Implement Login View
- Create login form component, bind credentials, call `POST /api/login`, store JWT in auth store, and redirect to Ledger on success.

### 6.4 Implement persistent Navigation Drawer layout
- Build main layout with persistent Quasar navigation drawer providing links to Ledger, Manual Entry, Sync Manager, and Settings.

### 6.5 Implement Fetch API client wrapper
- Build centralized wrapper around native `fetch` that automatically attaches `Authorization: Bearer <token>` headers, handles base URLs, parses JSON, and redirects to login on 401.

---

## Phase 7: Frontend Company & Settings Management
*Goal: Allow users to configure businesses and Wave connections.*

### 7.1 Create Company Management & Settings View
- Build interface listing all configured companies and controls to add or edit companies.

### 7.2 Implement Company form
- Form inputs for `name` and `wave_equity_account_id`. Connect form to `POST /api/companies` and `PUT /api/companies/{id}`.

### 7.3 Implement "Connect to Wave" OAuth action
- Button invoking `GET /api/wave/oauth/authorize?company_id={id}` and redirecting browser to Wave's OAuth consent screen.

### 7.4 Implement token status indicator
- Display connection status (Connected, Disconnected, or Expired) based on company token presence and expiration timestamp.

### 7.5 Implement "Sync Categories" button
- Button triggering `POST /api/companies/{id}/sync-categories` with loading states and user notification upon success.

---

## Phase 8: Revert Wave Integration (Backend & Database)
*Goal: Remove Wave API integrations, clean up backend models and configuration, and migrate the database schema to remove Wave-specific fields and tables.*

### 8.1 Remove Wave configuration settings from backend
- In `core/config.py`, remove `WAVE_CLIENT_ID`, `WAVE_CLIENT_SECRET`, and `WAVE_REDIRECT_URI` settings.
- Ensure the configuration loader only expects `ADMIN_USERNAME`, `ADMIN_PASSWORD`, `JWT_SECRET_KEY`, `JWT_ACCESS_TOKEN_EXPIRE_MINUTES`, and `RECEIPT_STORAGE_DIR`.

### 8.2 Remove Wave routers, services, and schemas
- Unregister and delete `routers/wave_oauth.py`.
- Remove `POST /api/companies/{id}/sync-categories` and `GET /api/companies/{id}/categories` endpoints from `routers/companies.py`.
- Delete `services/wave.py`.
- Delete `schemas/wave.py` and `schemas/wave_category.py`.

### 8.3 Update Company ORM model and schemas
- In `models/company.py`, remove columns: `wave_business_id`, `wave_access_token`, `wave_refresh_token`, `wave_token_expires_at`, and `wave_equity_account_id`.
- Ensure `name` is unique on `Company`.
- In `schemas/company.py`, update `CompanyCreate`, `CompanyUpdate`, and `CompanyResponse` to only expose `id` and `name`.

### 8.4 Update Allocation ORM model, SyncStatus enum, and drop WaveCategory model
- In `models/allocation.py`, remove `wave_category_id` and `wave_transaction_id` columns and relationships.
- Update `SyncStatus` enum to only contain `PENDING` and `SYNCED`.
- Delete `models/wave_category.py` and remove references in model metadata.
- In `schemas/allocation.py`, remove `wave_category_id` and `wave_transaction_id`.

### 8.5 Update allocation endpoints and company deletion validation
- In `routers/transactions.py`, update `PUT /api/transactions/{id}/allocations` to remove WaveCategory validation. Ensure foreign key validation only checks `company_id` when `is_personal` is False.
- Retain immutability validation returning HTTP 400 if any existing allocation is `SYNCED`.
- In `routers/companies.py`, update `DELETE /api/companies/{id}` to verify whether any allocations reference the company; if linked allocations exist, return HTTP 400 Bad Request.

### 8.6 Generate and execute Alembic migration for schema cleanup
- Create an Alembic migration using batch operations for SQLite:
  - Drop the `wave_categories` table.
  - Drop Wave columns from `companies` (`wave_business_id`, `wave_access_token`, `wave_refresh_token`, `wave_token_expires_at`, `wave_equity_account_id`).
  - Drop `wave_category_id` and `wave_transaction_id` from `allocations`.
  - Ensure unique constraint on `companies.name`.
- Run `alembic upgrade head` to apply the migration.

---

## Phase 9: Backend Export & Sync Reconciliation Endpoints
*Goal: Implement server-side filtering, allocation status reversion, and Wave-compatible CSV generation and reconciliation endpoints.*

### 9.1 Implement transaction filtering on `GET /api/transactions`
- Update `GET /api/transactions` in `routers/transactions.py` to support filtering query parameters: `source`, `start_date`, `end_date` and `company_id` (~~`is_approved`~~ filter superseded).
- Apply filters to database query alongside existing pagination (`page`, `page_size`) and sorting.

### 9.2 Implement single allocation reversion endpoint (`PUT /api/allocations/{id}/revert`)
- Implement `PUT /api/allocations/{id}/revert` endpoint.
- If allocation exists and is `SYNCED`, revert `sync_status` to `PENDING` and commit. Return updated allocation. Return 404 if allocation does not exist.

### 9.3 Implement RFC 4180 CSV export utility for Wave format
- Implement CSV generator utility adhering to Wave specifications:
  - Header: `Date,Description,Amount`
  - `Date`: ISO 8601 (`YYYY-MM-DD`) from parent `Transaction.date`.
  - `Description`: Escaped text string from parent `Transaction.description`.
  - `Amount`: Two decimal places with leading negative sign for refunds/credits from `Allocation.amount`.
  - Filter: Exclude personal allocations; map each business allocation for the company to one row.

### 9.4 Implement `GET /api/companies/{id}/export-transactions` endpoint
- Add endpoint accepting query parameter `status` (defaults to `PENDING`, optional `SYNCED`).
- Query business allocations for the company matching the specified status.
- Generate CSV using export utility and stream file download with `Content-Type: text/csv` and descriptive filename attachment.

### 9.5 Implement `POST /api/companies/{id}/mark-synced` endpoint
- Add endpoint accepting optional payload `allocation_ids: list[uuid.UUID] | None`.
- If `allocation_ids` is provided, mark those specific allocations for the company as `SYNCED`.
- If `allocation_ids` is omitted or empty, mark all `PENDING` allocations for the company as `SYNCED`.

### 9.6 Implement `POST /api/companies/{id}/revert-synced` endpoint
- Add endpoint accepting optional payload `allocation_ids: list[uuid.UUID] | None`.
- If `allocation_ids` is provided, revert those specific allocations for the company back to `PENDING`.
- If `allocation_ids` is omitted or empty, revert all `SYNCED` allocations for the company back to `PENDING`.

---

## Phase 10: Frontend Wave Reversion & Settings Updates
*Goal: Remove Wave integration UI elements from the frontend and update company settings and navigation.*

### 10.1 Remove Wave OAuth UI and actions from Settings
- In `web/src/views/SettingsView.vue`, remove "Connect to Wave", "Reconnect Wave", and "Sync Categories" buttons.
- Remove token status column and remove `TokenStatusBadge.vue` component.

### 10.2 Update Company dialog, types, and store
- In `web/src/types/company.ts`, remove Wave-related properties.
- In `web/src/components/CompanyFormDialog.vue`, remove the `wave_equity_account_id` field, keeping only Company Name.
- In `web/src/stores/companies.ts`, remove OAuth and category sync methods.
- In `web/src/views/SettingsView.vue`, display total allocated transaction count for each company.

### 10.3 Update navigation drawer and routing for Export Manager
- In `web/src/layouts/nav.ts`, replace "Sync Manager" with "Export Manager" (`path: "/export-manager"`).
- In `web/src/router/routes.ts`, update route to map `/export-manager` to `ExportManagerView.vue`.
- Rename or replace `web/src/views/SyncManagerView.vue` with `web/src/views/ExportManagerView.vue`.

---

## Phase 11: Frontend Ledger & Allocation Editor
*Goal: Implement the transaction ledger table, receipt downloads, and transaction split editor without Wave category dependencies.*

### 11.1 Build Ledger View with server-side pagination and filters
- In `web/src/views/LedgerView.vue`, implement `QTable` connected to `GET /api/transactions` supporting server-side pagination, sorting, and filter controls (`source`, date range, company; ~~`is_approved`~~ filter superseded).

### 11.2 Implement visual locking for synced transactions and reversion action
- Display a locked indicator badge on transactions containing any `SYNCED` allocations, disabling split editing.
- Provide a row/inline action to revert synced allocations back to `PENDING` via `PUT /api/allocations/{id}/revert`, unlocking the transaction.

### 11.3 Build Allocation Editor (Transaction Splitter) component
- Modal or expandable panel allowing users to split transaction amounts across personal and business entities.
- Controls: `is_personal` toggle, Company select dropdown (disabled if personal), and amount input.
- Enforce validation ensuring sum of allocation amounts equals `Transaction.total_amount`.

### 11.4 Integrate Allocation Editor with backend API
- Submit updated splits to `PUT /api/transactions/{id}/allocations`.
- Handle HTTP 400 error cleanly if parent transaction contains synced allocations.

### 11.5 Implement receipt file upload and direct download link
- Add receipt file upload button calling `POST /api/transactions/{id}/receipt`.
- Add receipt download link/button for transactions with `receipt_file_path` calling `GET /api/receipts/{path}` so users can inspect and download receipt files for manual upload to Wave.

### ~~11.6 Implement transaction approval toggle UI~~ (Superseded)
- ~~Add approval toggle button or checkbox calling `PUT /api/transactions/{id}/approve`.~~ *(Superseded: Approval status and endpoint removed).*

---

## Phase 12: Frontend Export Manager UI
*Goal: Implement the Export Manager view to generate Wave-compatible CSVs and manage allocation sync reconciliation.*

### 12.1 Build Export Manager View with Pending Exports Summary
- In `web/src/views/ExportManagerView.vue`, display a pending exports summary grouped by Company.
- For each company, show: Company Name, count of `PENDING` allocations, and total dollar amount of pending allocations.

### 12.2 Implement "Export CSV" download action per company
- Add "Export CSV" button per company triggering `GET /api/companies/{id}/export-transactions?status=PENDING` and downloading the generated RFC 4180 CSV file.

### 12.3 Implement "Mark as Synced" action per company
- Add "Mark as Synced" button that becomes active/primary after export, calling `POST /api/companies/{id}/mark-synced` to transition pending allocations to `SYNCED`.

### 12.4 Build Reconciliation & History section with reversion
- Build tab or expandable view displaying `SYNCED` allocations grouped by company.
- Add "Revert to Pending" button calling `POST /api/companies/{id}/revert-synced` to return allocations to `PENDING` state if a Wave import was aborted or needs correction.

---

## Phase 13: Manual Expense Intake & Rapid Entry Form
*Goal: Implement backend atomic manual transaction creation with company attribution and default allocation, along with a dedicated keyboard-optimized manual entry UI.*

### 13.1 Update `POST /api/transactions` endpoint and schemas for company attribution and atomic allocations
- Update `TransactionCreate` schema to require `company_id: UUID`, validate that `total_amount` is strictly non-zero (positive for expenses, negative for returns/refunds), and accept optional `allocations: list[AllocationCreateItem]`.
- Update `POST /api/transactions` in `routers/transactions.py`:
  - Enforce split balance validation: if `allocations` list is provided, verify `sum(allocation.amount) == total_amount`.
  - In a single atomic database transaction:
    1. Create `Transaction` record with `source = "manual"` and `company_id`. (~~`is_approved`~~ superseded and removed).
    2. If a receipt file is uploaded in `multipart/form-data`, persist to `RECEIPT_STORAGE_DIR` and set `receipt_file_path`.
    3. Create `Allocation` records: if splits are omitted in the request, automatically generate a single default business allocation (`amount = total_amount`, `company_id = payload.company_id`, `is_personal = false`, `sync_status = PENDING`). If splits are provided, persist them as business allocations.
  - Return HTTP `201 Created` with `TransactionResponse` populated with the generated allocations.

### 13.2 Build Manual Entry form controls and datepicker in `ManualEntryView.vue`
- In `web/src/views/ManualEntryView.vue`, build form layout dedicated exclusively to business expenses:
  - Date input: starts empty (no default date); integrates Quasar datepicker popup (`q-date` / `q-popup-proxy`) configured with `today-btn=true` for 1-click current date selection.
  - Description / Payee: required text input.
  - Total Amount: required numeric input formatted to two decimal places, strictly non-zero.
  - Company: required select dropdown populated with active businesses from `useCompanyStore`.
  - Receipt Attachment: optional file dropzone/picker accepting PDF, PNG, and JPEG.
  - ~~Approval Toggle: optional toggle (`is_approved`), defaults to `true`.~~

### 13.3 Implement inline allocation splitter with real-time balance validation
- Within `ManualEntryView.vue`, build an inline split manager:
  - Default state: single split assigning 100% of `Total Amount` to the selected `Company` (`is_personal = false`, `sync_status = PENDING`).
  - Support adding and removing additional business splits across different active companies for multi-company receipts.
  - Enforce business splits only: restrict `is_personal` to `false` and require a valid `company_id`.
  - Real-time balance validation: calculate remainder (`Total Amount - sum(splits)`). Disable submit action while remainder != `0.00` and display a clear balance indicator.

### 13.4 Implement keyboard shortcuts, rapid continuous entry reset, and auto-focus
- Attach a global `Ctrl + Enter` keydown shortcut within the form to trigger submission immediately.
- Attach `Ctrl + ;` keydown shortcut within the date field to auto-fill today's date.
- Integrate submission with `POST /api/transactions` (using `multipart/form-data` if receipt file attached, else JSON).
- On HTTP `201 Created`:
  1. Show a success toast notification.
  2. Completely reset form fields: empty the date input, clear description, clear amount, clear receipt file, and restore a single 100% default allocation to the selected company.
  3. Automatically programmatically focus the Date input field so the user can immediately type the next expense without using the mouse.

### 13.5 Verify Manual Entry end-to-end in browser
- Verify manual transaction creation with single company default allocation.
- Verify multi-company split allocation creation and remainder validation.
- Verify receipt file attachment and storage.
- Verify `today-btn=true` one-click date selection, `Ctrl + Enter` shortcut submission, and post-submission form reset with Date field auto-focus.

---

## Phase 14: Removal of `is_approved` (Schema & Code Remediation)
*Goal: Remove the superseded `is_approved` field and `/approve` endpoint across the database schema, backend code, frontend UI, and test suites.*

### 14.1 Generate and apply Alembic migration to drop `is_approved`
- Create a new Alembic migration script using `op.drop_column('transactions', 'is_approved')`.
- Apply migration to update the SQLite database schema (`wrangler.db`).

### 14.2 Remove `is_approved` and `TransactionApproveRequest` from backend schemas and ORM model
- In `api/src/models/transaction.py`, remove the `is_approved` mapped column from `Transaction`.
- In `api/src/schemas/transaction.py`, remove `is_approved` from `TransactionCreate`, `TransactionUpdate`, and `TransactionResponse`.
- Remove `TransactionApproveRequest` schema entirely.

### 14.3 Remove `/approve` endpoint and filter query from `routers/transactions.py`
- In `api/src/routers/transactions.py`, remove `@router.put("/{transaction_id}/approve")`.
- Remove `is_approved` query parameter and filtering logic from `GET /api/transactions`.
- Remove `is_approved` form/json parsing from `POST /api/transactions` and `PUT /api/transactions/{id}`.

### 14.4 Remove `is_approved` from frontend types, store, and views
- In `web/src/types/transaction.ts`, remove `is_approved` from `Transaction` interface and filter interfaces.
- In `web/src/stores/transactionStore.ts`, remove `is_approved` state and filter query serialization.
- In `web/src/views/LedgerView.vue`, remove approval column and approval filter UI elements.
- In `web/src/views/ManualEntryView.vue`, ensure no approval toggles or references exist.

### 14.5 Update backend and frontend test suites
- In `api/tests/test_transactions.py`, `test_models.py`, and `test_transaction_flow.py`, remove or update tests asserting `is_approved` or invoking `/approve`.
- In `web/tests/transaction.test.ts`, update store and view tests to remove `is_approved` assertions.
- Run all backend and frontend test suites to verify 100% pass rate.


