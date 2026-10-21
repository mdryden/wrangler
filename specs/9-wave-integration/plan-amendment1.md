# Implementation Plan: Amendment 1 - Due to Owner Anchor Classification & Column Renaming

This implementation plan defines the deliverables required to support **Due to You and Other Business Owners** accounts and universally rename equity account references to anchor account references, as specified in [`specs/v3/2-wave-integration/spec-amendment1.md`](file:///D:/src/personal/wrangler/specs/v3/2-wave-integration/spec-amendment1.md).

Wrangler acts as an ingestion, deduplication, and entity attribution layer. In Wave accounting, personal expenses incurred on behalf of a company that must be reimbursed are tracked on the balance sheet under Liabilities & Credit Cards—specifically within the **"Due to You and Other Business Owners"** account ledger (`DUE_TO_YOU_AND_OTHER_OWNERS`). This amendment updates the candidate anchor account filtering rules, performs database and model migrations to rename `wave_equity_account_id` to `wave_anchor_account_id`, adjusts API request/response schemas with backward compatibility, and refines frontend labels and types.

The plan is divided into sequential, deliverable-driven phases with atomic implementation tasks in dependency order. Each task specifies concrete files, models, schemas, endpoints, or UI components along with automated test coverage adhering to development standards defined in [`AGENTS.md`](file:///D:/src/personal/wrangler/AGENTS.md).

---

## Phase 1: Database Migration & SQLAlchemy Model

*Goal:* Update the database schema to rename `wave_equity_account_id` to `wave_anchor_account_id` via a reversible Alembic migration and update the SQLAlchemy `Company` ORM model.

### 1.1 Create Alembic Migration for Anchor Column Renaming
- Create migration script in [`api/alembic/versions/`](file:///D:/src/personal/wrangler/api/alembic/versions/) revising current head `f2a7b1c9d8e3`:
  - **Down Revision:** `f2a7b1c9d8e3` (`add wave integration tables and columns`)
  - In `upgrade()` using Alembic SQLite batch operations:
    ```python
    with op.batch_alter_table("companies", schema=None) as batch_op:
        batch_op.alter_column(
            "wave_equity_account_id",
            new_column_name="wave_anchor_account_id",
            existing_type=sa.String(),
            nullable=True,
        )
    ```
  - In `downgrade()` using Alembic SQLite batch operations:
    ```python
    with op.batch_alter_table("companies", schema=None) as batch_op:
        batch_op.alter_column(
            "wave_anchor_account_id",
            new_column_name="wave_equity_account_id",
            existing_type=sa.String(),
            nullable=True,
        )
    ```
- Update migration and schema tests in [`api/tests/test_migrations.py`](file:///D:/src/personal/wrangler/api/tests/test_migrations.py) and [`api/tests/test_schema.py`](file:///D:/src/personal/wrangler/api/tests/test_schema.py):
  - In `test_migrations.py`: assert `wave_anchor_account_id` is present in `companies` columns at head revision and `wave_equity_account_id` is absent.
  - In `test_schema.py`: assert `wave_anchor_account_id` is present in `companies` columns and `wave_equity_account_id` is absent.

### 1.2 Update `Company` SQLAlchemy Model & Model Persistence Tests
- In [`api/src/models/company.py`](file:///D:/src/personal/wrangler/api/src/models/company.py):
  - In class [`Company`](file:///D:/src/personal/wrangler/api/src/models/company.py#L15-L26):
    - Replace attribute:
      ```python
      wave_equity_account_id: Mapped[str | None] = mapped_column(String, nullable=True)
      ```
      with:
      ```python
      wave_anchor_account_id: Mapped[str | None] = mapped_column(String, nullable=True)
      ```
- Update model persistence tests in [`api/tests/test_wave_models.py`](file:///D:/src/personal/wrangler/api/tests/test_wave_models.py):
  - Update `test_company_persistence_with_wave_fields` to instantiate [`Company`](file:///D:/src/personal/wrangler/api/src/models/company.py#L15-L26) with `wave_anchor_account_id="QWNjb3VudDoxMjM="` and assert `company.wave_anchor_account_id == "QWNjb3VudDoxMjM="`.

---

## Phase 2: Wave GraphQL Service Client

*Goal:* Update `WaveClient` to include the `DUE_TO_YOU_AND_OTHER_OWNERS` liability subtype in candidate anchor accounts while excluding `OWNERS_EQUITY`, and rename transaction creation parameters to use anchor account semantics.

### 2.1 Update Candidate Anchor Account Filtering in `WaveClient`
- In [`api/src/services/wave/client.py`](file:///D:/src/personal/wrangler/api/src/services/wave/client.py):
  - In `get_business_accounts` method of [`WaveClient`](file:///D:/src/personal/wrangler/api/src/services/wave/client.py#L103-L274):
    - Update candidate anchor subtypes and types:
      ```python
      valid_anchor_subtypes = {
          "DUE_TO_YOU_AND_OTHER_OWNERS",
          "CASH_AND_BANK",
          "CREDIT_CARD",
          "MONEY_MARKET",
      }
      valid_anchor_types = {"ASSET", "LIABILITY"}
      ```
    - Ensure accounts where `subtype.value == "OWNERS_EQUITY"` or `isArchived == True` are excluded from `anchor_accounts`.
- Update [`api/tests/test_wave_client.py`](file:///D:/src/personal/wrangler/api/tests/test_wave_client.py):
  - In `test_get_business_accounts_success`:
    - Configure mock account list containing `DUE_TO_YOU_AND_OTHER_OWNERS` (Liability), `OWNERS_EQUITY` (Equity), and `CASH_AND_BANK` (Asset).
    - Assert `DUE_TO_YOU_AND_OTHER_OWNERS` and `CASH_AND_BANK` are returned in `anchor_accounts`.
    - Assert `OWNERS_EQUITY` is excluded from `anchor_accounts`.

### 2.2 Update Parameter & Mutation Payload in `WaveClient.create_money_transaction`
- In [`api/src/services/wave/client.py`](file:///D:/src/personal/wrangler/api/src/services/wave/client.py):
  - In `create_money_transaction` method of [`WaveClient`](file:///D:/src/personal/wrangler/api/src/services/wave/client.py#L221-L274):
    - Rename parameter `equity_account_id: str` to `anchor_account_id: str`.
    - Update input payload dictionary:
      ```python
      "anchor": {
          "accountId": anchor_account_id,
          "amount": float_amt,
          "direction": anchor_direction,
      }
      ```
    - Preserve double-entry directional balance logic:
      - Positive amount: `anchor_direction = "WITHDRAWAL"`, line item `balance = "INCREASE"` (credits/increases liability debt owed to owner, debits expense category).
      - Negative amount: `anchor_direction = "DEPOSIT"`, line item `balance = "DECREASE"` (debits/reduces liability debt owed to owner, credits expense category).
- Update [`api/tests/test_wave_client.py`](file:///D:/src/personal/wrangler/api/tests/test_wave_client.py):
  - Update calls to `create_money_transaction` in test cases to pass keyword argument `anchor_account_id` and assert `input["anchor"]["accountId"] == anchor_account_id`.

---

## Phase 3: Backend Schemas, Companies Router & Integration Tests

*Goal:* Update Pydantic schemas and company router endpoints to expose `wave_anchor_account_id`, accept `anchor_account_id` with backward compatibility fallback for `equity_account_id`, and wire synchronization calls.

### 3.1 Update Pydantic Schemas for Companies and Wave Connection
- In [`api/src/schemas/company.py`](file:///D:/src/personal/wrangler/api/src/schemas/company.py):
  - In [`CompanyResponse`](file:///D:/src/personal/wrangler/api/src/schemas/company.py#L19-L31):
    - Replace `wave_equity_account_id: str | None = None` with:
      ```python
      wave_anchor_account_id: str | None = None
      ```
  - In [`WaveConnectRequest`](file:///D:/src/personal/wrangler/api/src/schemas/company.py#L68-L73):
    - Define:
      ```python
      anchor_account_id: str = Field(..., min_length=1, description="Selected Wave Anchor Account ID")
      equity_account_id: str | None = Field(default=None, description="Legacy fallback alias for anchor_account_id")
      ```
    - Add a `model_validator(mode="before")` to allow seamless backward compatibility: if `anchor_account_id` is omitted but `equity_account_id` is supplied in transitional payloads, set `anchor_account_id = equity_account_id`.
- Update [`api/tests/test_companies.py`](file:///D:/src/personal/wrangler/api/tests/test_companies.py):
  - In `test_create_company_success`: assert `"wave_anchor_account_id" in data` and `"wave_equity_account_id" not in data`.

### 3.2 Update Companies Router Endpoints and Synchronization Flow
- In [`api/src/routers/companies.py`](file:///D:/src/personal/wrangler/api/src/routers/companies.py):
  - In `_format_company_response`:
    - Update connection check:
      ```python
      is_wave_connected = bool(company.wave_api_token and company.wave_business_id and company.wave_anchor_account_id)
      ```
    - Return dictionary key `"wave_anchor_account_id": company.wave_anchor_account_id`.
  - In `connect_wave` (`POST /api/companies/{company_id}/wave/connect`):
    - Assign `company.wave_anchor_account_id = payload.anchor_account_id`.
  - In `disconnect_wave` (`POST /api/companies/{company_id}/wave/disconnect`):
    - Reset `company.wave_anchor_account_id = None`.
  - In `sync_wave` (`POST /api/companies/{company_id}/sync-wave`):
    - Verify `company.wave_anchor_account_id` is set when confirming Wave connection status.
    - Pass `anchor_account_id=company.wave_anchor_account_id` into `WaveClient.create_money_transaction`.
  - In [`api/companies.http`](file:///D:/src/personal/wrangler/api/companies.http):
    - Update HTTP sample requests to reference `wave_anchor_account_id` and `anchor_account_id`.
- Update [`api/tests/test_company_wave_config.py`](file:///D:/src/personal/wrangler/api/tests/test_company_wave_config.py) and [`api/tests/test_wave_sync_api.py`](file:///D:/src/personal/wrangler/api/tests/test_wave_sync_api.py):
  - In `test_company_wave_config.py`:
    - Test `POST /api/companies/{company_id}/wave/connect` using `anchor_account_id` payload; verify `wave_anchor_account_id` persists in response and database.
    - Test backward compatibility: verify `POST /api/companies/{company_id}/wave/connect` using legacy `equity_account_id` payload succeeds and populates `wave_anchor_account_id`.
    - Test `POST /api/companies/{company_id}/wave/disconnect` clears `wave_anchor_account_id`.
  - In `test_wave_sync_api.py`:
    - Configure mock company with `wave_anchor_account_id="anchor_123"` and assert `WaveClient.create_money_transaction` is called with `anchor_account_id="anchor_123"`.

---

## Phase 4: Frontend Types, Pinia Store & UI Components

*Goal:* Update Vue 3 / Quasar frontend types, store actions, and `CompanyFormDialog.vue` UI components to use anchor account semantics and display clear reimbursement and bank labels.

### 4.1 Update TypeScript Types and Pinia Store
- In [`web/src/types/company.ts`](file:///D:/src/personal/wrangler/web/src/types/company.ts):
  - On interface [`Company`](file:///D:/src/personal/wrangler/web/src/types/company.ts#L1-L12):
    - Replace `wave_equity_account_id?: string | null` with:
      ```typescript
      wave_anchor_account_id?: string | null
      ```
- In [`web/src/types/wave.ts`](file:///D:/src/personal/wrangler/web/src/types/wave.ts):
  - On interface [`WaveConnectPayload`](file:///D:/src/personal/wrangler/web/src/types/wave.ts#L20-L25):
    - Replace `equity_account_id: string` with:
      ```typescript
      anchor_account_id: string
      ```
- In [`web/src/stores/companies.ts`](file:///D:/src/personal/wrangler/web/src/stores/companies.ts):
  - In `connectWave(companyId: string, payload: WaveConnectPayload)`:
    - Pass payload `{ token, business_id, business_name, anchor_account_id: payload.anchor_account_id }` in the POST request to `/api/companies/${companyId}/wave/connect`.
- Update [`web/tests/waveStores.test.ts`](file:///D:/src/personal/wrangler/web/tests/waveStores.test.ts):
  - Update `connectWave` test to supply `anchor_account_id: "a1"`, verify payload sent to endpoint, and assert `company.wave_anchor_account_id == "a1"`.
  - Update `disconnectWave` test to assert `company.wave_anchor_account_id == null`.

### 4.2 Update `CompanyFormDialog.vue` UI and Component Tests
- In [`web/src/components/CompanyFormDialog.vue`](file:///D:/src/personal/wrangler/web/src/components/CompanyFormDialog.vue):
  - Update anchor account `<q-select>`:
    ```html
    <q-select
      v-if="anchorAccounts.length > 0"
      v-model="selectedAnchorId"
      :options="anchorOptions"
      emit-value
      map-options
      label="Select Anchor Account (Reimbursement / Bank) *"
      outlined
      dense
      :loading="fetchingAccounts"
      data-testid="select-wave-anchor"
    />
    ```
  - In edit mode prefilling:
    ```typescript
    selectedAnchorId.value = comp.wave_anchor_account_id ?? null
    ```
  - In save submission when connecting Wave:
    ```typescript
    await companyStore.connectWave(result.id, {
      token: waveToken.value.trim(),
      business_id: selectedBusinessId.value,
      business_name: chosenBiz?.name || "Wave Business",
      anchor_account_id: selectedAnchorId.value,
    })
    ```
- Update [`web/tests/waveUi.test.ts`](file:///D:/src/personal/wrangler/web/tests/waveUi.test.ts):
  - Update template assertion to verify `data-testid="select-wave-anchor"`.
  - Update mock accounts data in `selecting a business triggers accounts fetch and populates anchor candidates` to include `DUE_TO_YOU_AND_OTHER_OWNERS` (Liability) and `CASH_AND_BANK` (Asset).
  - Verify options populate with "Due to You and Other Business Owners" and select label displays "Select Anchor Account (Reimbursement / Bank) *".
