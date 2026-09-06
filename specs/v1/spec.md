# Family Accounting App - Technical Specification

## 1. Project Overview
This application is a private, internal web tool used to review, allocate, and process financial transactions from various intake sources. Transactions can be split and assigned to either personal/home expenses or specific business entities. Approved business transactions are subsequently synced to Wave (waveapps.com) via their API.

### 1.1 Target Audience & Access
- The application is for internal family use only.
- It will not be exposed publicly to the internet.
- Access requires a single-user login mechanism.

## 2. Technical Stack
- **Frontend:** Vue 3.5.x (typescript), Vue Router, Quasar 2.30.x, Pinia 3.x, Fetch API
- **Backend:** Python 3.14.x, FastAPI, Uvicorn, Pydantic, Alembic
- **Database:** SQLite
- **Wave API:** Wave GraphQL API

### 3.1 Tooling

- uv for managing python and dependencies, along with formatting and linting
- nvm for managing nodejs and dependencies
- prettier for formatting and linting the frontend
- pnpm for frontend package management
- pytest and httpx for backend testing
- vitest for frontend testing


## 3. Security & Authentication
- **Admin Credentials:** A single username and password must be configured via environment variables (e.g., `ADMIN_USERNAME`, `ADMIN_PASSWORD`).
- **Session Management:** The frontend will authenticate via a login screen, receiving a JWT (JSON Web Token) from the FastAPI backend.
- **Secure-by-Default Architecture:** All endpoints across the backend are protected by default regardless of router. Authentication is
  automatically enforced at the middleware layer (`AuthenticationMiddleware`). Unauthenticated requests to any non-exempt route are rejected with HTTP
  `401 Unauthorized`.
    - **Opt-in Anonymous Routes:** Public/unauthenticated access is strictly opt-in. Only `GET /api/health`, `POST /api/login`, and OpenAPI
  documentation endpoints (`/docs`, `/redoc`, `/openapi.json`) are permitted without credentials. Any newly added endpoint or router is secured
  automatically without requiring manual per-route annotations.
    - **User Identity Extraction:** Upon successful Bearer token verification, the middleware populates `request.state.current_user`. Routes that need
  the authenticated admin identity can inject it via the `get_current_user` dependency.
- **Global Configuration:** The application requires the following environment variables:
  - `JWT_SECRET_KEY` and `JWT_ACCESS_TOKEN_EXPIRE_MINUTES` for session management.
  - `WAVE_CLIENT_ID`, `WAVE_CLIENT_SECRET`, and `WAVE_REDIRECT_URI` for OAuth.
  - `RECEIPT_STORAGE_DIR`: Absolute path for durable file storage.
- **Wave API Credentials & Scopes:** Wave API tokens must be configurable *per company* and stored in the database. The OAuth flow must request the following scopes: `business:read`, `account:read`, `transaction:write`. To identify the company during the OAuth callback, the `company_id` must be passed as a signed JWT within the OAuth `state` parameter.

## 4. Data Model
The database will be SQLite. The implementation agent should use an ORM (like SQLAlchemy or SQLModel).

### 4.1 Company
Represents a business entity.
- `id`: UUID / Primary Key
- `name`: String
- `wave_business_id`: String
- `wave_access_token`: String
- `wave_refresh_token`: String
- `wave_token_expires_at`: DateTime
- `wave_equity_account_id`: String (**REQUIRED** for Wave's double-entry accounting. This represents the offset/anchor account like 'Bank' or 'Owner's Equity' used to balance expenses).

### 4.2 WaveCategory (Cached)
The app will fetch and cache the Chart of Accounts from Wave.
- `id`: UUID
- `company_id`: Foreign Key to Company
- `wave_account_id`: String
- `name`: String
- *Note:* Fetching should filter only for applicable Expense/Asset/Income accounts to prevent users from allocating to invalid system accounts.

### 4.3 Transaction
Represents the top-level transaction imported from a source or manually entered.
- `id`: UUID
- `source`: String (e.g., "manual", "amazon")
- `external_id`: String (Nullable. Unique identifier from the source system. A Database Unique Constraint must be placed on `(source, external_id)` to prevent duplicate imports).
- `date`: Date
- `description`: String
- `total_amount`: Decimal / Float (Can be negative to support refunds/income).
- `currency_code`: String (Defaults to the base currency).
- `receipt_file_path`: String
- `is_approved`: Boolean

