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
  - `is_approved`: Boolean (default False)
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

### 1.12 Verify database schema setup and health check endpoint
- Run migration script and verify table creation, columns, relationships, and unique constraints in SQLite.
- Send a request to `GET /api/health` using a REST client to verify HTTP `200 OK` and healthy response payload with metadata.
- Verify HTTP `503 Service Unavailable` error handling when SQLite is unreachable or query execution fails.

---

## Phase 2: Authentication & Security (Backend)
*Goal: Secure the API and issue JWTs for the single admin user.*

### 2.1 Implement JWT utilities
- Implement functions to generate and decode JWT tokens with expiration using `JWT_SECRET_KEY` and `JWT_ACCESS_TOKEN_EXPIRE_MINUTES`.

### 2.2 Implement admin credential verification
- Implement secure comparison for incoming username and password against `ADMIN_USERNAME` and `ADMIN_PASSWORD`.

### 2.3 Create `POST /api/login` endpoint
- Accepts credentials payload, validates against admin settings, and returns `{ "access_token": "...", "token_type": "bearer" }`.

### 2.4 Create authentication dependency (`get_current_user`)
- Implement FastAPI dependency to parse and validate `Authorization: Bearer <token>` header, returning 401 Unauthorized on invalid or missing tokens.

### 2.5 Verify authentication and route protection
- Use a REST client to verify `POST /api/login` succeeds with valid credentials, fails with invalid credentials, and protected routes reject requests without a valid token.

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

### 3.6 Verify company management and OAuth flow
- Create a company record via REST client, test authorize redirect URL generation, simulate callback exchange, and verify tokens in database.

---

## Phase 4: Wave Chart of Accounts Sync
*Goal: Pull down and cache valid categories from Wave.*

### 4.1 Implement Wave Chart of Accounts GraphQL query
- Implement GraphQL query fetching accounts for a given business ID, filtering only for applicable Expense, Asset, and Income accounts.

### 4.2 Create `POST /api/companies/{id}/sync-categories` endpoint
- Retrieves company credentials, calls Wave GraphQL API, and parses returned categories.

### 4.3 Implement upsert logic for `WaveCategory`
- Insert new accounts and update existing ones in `WaveCategory` table scoped to `company_id`.

### 4.4 Verify category synchronization
- Trigger `POST /api/companies/{id}/sync-categories` via REST client and verify records are populated in SQLite.

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

### 5.4 Create `PUT /api/transactions/{id}` and `PUT /api/transactions/{id}/approve` endpoints
- Update transaction metadata and toggle `is_approved`.

### 5.5 Create `PUT /api/transactions/{id}/allocations` endpoint
- Accept a list of split allocations for a transaction, replacing or updating the allocations in the database.

### 5.6 Enforce immutability validation on allocations
- In `PUT /api/transactions/{id}/allocations`, check if any existing allocation has `sync_status == SYNCED`. Return HTTP 400 Bad Request if any synced allocation exists.

### 5.7 Implement receipt upload and retrieval endpoints
- `POST /api/transactions/{id}/receipt`: Save uploaded multipart file into `RECEIPT_STORAGE_DIR` and save path to `Transaction.receipt_file_path`.
- `GET /api/receipts/{path}`: Safely stream/serve receipt file from `RECEIPT_STORAGE_DIR`.

### 5.8 Verify transaction and allocation endpoints
- Test creating transactions, updating split allocations, verifying the 400 error on synced items, and uploading/retrieving receipt files via REST client.

---

## Phase 6: Frontend Foundation
*Goal: Initialize the frontend application, layout, authentication, and API client.*

### 6.1 Initialize Vue 3 + Quasar project with Pinia
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

### 6.6 Verify frontend foundation
- Run dev server, verify login flow, test route protection guards, and confirm navigation drawer switches views correctly.

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

### 7.6 Verify Company Management UI
- Verify creating a company, setting the equity account ID, initiating OAuth, and syncing categories via browser.

---

