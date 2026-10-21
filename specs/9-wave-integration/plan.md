# Implementation Plan: Wave API Integration & Synchronization

This implementation plan defines the deliverables required to integrate automated Wave API synchronization into Wrangler alongside the existing CSV export workflow, as specified in [`specs/v3/2-wave-integration/spec.md`](file:///D:/src/personal/wrangler/specs/v3/2-wave-integration/spec.md).

Wrangler acts as an ingestion, deduplication, and entity attribution layer. It enforces that a parent transaction has at most one allocation per entity (at most one personal split and at most one split per company). Accounting category assignments occur exclusively prior to synchronization in the Sync & Export view, keeping all intake views completely clean.

The plan is divided into sequential, deliverable-driven phases with atomic implementation tasks in dependency order. Each task specifies concrete files, models, schemas, endpoints, or UI components along with automated test coverage adhering to development standards defined in [`AGENTS.md`](file:///D:/src/personal/wrangler/AGENTS.md).

---

## Phase 1: Database Schema, ORM Models & Entity Attribution Guard

*Goal:* Update database models for Wave credentials, account caching, and transaction synchronization tracking; generate the Alembic migration; and enforce the single-allocation-per-entity attribution boundary.

### 1.1 Update `Company` and `Allocation` Models and Create `WaveCategory` Model
- In [`api/src/models/company.py`](file:///D:/src/personal/wrangler/api/src/models/company.py):
  - Add Wave connection fields to `Company(Base)`:
    - `wave_api_token: Mapped[str | None] = mapped_column(String, nullable=True)`
    - `wave_business_id: Mapped[str | None] = mapped_column(String, nullable=True)`
    - `wave_business_name: Mapped[str | None] = mapped_column(String, nullable=True)`
    - `wave_equity_account_id: Mapped[str | None] = mapped_column(String, nullable=True)`
  - Add relationship `categories: Mapped[list[WaveCategory]] = relationship("WaveCategory", back_populates="company", cascade="all, delete-orphan")`.
- Create [`api/src/models/wave_category.py`](file:///D:/src/personal/wrangler/api/src/models/wave_category.py):
  - Define `WaveCategory(Base)` mapped to table `wave_categories`:
    - `id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)`
    - `company_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("companies.id", ondelete="CASCADE"), nullable=False)`
    - `wave_account_id: Mapped[str] = mapped_column(String, nullable=False)`
    - `name: Mapped[str] = mapped_column(String, nullable=False)`
    - `account_type: Mapped[str] = mapped_column(String, nullable=False)`
    - `account_subtype: Mapped[str | None] = mapped_column(String, nullable=True)`
    - `is_uncategorized: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)`
    - Table constraint: `UniqueConstraint("company_id", "wave_account_id", name="uq_wave_categories_company_account")`
    - Relationship `company: Mapped[Company] = relationship("Company", back_populates="categories")`.
- In [`api/src/models/allocation.py`](file:///D:/src/personal/wrangler/api/src/models/allocation.py):
  - Add Wave tracking columns to `Allocation(Base)`:
    - `wave_category_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("wave_categories.id", ondelete="SET NULL"), nullable=True)`
    - `wave_transaction_id: Mapped[str | None] = mapped_column(String, nullable=True)`
  - Add relationship `wave_category: Mapped[WaveCategory | None] = relationship("WaveCategory")`.

### 1.2 Generate and Apply Alembic Migration for Wave Integration
- In [`api/alembic/env.py`](file:///D:/src/personal/wrangler/api/alembic/env.py):
  - Ensure `WaveCategory` is imported so its metadata is registered with Alembic.
- Create migration script in [`api/alembic/versions/`](file:///D:/src/personal/wrangler/api/alembic/versions/) (revising current head `d4a8e2b1c3f5`):
  - In `upgrade()` using SQLite batch operations:
    - Alter table `companies`: add nullable columns `wave_api_token` (String), `wave_business_id` (String), `wave_business_name` (String), and `wave_equity_account_id` (String).
    - Create table `wave_categories` with primary key `id`, foreign key `company_id` referencing `companies.id` (`ondelete="CASCADE"`), `wave_account_id`, `name`, `account_type`, `account_subtype`, `is_uncategorized`, and unique constraint `uq_wave_categories_company_account`.
    - Alter table `allocations`: add nullable column `wave_category_id` (Uuid, FK referencing `wave_categories.id`, `ondelete="SET NULL"`) and `wave_transaction_id` (String).
  - In `downgrade()`:
    - Drop `wave_category_id` and `wave_transaction_id` from `allocations`.
    - Drop table `wave_categories`.
    - Drop `wave_api_token`, `wave_business_id`, `wave_business_name`, and `wave_equity_account_id` from `companies`.
- Create [`api/tests/test_wave_models.py`](file:///D:/src/personal/wrangler/api/tests/test_wave_models.py):
  - Test persistence of `Company` with Wave fields.
  - Test `WaveCategory` persistence and foreign key constraint referencing `Company`.
  - Test cascade deletion: deleting a `Company` deletes its associated `WaveCategory` rows.
  - Test unique constraint `(company_id, wave_account_id)` preventing duplicate accounts for the same company.
  - Test `Allocation` referencing `WaveCategory`, and verify that deleting a category sets `wave_category_id = None` on the allocation (`SET NULL`).

### 1.3 Enforce Entity Attribution Constraint (1 Allocation per Entity)
- In [`api/src/routers/transactions.py`](file:///D:/src/personal/wrangler/api/src/routers/transactions.py):
  - In `_validate_and_apply_allocations`:
    - Validate that at most **one** allocation has `is_personal == True`.
    - Validate that for all allocations with `is_personal == False`, every `company_id` is unique (`len(business_company_ids) == len(set(business_company_ids))`).
    - If multiple personal allocations or duplicate company allocations are present, raise `HTTPException(status_code=400, detail="A transaction can have at most one allocation per company/entity. Manage sub-categories directly in Wave.")`.
    - Update the split validation logic so multi-entity transactions can allocate between personal and one or more distinct companies.
  - In `create_transaction` (`POST /api/transactions`):
    - Enforce the same uniqueness rule across business allocations (`len(company_ids) == len(set(company_ids))`).
- Create [`api/tests/test_entity_attribution.py`](file:///D:/src/personal/wrangler/api/tests/test_entity_attribution.py):
  - Test that updating a transaction with two allocations for the same `company_id` returns HTTP 400 with the exact error message.
  - Test that updating a transaction with two personal allocations returns HTTP 400.
  - Test that a transaction with one personal allocation and one business allocation is allowed.
  - Test that a transaction with splits across two distinct companies (e.g. Company A and Company B) is allowed.

---

## Phase 2: Wave GraphQL Service Client

*Goal:* Implement a dedicated, typed asynchronous GraphQL client using `httpx.AsyncClient` targeting Wave's public API for token verification, Chart of Accounts inspection, and double-entry transaction creation.

### 2.1 Implement Wave Service Data Schemas and GraphQL Client
- Create [`api/src/services/wave/client.py`](file:///D:/src/personal/wrangler/api/src/services/wave/client.py):
  - Define Wave GraphQL endpoint constant: `WAVE_GRAPHQL_URL = "https://gql.waveapps.com/graphql/public"`.
  - Define internal data models or dataclasses:
    - `WaveBusiness`: `id: str`, `name: str`, `is_personal: bool`.
    - `WaveAccount`: `id: str`, `name: str`, `type: str`, `subtype: str | None = None`, `is_uncategorized: bool = False`.
    - `WaveAccountsResult`: `anchor_accounts: list[WaveAccount]`, `expense_categories: list[WaveAccount]`.
  - Define custom exception classes:
    - `WaveAuthError(Exception)`: for invalid or expired tokens (maps to HTTP 401).
    - `WaveApiError(Exception)`: for upstream Wave errors or network failures (maps to HTTP 502).
  - Implement `WaveClient`:
    - `async def get_user_businesses(token: str) -> list[WaveBusiness]`:
      - Execute `query GetUserBusinesses` with `Authorization: Bearer <token>`.
      - Translate 401 response or GraphQL auth errors to `WaveAuthError`.
      - Translate connection errors or upstream 5xx responses to `WaveApiError`.
      - Extract and return list of businesses (`id`, `name`, `is_personal`).
    - `async def get_business_accounts(token: str, business_id: str) -> WaveAccountsResult`:
      - Execute `query GetBusinessAccounts($businessId: ID!)`.
      - Filter accounts: exclude any account with `isArchived == True`.
      - Filter `anchor_accounts`: accounts where `type.value in ("ASSET", "LIABILITY", "EQUITY")` and `subtype.value in ("CASH_AND_BANK", "CREDIT_CARD", "MONEY_MARKET", "OWNERS_EQUITY")`.
      - Filter `expense_categories`: accounts where `type.value == "EXPENSE"`. Flag account with `is_uncategorized = True` when `subtype.value == "UNCATEGORIZED_EXPENSE"`.
      - Return `WaveAccountsResult(anchor_accounts=..., expense_categories=...)`.
    - `async def create_money_transaction(...) -> str`:
      - Parameters: `token: str`, `business_id: str`, `external_id: str`, `date: str`, `description: str`, `amount: Decimal`, `equity_account_id: str`, `category_account_id: str`.
      - Format payload:
        - If `amount > 0`: `anchor` has `accountId: equity_account_id`, `amount: float(amount)`, `direction: "WITHDRAWAL"`; `lineItems` has `accountId: category_account_id`, `amount: float(amount)`, `balance: "INCREASE"`.
        - If `amount < 0`: `anchor` has `accountId: equity_account_id`, `amount: float(abs(amount))`, `direction: "DEPOSIT"`; `lineItems` has `accountId: category_account_id`, `amount: float(abs(amount))`, `balance: "DECREASE"`.
      - Execute mutation `mutation CreateMoneyTransaction($input: MoneyTransactionCreateInput!)`.
      - If `didSucceed` is False or `inputErrors` is non-empty: raise `WaveApiError` with joined input error messages.
      - Return `transaction.id`.

### 2.2 Wave GraphQL Client Unit Test Suite
- Create [`api/tests/test_wave_client.py`](file:///D:/src/personal/wrangler/api/tests/test_wave_client.py):
  - Test `get_user_businesses`:
    - Successful response parses business ID, name, and `isPersonal`.
    - HTTP 401 or GraphQL authentication error raises `WaveAuthError`.
    - Network timeout or connection drop raises `WaveApiError`.
  - Test `get_business_accounts`:
    - Archived accounts are excluded.
    - Anchor account filtering matches Bank, Credit Card, and Owner's Equity accounts.
    - Expense categories match `type.value == "EXPENSE"`.
    - System `UNCATEGORIZED_EXPENSE` is flagged with `is_uncategorized = True`.
  - Test `create_money_transaction`:
    - Standard positive expense maps to `WITHDRAWAL` and `INCREASE`.
    - Negative refund/credit maps to `DEPOSIT` and `DECREASE` with absolute amounts.
    - Idempotency key `externalId` is correctly passed.
    - Wave GraphQL `inputErrors` responses raise `WaveApiError` containing the error details.

---

## Phase 3: Wave Configuration & Category API Endpoints

*Goal:* Expose REST endpoints to test Full Access Tokens, fetch candidate accounts for a business, save Wave connection credentials on companies, and sync/list cached expense categories.

### 3.1 Define Pydantic Schemas for Wave Configuration & Categories
- In [`api/src/schemas/company.py`](file:///D:/src/personal/wrangler/api/src/schemas/company.py):
  - Add Wave fields to `CompanyResponse`:
    - `wave_business_id: str | None = None`
    - `wave_business_name: str | None = None`
    - `wave_equity_account_id: str | None = None`
    - `is_wave_connected: bool = False`
  - Add `WaveTestTokenRequest`: `token: str = Field(..., min_length=1)`
  - Add `WaveBusinessAccountsRequest`: `token: str = Field(..., min_length=1)`, `business_id: str = Field(..., min_length=1)`
  - Add `WaveBusinessItem`: `id: str`, `name: str`, `is_personal: bool`
  - Add `WaveAccountItem`: `id: str`, `name: str`, `type: str`, `subtype: str | None = None`, `is_uncategorized: bool = False`
  - Add `WaveBusinessAccountsResponse`: `anchor_accounts: list[WaveAccountItem]`, `expense_categories: list[WaveAccountItem]`
  - Add `WaveConnectRequest`: `token: str = Field(..., min_length=1)`, `business_id: str = Field(..., min_length=1)`, `business_name: str = Field(..., min_length=1)`, `equity_account_id: str = Field(..., min_length=1)`
  - Add `WaveCategoryResponse`:
    - `id: uuid.UUID`
    - `company_id: uuid.UUID`
    - `wave_account_id: str`
    - `name: str`
    - `account_type: str`
    - `account_subtype: str | None = None`
    - `is_uncategorized: bool = False`
    - `model_config = ConfigDict(from_attributes=True)`

### 3.2 Implement Company Wave Endpoints in Companies Router
- In [`api/src/routers/companies.py`](file:///D:/src/personal/wrangler/api/src/routers/companies.py):
  - Update `_get_company_metrics` and company serialization to compute `is_wave_connected`:
    - `is_wave_connected = bool(company.wave_api_token and company.wave_business_id and company.wave_equity_account_id)`
  - Add `POST /api/companies/wave/test-token`:
    - Call `WaveClient.get_user_businesses(payload.token)`.
    - Return `list[WaveBusinessItem]`.
    - Map `WaveAuthError` to HTTP 401; map `WaveApiError` to HTTP 502.
  - Add `POST /api/companies/wave/business-accounts`:
    - Call `WaveClient.get_business_accounts(payload.token, payload.business_id)`.
    - Return `WaveBusinessAccountsResponse`.
    - Map `WaveAuthError` to HTTP 401; map `WaveApiError` to HTTP 502.
  - Add `POST /api/companies/{id}/wave/connect`:
    - Verify company exists (`404 Not Found`).
    - Save `wave_api_token`, `wave_business_id`, `wave_business_name`, `wave_equity_account_id` on the company record.
    - Query Wave Chart of Accounts for `payload.business_id` using `WaveClient.get_business_accounts`.
    - Upsert active expense accounts into `wave_categories` for this `company_id` (insert new, update existing names/subtypes).
    - Commit and return updated `CompanyResponse`.
  - Add `POST /api/companies/{id}/wave/sync-categories`:
    - Verify company exists and is Wave-connected (`400 Bad Request` if unlinked).
    - Query Wave Chart of Accounts for `company.wave_business_id`.
    - Synchronize `wave_categories`: upsert active expense accounts, remove categories that no longer exist in Wave.
    - Return updated list of `WaveCategoryResponse` sorted with `is_uncategorized` first, then alphabetically by `name`.
  - Add `GET /api/companies/{id}/wave/categories`:
    - Verify company exists.
    - Return cached `WaveCategory` rows for `company_id` ordered `is_uncategorized.desc()`, `name.asc()`.
  - Add `DELETE /api/companies/{id}/wave`:
    - Clear `wave_api_token`, `wave_business_id`, `wave_business_name`, and `wave_equity_account_id` on the company.
    - Delete associated `wave_categories` records.
    - Commit and return updated `CompanyResponse`.

### 3.3 Company Wave Configuration API Test Suite
- Create [`api/tests/test_company_wave_config.py`](file:///D:/src/personal/wrangler/api/tests/test_company_wave_config.py):
  - Test `POST /api/companies/wave/test-token`:
    - Valid token returns business list.
    - Invalid token returns HTTP 401.
    - Wave unreachable returns HTTP 502.
  - Test `POST /api/companies/wave/business-accounts`:
    - Returns anchor candidate accounts and expense categories.
  - Test `POST /api/companies/{id}/wave/connect`:
    - Updates company Wave fields, fetches accounts, and populates `wave_categories`.
    - Company response reflects `is_wave_connected == True`.
  - Test `POST /api/companies/{id}/wave/sync-categories`:
    - Synchronizes new accounts and removes deleted accounts.
    - Calling on an unlinked company returns HTTP 400.
  - Test `GET /api/companies/{id}/wave/categories`:
    - Returns cached categories with `is_uncategorized` entry sorted first.
  - Test `DELETE /api/companies/{id}/wave`:
    - Clears credentials, deletes cached categories, and resets `is_wave_connected` to False.

---

## Phase 4: Wave Synchronization & Allocation Category Endpoints

*Goal:* Implement inline allocation category assignment and the batch synchronization endpoint with atomic per-transaction commits, receipt memo formatting, and idempotency safeguards.

### 4.1 Update Allocation Schemas & Implement Inline Category Assignment Endpoint
- In [`api/src/schemas/allocation.py`](file:///D:/src/personal/wrangler/api/src/schemas/allocation.py):
  - Add `wave_category_id: uuid.UUID | None = None` and `wave_transaction_id: str | None = None` to `AllocationResponse`, `AllocationItem`, and `AllocationCreateItem`.
  - Add `AllocationCategoryUpdateRequest(BaseModel)`:
    - `wave_category_id: uuid.UUID | None = None`
- In [`api/src/routers/allocations.py`](file:///D:/src/personal/wrangler/api/src/routers/allocations.py):
  - Implement `PATCH /api/allocations/{id}/category`:
    - Query allocation by ID (`404 Not Found` if missing).
    - If `allocation.is_locked`: raise `HTTPException(400, "Cannot change category on a locked allocation")`.
    - If `payload.wave_category_id` is provided:
      - Query `WaveCategory` by ID.
      - If missing or `category.company_id != allocation.company_id`: raise `HTTPException(400, "Invalid category for this company")`.
    - Update `allocation.wave_category_id = payload.wave_category_id`.
    - Commit and return updated `AllocationResponse`.

### 4.2 Implement `POST /api/companies/{id}/sync-wave` Batch Sync Endpoint
- In [`api/src/schemas/company.py`](file:///D:/src/personal/wrangler/api/src/schemas/company.py):
  - Add `WaveSyncBatchRequest(BaseModel)`:
    - `allocation_ids: list[uuid.UUID] | None = None`
  - Add `WaveSyncErrorItem(BaseModel)`:
    - `allocation_id: uuid.UUID`
    - `description: str`
    - `error: str`
  - Add `WaveSyncResponse(BaseModel)`:
    - `total_processed: int`
    - `synced_count: int`
    - `failed_count: int`
    - `errors: list[WaveSyncErrorItem] = Field(default_factory=list)`
- In [`api/src/routers/companies.py`](file:///D:/src/personal/wrangler/api/src/routers/companies.py):
  - Implement `POST /api/companies/{id}/sync-wave`:
    - Verify company exists and `is_wave_connected` is True (`400 Bad Request` if unlinked).
    - Retrieve fallback uncategorized category: find `WaveCategory` where `company_id == company.id` and `is_uncategorized.is_(True)`.
    - Query target allocations:
      - Filter by `Allocation.company_id == company.id`, `Allocation.is_personal.is_(False)`, and `Allocation.is_locked.is_(False)`.
      - If `payload.allocation_ids` is provided, filter by `Allocation.id.in_(payload.allocation_ids)`.
      - Join and eager load `Allocation.transaction` and `Allocation.wave_category`.
      - Order by `Transaction.date.asc()`, `Transaction.id.asc()`, `Allocation.id.asc()`.
    - Pre-flight validation:
      - Any allocation where `wave_transaction_id is not None`: raise `HTTPException(400, f"Allocation {alloc.id} was already synced to Wave")`.
      - Check each allocation has a category: if `alloc.wave_category_id is None` and no fallback uncategorized category exists, raise `HTTPException(400, f"Allocation {alloc.id} requires a category before syncing")`.
    - Sequential batch execution with atomic per-allocation commit:
      - For each allocation:
        - Determine target category account ID: `alloc.wave_category.wave_account_id` if present, else fallback category's `wave_account_id`.
        - Memo annotation: if `alloc.transaction.receipt_file_path`:
          - Extract sanitized filename via `os.path.basename(alloc.transaction.receipt_file_path)`.
          - Description = `f"{alloc.transaction.description} [Receipt: {sanitized_filename}]"`.
          - Otherwise Description = `alloc.transaction.description`.
        - Try:
          - Call `WaveClient.create_money_transaction(...)` with `external_id = f"wrangler_{alloc.id}"`.
          - Update allocation: `alloc.is_locked = True`, `alloc.wave_transaction_id = wave_tx_id`.
          - If `alloc.wave_category_id is None` (used fallback): set `alloc.wave_category_id = fallback_category.id`.
          - `db.commit()` immediately for this allocation.
          - Increment `synced_count`.
        - Except `WaveApiError` or upstream exception as exc:
          - `db.rollback()` for this allocation.
          - Append `WaveSyncErrorItem(allocation_id=alloc.id, description=alloc.transaction.description, error=str(exc))` to `errors`.
          - Increment `failed_count`.
    - Return `WaveSyncResponse(total_processed=len(allocations), synced_count=synced_count, failed_count=failed_count, errors=errors)`.

### 4.3 Wave Sync API Test Suite
- Create [`api/tests/test_wave_sync_api.py`](file:///D:/src/personal/wrangler/api/tests/test_wave_sync_api.py):
  - Test `PATCH /api/allocations/{id}/category`:
    - Successfully assigns category to unlocked allocation.
    - Locked allocation returns HTTP 400.
    - Category belonging to a different company returns HTTP 400.
  - Test `POST /api/companies/{id}/sync-wave`:
    - Unlinked company returns HTTP 400.
    - Syncing an allocation that already has `wave_transaction_id` returns HTTP 400 with duplicate safeguard warning.
    - Allocation missing category falls back to `UNCATEGORIZED_EXPENSE` category if present, or returns HTTP 400 if no fallback exists.
    - Successful sync locks the allocation and persists `wave_transaction_id`.
    - Receipt memo formatting verifies `[Receipt: filename.ext]` appended when receipt is attached.
    - Resilient partial sync test: when 1 of 3 allocations triggers an upstream Wave error, the other 2 allocations remain locked and committed with Wave IDs, while the failed allocation remains unlocked and appears in `errors`.

---

## Phase 5: Frontend TypeScript Types & Pinia Store Integration

*Goal:* Update TypeScript interfaces and Pinia stores to support Wave connection management, Chart of Accounts caching, inline allocation categorization, and batch Wave synchronization.

### 5.1 Define Wave and Allocation TypeScript Types
- In [`web/src/types/company.ts`](file:///D:/src/personal/wrangler/web/src/types/company.ts):
  - Add Wave connection fields to `Company`:
    - `wave_business_id?: string | null`
    - `wave_business_name?: string | null`
    - `wave_equity_account_id?: string | null`
    - `is_wave_connected?: boolean`
- Create [`web/src/types/wave.ts`](file:///D:/src/personal/wrangler/web/src/types/wave.ts):
  - Define `WaveBusiness`: `id: string`, `name: string`, `is_personal: boolean`.
  - Define `WaveAccount`: `id: string`, `name: string`, `type: string`, `subtype?: string | null`, `is_uncategorized?: boolean`.
  - Define `WaveBusinessAccountsResponse`: `anchor_accounts: WaveAccount[]`, `expense_categories: WaveAccount[]`.
  - Define `WaveConnectPayload`: `token: string`, `business_id: string`, `business_name: string`, `equity_account_id: string`.
  - Define `WaveCategory`: `id: string`, `company_id: string`, `wave_account_id: string`, `name: string`, `account_type: string`, `account_subtype?: string | null`, `is_uncategorized: boolean`.
  - Define `WaveSyncErrorItem`: `allocation_id: string`, `description: string`, `error: string`.
  - Define `WaveSyncResponse`: `total_processed: number`, `synced_count: number`, `failed_count: number`, `errors: WaveSyncErrorItem[]`.
- In [`web/src/types/transaction.ts`](file:///D:/src/personal/wrangler/web/src/types/transaction.ts):
  - Add `wave_category_id?: string | null` and `wave_transaction_id?: string | null` to `Allocation`, `AllocationCreateItem`, and `AllocationUpdateItem`.

### 5.2 Implement Wave Actions in Company and Transaction Pinia Stores
- In [`web/src/stores/companies.ts`](file:///D:/src/personal/wrangler/web/src/stores/companies.ts):
  - Implement Wave configuration store actions:
    - `async function testWaveToken(token: string): Promise<WaveBusiness[]>`: POST `/api/companies/wave/test-token`.
    - `async function fetchBusinessAccounts(token: string, businessId: string): Promise<WaveBusinessAccountsResponse>`: POST `/api/companies/wave/business-accounts`.
    - `async function connectWave(companyId: string, payload: WaveConnectPayload): Promise<Company>`: POST `/api/companies/${companyId}/wave/connect`. Updates company in `companies` array.
    - `async function disconnectWave(companyId: string): Promise<Company>`: DELETE `/api/companies/${companyId}/wave`. Updates company in `companies` array.
    - `async function fetchWaveCategories(companyId: string): Promise<WaveCategory[]>`: GET `/api/companies/${companyId}/wave/categories`.
    - `async function syncWaveCategories(companyId: string): Promise<WaveCategory[]>`: POST `/api/companies/${companyId}/wave/sync-categories`.
    - `async function syncCompanyToWave(companyId: string, allocationIds?: string[]): Promise<WaveSyncResponse>`: POST `/api/companies/${companyId}/sync-wave`.
- In [`web/src/stores/transactions.ts`](file:///D:/src/personal/wrangler/web/src/stores/transactions.ts):
  - Implement inline category assignment:
    - `async function updateAllocationCategory(allocationId: string, waveCategoryId: string | null): Promise<Allocation>`:
      - PATCH `/api/allocations/${allocationId}/category` with `{ wave_category_id: waveCategoryId }`.
      - Update matching allocation across cached transactions in `transactions.value`.
      - Return updated allocation.

### 5.3 Pinia Wave Stores Unit Test Suite
- Create [`web/tests/waveStores.test.ts`](file:///D:/src/personal/wrangler/web/tests/waveStores.test.ts):
  - Test `testWaveToken` POST request dispatch and business list return.
  - Test `fetchBusinessAccounts` POST request dispatch and accounts response.
  - Test `connectWave` updating the target company record with `is_wave_connected: true`.
  - Test `disconnectWave` updating company with credentials cleared.
  - Test `fetchWaveCategories` and `syncWaveCategories` caching categories.
  - Test `syncCompanyToWave` dispatching target allocation IDs and returning `WaveSyncResponse`.
  - Test `updateAllocationCategory` dispatching category update and locally updating state in `transactionStore`.

---

## Phase 6: Frontend UI Components & Adaptive Sync View

*Goal:* Update company configuration dialogs with Wave credential and account controls, provide adaptive Wave synchronization and inline category assignment in the Sync & Export view, and preserve clean zero-category intake across Ledger, Manual Entry, and Staging views.

### 6.1 Update `CompanyFormDialog.vue` for Wave Integration
- In [`web/src/components/CompanyFormDialog.vue`](file:///D:/src/personal/wrangler/web/src/components/CompanyFormDialog.vue):
  - Add Wave Integration Card / Expansion section:
    - Display connection badge: **"Connected to Wave"** (green chip) or **"CSV Export Only"** (grey chip).
    - Password-masked input field for Wave Full Access Token with a **"Test & Fetch Businesses"** button.
    - On token verification:
      - Display **Wave Business** selectable dropdown.
      - On business selection: automatically fetch business accounts and populate **Anchor Account** dropdown with eligible Cash, Bank, and Owner's Equity accounts.
    - For connected companies:
      - Display linked business name and anchor account name.
      - **"Sync Categories"** button displaying total cached categories.
      - **"Disconnect Wave"** button prompting confirmation dialog before unlinking.
    - Integrate with form submission: connect Wave credentials when creating or updating company.

### 6.2 Update `ExportManagerView.vue` and Helpers for Adaptive Wave Synchronization
- In [`web/src/views/exportManager.ts`](file:///D:/src/personal/wrangler/web/src/views/exportManager.ts):
  - Update `ExportAllocationRow` to include `wave_category_id: string | null` and `wave_transaction_id: string | null`.
  - Update `extractCompanyAllocationRows` to populate `wave_category_id` and `wave_transaction_id`.
  - Add helper functions:
    - `isWaveAlreadySynced(row: ExportAllocationRow): boolean`: returns `Boolean(!row.is_locked && row.wave_transaction_id)`.
    - `canSyncRowToWave(row: ExportAllocationRow): boolean`: returns `Boolean(!row.is_locked && !row.wave_transaction_id && row.wave_category_id)`.
- In [`web/src/views/ExportManagerView.vue`](file:///D:/src/personal/wrangler/web/src/views/ExportManagerView.vue):
  - Detect whether `selectedCompany.is_wave_connected` is True.
  - **Action Bar (Wave Mode):**
    - Primary button: **"Sync to Wave"** (icon `cloud_upload`, disabled if no rows selected or selected rows lack categories).
    - Secondary dropdown/split action: **"Export CSV"** backup action.
    - **"Sync Categories"** quick action icon next to company selector to refresh cached categories from Wave on demand.
  - **Allocations Table (Wave Mode):**
    - Multi-select row checkboxes with "Select All" toggle in header. Checkbox disabled for rows where `isWaveAlreadySynced(row)` is true.
    - **Category Column:**
      - Inline `QSelect` dropdown on every row populated with cached categories.
      - Highlights system `"Uncategorized Expense"` account.
      - Changing category triggers `updateAllocationCategory` immediately with a brief saved transition.
      - If category is empty, render warning chip: `"Category Required"`.
    - **Lock / Sync Status Column:**
      - `!row.is_locked && !row.wave_transaction_id`: `"Unlocked"` badge.
      - `row.is_locked && row.wave_transaction_id`: `"Synced to Wave"` (green chip with checkmark).
      - `!row.is_locked && row.wave_transaction_id`: `"Already in Wave"` (warning chip) with tooltip: *"Previously pushed to Wave. Wave does not allow updates via API; adjust in Wave directly."*
    - **Receipt Column:** Button to open stored receipt in a new tab.
  - **Sync Execution & Feedback:**
    - Confirmation dialog: *"Push {count} transactions totaling {total} to Wave?"*.
    - Progress spinner dialog during sync execution.
    - Completion summary dialog:
      - Green banner displaying `synced_count` successful transactions.
      - Error list displaying any failed transactions with error messages.
    - Automatically refresh table rows and company metrics on finish.

### 6.3 Clean Intake Verification in Ledger, Manual Entry, and Staging Views
- In [`web/src/views/LedgerView.vue`](file:///D:/src/personal/wrangler/web/src/views/LedgerView.vue):
  - Verify transactions and allocations display lock status and Wave status chips without showing category dropdowns.
- In [`web/src/views/ManualEntryView.vue`](file:///D:/src/personal/wrangler/web/src/views/ManualEntryView.vue):
  - Verify manual intake remains 100% free of accounting category inputs.
- In [`web/src/views/ImportView.vue`](file:///D:/src/personal/wrangler/web/src/views/ImportView.vue):
  - Verify staging area allocations only assign entity companies, keeping category assignments deferred to the Sync & Export view.

### 6.4 Frontend Component Test Suite for Wave Integration
- Create [`web/tests/waveUi.test.ts`](file:///D:/src/personal/wrangler/web/tests/waveUi.test.ts):
  - Test `CompanyFormDialog.vue`:
    - Entering a token and clicking "Test & Fetch Businesses" populates the business select dropdown.
    - Selecting a business triggers accounts fetch and populates the anchor account select dropdown.
    - Connected company shows "Connected to Wave" status badge and displays "Sync Categories" and "Disconnect Wave" buttons.
  - Test `ExportManagerView.vue`:
    - Adaptive mode: selecting a Wave-connected company renders "Sync to Wave" primary button, row checkboxes, and category dropdown column.
    - Unlinked company renders standard "Export CSV" button without category dropdown column.
    - Changing row category triggers `updateAllocationCategory`.
    - Already-synced row displays "Already in Wave" badge and disables row checkbox.
    - Clicking "Sync to Wave" opens confirmation dialog and summary dialog upon completion.