### 4.4 Allocation (Splits)
A transaction must be able to be split.
- `id`: UUID
- `transaction_id`: Foreign Key to Transaction
- `amount`: Decimal / Float
- `is_personal`: Boolean
- `company_id`: Foreign Key to Company (Nullable)
- `wave_category_id`: Foreign Key to WaveCategory (Nullable)
- `sync_status`: Enum (`PENDING`, `SYNCED`, `FAILED`, `IGNORED`)
- `wave_transaction_id`: String (Nullable)

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
- **Auth:** `POST /api/login` (Returns JWT)
- **Companies:** CRUD operations for businesses and their configuration.
- **Wave OAuth:**
  - `GET /api/wave/oauth/authorize?company_id={id}`
  - `GET /api/wave/oauth/callback`
- **Wave Sync:** 
  - `POST /api/companies/{id}/sync-categories`
- **Transactions:** 
  - `GET /api/transactions` (Must implement **server-side pagination**).
  - `POST /api/transactions` (Manual entry with file upload support).
  - `PUT /api/transactions/{id}`
  - `PUT /api/transactions/{id}/approve`
- **Allocations:**
  - `PUT /api/transactions/{id}/allocations` (Updates split allocations. **MUST** return a 400 error if any existing allocation is `SYNCED`).
- **Receipts:**
  - `POST /api/transactions/{id}/receipt` (Uploads to `RECEIPT_STORAGE_DIR`).
  - `GET /api/receipts/{path}` 
- **Wave Push:**
  - `POST /api/sync/wave` (Must spawn a **background task** to process `PENDING` transactions to avoid 504 timeouts. Returns `202 Accepted`).

### 5.2 Abstraction Layer for Intake Sources
The backend must include an abstraction layer for parsing transaction sources, enforcing the extraction of `external_id` for duplicate prevention.

## 6. Frontend UI Requirements (Vue 3 + Quasar)

### 6.1 Layout
Persistent navigation drawer: Ledger, Manual Entry, Sync Manager, and Settings.

### 6.2 Ledger View
- **Data Table:** Displays top-level `Transactions` using server-side pagination.
- **Immutability:** Transactions with `SYNCED` allocations must be visually locked and strictly read-only to prevent drifting from Wave.

### 6.3 Allocation Editor (Transaction Splitter)
- UI allowing user to split a transaction into `Allocations`.
- Personal switch, Company select, Category select.
- Locked if any allocation has `sync_status == SYNCED`.

### 6.4 Sync Manager UI
- Dedicated view for Wave synchronization.
- Displays `PENDING` and `FAILED` business allocations.
- Actions: "Sync to Wave" and "Retry Failed".
- UI should poll the backend to display background sync progress.

### 6.5 Company Management & Settings UI
- CRUD interface for `Company` records.
- Configures `wave_equity_account_id` per company.
- Connect to Wave (OAuth flow) button and token status indicator.

## 7. Wave Integration Details

### 7.1 Sync Logic & Rules
- **Double-Entry Requirement:** Wave requires an offset account. The system will use the `Company.wave_equity_account_id` as the anchor account for all synced transactions.
- **Transaction Grouping:** Multiple allocations for the *same* company from a single parent `Transaction` must be grouped into a **single Wave transaction with multiple line items**.
- **Cross-Company Receipts:** If a receipt is attached to a parent transaction split across *two different* companies, the receipt must be uploaded separately to *each* company's Wave workspace.
- **Immutability & Refunds:** Synced transactions are read-only. Negative amounts represent refunds and must flip debits/credits in the Wave GraphQL mutation.

### 7.2 Implementation Steps for Wave API
1. Identify the Wave `businessId` and `wave_equity_account_id` from the `Company` record.
2. Verify token validity (`wave_token_expires_at`). If expired, use `wave_refresh_token` to get new tokens before proceeding.
3. Authenticate using the valid `wave_access_token`.
4. **Receipts (Multipart Note):** Wave's GraphQL API requires the Apollo GraphQL multipart request specification for file uploads. The developer must use `httpx` with `multipart/form-data` for the `documentCreate` mutation.
5. Execute transaction mutation using `wave_category_id` (line item) and `wave_equity_account_id` (anchor account). 
6. Wrap the local DB updates (`sync_status = SYNCED` and `wave_transaction_id`) in a local database transaction to prevent orphan states if the local commit fails.