## Phase 8: Frontend Ledger & Allocation Editor
*Goal: Provide the main interface for reviewing and categorizing expenses.*

### 8.1 Create Ledger View with server-side pagination
- Build table using `QTable` connected to `GET /api/transactions` supporting server-side pagination, sorting, and row selection.

### 8.2 Implement visual locking for synced transactions
- When a transaction contains any allocation with `sync_status == SYNCED`, render a lock indicator and disable editing actions.

### 8.3 Build Allocation Editor (Transaction Splitter) component
- Modal or expandable row allowing user to split the total transaction amount into multiple allocations.
- Controls: `is_personal` toggle, Company select dropdown, Wave Category select dropdown (filtered by selected company), and split amount.

### 8.4 Integrate Allocation Editor with backend
- Submit updated splits to `PUT /api/transactions/{id}/allocations`. Handle 400 error cleanly if record is locked.

### 8.5 Implement receipt upload and view component
- File upload trigger calling `POST /api/transactions/{id}/receipt` and link/modal to view receipt via `GET /api/receipts/{path}`.

### 8.6 Implement transaction approval UI
- Checkbox or button to toggle transaction approval status via `PUT /api/transactions/{id}/approve`.

### 8.7 Verify Ledger and Allocation Editor UI
- Test viewing transactions, splitting allocations, uploading receipts, approving transactions, and checking lock state in browser.

---

## Phase 9: Wave Synchronization Engine (Backend)
*Goal: Push approved transactions to Wave as a background task.*

### 9.1 Implement Wave GraphQL `documentCreate` mutation (Receipt upload)
- Implement multipart file upload using `httpx` and the Apollo GraphQL multipart request specification to upload receipt files to Wave.

### 9.2 Implement Wave GraphQL transaction mutation builder
- Construct mutation using `wave_category_id` (line items) and `wave_equity_account_id` (anchor/offset account).

### 9.3 Implement transaction grouping logic
- Group multiple allocations for the same company from a single parent `Transaction` into a single Wave transaction with multiple line items.

### 9.4 Implement refund and negative amount handling
- When allocation amount is negative, invert debit/credit legs in the Wave GraphQL transaction payload.

### 9.5 Implement cross-company receipt upload logic
- If a receipt is attached to a parent transaction split across multiple companies, upload the receipt separately to each company's Wave workspace.

### 9.6 Implement background task worker logic
- Worker process querying `PENDING` allocations on approved transactions, calling Wave API for receipts and transactions, and marking results as `SYNCED` or `FAILED`.

### 9.7 Wrap Wave push updates in local database transaction
- Wrap the local DB updates (`sync_status = SYNCED` and `wave_transaction_id`) inside a local DB transaction to prevent orphan states if local commit fails.

### 9.8 Implement `POST /api/sync/wave` endpoint
- Spawns background task and returns `202 Accepted`.

### 9.9 Implement sync progress polling endpoint
- Endpoint reporting status of ongoing or completed background sync operations.

### 9.10 Verify Wave synchronization engine
- Test background worker logic, grouping, refund debit/credit inversion, receipt upload, and atomic DB updates.

---

## Phase 10: Sync Manager & Polling (Frontend)
*Goal: Let users manage and monitor the Wave sync process.*

### 10.1 Create Sync Manager View
- Build view displaying allocations filtered/grouped by `PENDING` and `FAILED` statuses.

### 10.2 Implement "Sync to Wave" action
- Action button calling `POST /api/sync/wave` and initiating progress polling.

### 10.3 Implement "Retry Failed" action
- Button to reset `FAILED` allocations to `PENDING` and trigger sync.

### 10.4 Implement polling mechanism for sync progress
- Implement periodic polling while background task is active to update UI state and notify user upon completion.

### 10.5 Implement error display for failed syncs
- Show detailed error messages or failure reasons on `FAILED` allocations.

### 10.6 Verify end-to-end Wave sync flow
- Full verification: create split transaction, approve, trigger sync from Sync Manager, poll status, and verify final `SYNCED` state.
