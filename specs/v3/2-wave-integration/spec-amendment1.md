# Specification Amendment 1: Due to Owner Anchor Classification & Column Renaming

**Target Specification:** [`specs/v3/2-wave-integration/spec.md`](file:///D:/src/personal/wrangler/specs/v3/2-wave-integration/spec.md)  
**Status:** Approved  
**Author:** Application Architecture  
**Date:** 2026-10-20  

---

## 1. Context & Motivation

In [`specs/v3/2-wave-integration/spec.md`](file:///D:/src/personal/wrangler/specs/v3/2-wave-integration/spec.md), the initial design assumed that transactions routed through personal payment methods would be anchored against an equity account (`OWNERS_EQUITY`) or a bank clearing account (`CASH_AND_BANK`).

In actual operational accounting, personal expenses incurred on behalf of a company that must be reimbursed are tracked on the balance sheet under **Liabilities & Credit Cards** in Wave—specifically within the **"Due to You and Other Business Owners"** account ledger rather than an equity or bank account ledger.

Because the initial filter in `WaveClient.get_business_accounts` only allowed `{"CASH_AND_BANK", "CREDIT_CARD", "MONEY_MARKET", "OWNERS_EQUITY"}`:
1. Liability accounts with the Wave subtype `DUE_TO_YOU_AND_OTHER_OWNERS` were excluded from the anchor account dropdown.
2. The column and API schema specifically referenced "equity" (`wave_equity_account_id`, `equity_account_id`), which is inaccurate and misleading for liability-anchored reimbursement flows.

This amendment formally defines the scope, data model migration, backend updates, frontend UI adjustments, and test criteria to support **Due to Owner** accounts and universally rename equity account references to anchor account references.

---

## 2. Summary of Changes

1. **Subtype Reclassification:**
   - **Add:** `DUE_TO_YOU_AND_OTHER_OWNERS` (Wave's programmatic enum for *"Due to You and Other Business Owners"* under `LIABILITY`).
   - **Remove:** `OWNERS_EQUITY` from candidate anchor accounts.
   - **Retain:** `CASH_AND_BANK`, `CREDIT_CARD`, and `MONEY_MARKET` for bank clearing or corporate card usage.
2. **Column & Schema Renaming:**
   - Rename database column `companies.wave_equity_account_id` to `companies.wave_anchor_account_id`.
   - Update ORM models, Pydantic schemas, router payloads, and Pinia frontend store types to use `wave_anchor_account_id` (or `anchor_account_id` in request payloads).
3. **UI Labeling & Polish:**
   - Update [`CompanyFormDialog.vue`](file:///D:/src/personal/wrangler/web/src/components/CompanyFormDialog.vue) labels to clearly indicate reimbursement liability and bank accounts.

---

## 3. Data Model & Database Migration

### 3.1 Alembic Migration
A new migration script must be created in `api/alembic/versions/` revising current head `f2a7b1c9d8e3`:

- **Revision ID:** Auto-generated (e.g., `a1c4e9b8f3d2`)
- **Down Revision:** `f2a7b1c9d8e3` (`add wave integration tables and columns`)
- **`upgrade()` Operations:**
  Using Alembic's batch operations for SQLite compatibility:
  ```python
  with op.batch_alter_table("companies", schema=None) as batch_op:
      batch_op.alter_column(
          "wave_equity_account_id",
          new_column_name="wave_anchor_account_id",
          existing_type=sa.String(),
          nullable=True,
      )
  ```
- **`downgrade()` Operations:**
  ```python
  with op.batch_alter_table("companies", schema=None) as batch_op:
      batch_op.alter_column(
          "wave_anchor_account_id",
          new_column_name="wave_equity_account_id",
          existing_type=sa.String(),
          nullable=True,
      )
  ```

### 3.2 SQLAlchemy Model Changes ([`api/src/models/company.py`](file:///D:/src/personal/wrangler/api/src/models/company.py))
Replace:
```python
wave_equity_account_id: Mapped[str | None] = mapped_column(String, nullable=True)
```
with:
```python
wave_anchor_account_id: Mapped[str | None] = mapped_column(String, nullable=True)
```

---

## 4. Backend Service & API Specification

### 4.1 Wave Client Filtering ([`api/src/services/wave/client.py`](file:///D:/src/personal/wrangler/api/src/services/wave/client.py))

#### `get_business_accounts(token: str, business_id: str) -> WaveAccountsResult`
Update the filtering rules for candidate anchor accounts:
- **Valid Anchor Types:** `{"ASSET", "LIABILITY"}`
- **Valid Anchor Subtypes:**
  - `DUE_TO_YOU_AND_OTHER_OWNERS` *(New: Due to You and Other Business Owners liability account)*
  - `CASH_AND_BANK` *(Retained: Bank / Checking / Operating)*
  - `CREDIT_CARD` *(Retained: Corporate / Business Credit Card)*
  - `MONEY_MARKET` *(Retained: Liquid cash management)*
- Exclude accounts where `subtype.value == "OWNERS_EQUITY"` or where `isArchived == True`.

```python
valid_anchor_subtypes = {
    "DUE_TO_YOU_AND_OTHER_OWNERS",
    "CASH_AND_BANK",
    "CREDIT_CARD",
    "MONEY_MARKET",
}
valid_anchor_types = {"ASSET", "LIABILITY"}
```

#### `create_money_transaction(...) -> str`
Rename parameter `equity_account_id` to `anchor_account_id`:
```python
@classmethod
async def create_money_transaction(
    cls,
    token: str,
    business_id: str,
    external_id: str,
    date: str,
    description: str,
    amount: Decimal,
    anchor_account_id: str,
    category_account_id: str,
) -> str:
```
The payload construction remains structurally unchanged, mapping `anchor.accountId = anchor_account_id`:
- When `amount > 0`: `anchor.direction = "WITHDRAWAL"`, `anchor.accountId = anchor_account_id`.
  *(In Wave accounting, a WITHDRAWAL on a Liability account like `DUE_TO_YOU_AND_OTHER_OWNERS` credits/increases the liability owed to the owner, while the line item increases expense. The ledger entry balances perfectly).*
- When `amount < 0`: `anchor.direction = "DEPOSIT"`, `anchor.accountId = anchor_account_id`.
  *(Credits/refunds debit/reduce the liability owed to the owner).*

### 4.2 Pydantic Schemas ([`api/src/schemas/company.py`](file:///D:/src/personal/wrangler/api/src/schemas/company.py))

1. **`CompanyResponse`:**
   ```python
   class CompanyResponse(BaseModel):
       id: uuid.UUID
       name: str
       wave_business_id: str | None = None
       wave_business_name: str | None = None
       wave_anchor_account_id: str | None = None
       is_wave_connected: bool = False
       categories_count: int = 0
       model_config = ConfigDict(from_attributes=True)
   ```
2. **`WaveConnectRequest`:**
   ```python
   class WaveConnectRequest(BaseModel):
       token: str = Field(..., min_length=1, description="Wave Full Access Bearer Token")
       business_id: str = Field(..., min_length=1, description="Wave Business ID")
       business_name: str = Field(..., min_length=1, description="Wave Business Name")
       anchor_account_id: str = Field(..., min_length=1, description="Selected Wave Anchor Account ID")
   ```
   *Note for backward compatibility:* Accept `equity_account_id` as an optional fallback alias if `anchor_account_id` is missing in transitional payload calls.

### 4.3 Companies Router ([`api/src/routers/companies.py`](file:///D:/src/personal/wrangler/api/src/routers/companies.py))

1. **Wave Connected Check:**
   ```python
   is_wave_connected = bool(company.wave_api_token and company.wave_business_id and company.wave_anchor_account_id)
   ```
2. **`POST /api/companies/{company_id}/wave/connect`:**
   Assigns `company.wave_anchor_account_id = payload.anchor_account_id`.
3. **`POST /api/companies/{company_id}/wave/disconnect`:**
   Clears `company.wave_anchor_account_id = None`.
4. **`POST /api/companies/{company_id}/wave/sync`:**
   Passes `anchor_account_id=company.wave_anchor_account_id` into `WaveClient.create_money_transaction`.

---

## 5. Frontend UI & State Updates

### 5.1 TypeScript Types ([`web/src/types/company.ts`](file:///D:/src/personal/wrangler/web/src/types/company.ts))
Update interface properties:
```typescript
export interface Company {
  id: string
  name: string
  wave_business_id?: string | null
  wave_business_name?: string | null
  wave_anchor_account_id?: string | null
  is_wave_connected?: boolean
  categories_count?: number
}

export interface WaveConnectPayload {
  token: string
  business_id: string
  business_name: string
  anchor_account_id: string
}
```

### 5.2 Company Pinia Store ([`web/src/stores/companies.ts`](file:///D:/src/personal/wrangler/web/src/stores/companies.ts))
In `connectWave(companyId: string, payload: WaveConnectPayload)`:
Pass `{ token, business_id, business_name, anchor_account_id: payload.anchor_account_id }` in the POST request to `/api/companies/${companyId}/wave/connect`.

### 5.3 Company Form Dialog ([`web/src/components/CompanyFormDialog.vue`](file:///D:/src/personal/wrangler/web/src/components/CompanyFormDialog.vue))
- Update select label:
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
- When prefilling an existing company in edit mode:
  ```typescript
  selectedAnchorId.value = props.company.wave_anchor_account_id ?? null
  ```
- When dispatching connection:
  ```typescript
  await companyStore.connectWave(savedCompany.id, {
    token: waveToken.value.trim(),
    business_id: selectedBusinessId.value,
    business_name: selectedBiz?.name || "",
    anchor_account_id: selectedAnchorId.value,
  })
  ```

---

## 6. Double-Entry Accounting Verification

Wave's `moneyTransactionCreate` mutation enforces double-entry balance constraints. The table below documents how transactions anchor against `DUE_TO_YOU_AND_OTHER_OWNERS`:

| Scenario | Amount | Direction / Balance | Wave Meaning & Balance Sheet Impact |
| :--- | :--- | :--- | :--- |
| **Standard Expense** (e.g., $150 personal spend for business) | `+150.00` | Anchor: `WITHDRAWAL`<br>Line Item: `INCREASE` | **Credit** Liability (`DUE_TO_YOU_AND_OTHER_OWNERS`) by $150.<br>**Debit** Expense category by $150.<br>*Result:* Debt owed to business owner increases. |
| **Refund / Return** (e.g., -$30 refund credited back to personal card) | `-30.00` | Anchor: `DEPOSIT`<br>Line Item: `DECREASE` | **Debit** Liability (`DUE_TO_YOU_AND_OTHER_OWNERS`) by $30.<br>**Credit** Expense category by $30.<br>*Result:* Debt owed to business owner decreases. |

---

## 7. Test Suite Updates & Acceptance Criteria

### 7.1 Backend Tests (`api/tests/`)
1. **[`test_migrations.py`](file:///D:/src/personal/wrangler/api/tests/test_migrations.py) & [`test_schema.py`](file:///D:/src/personal/wrangler/api/tests/test_schema.py):**
   - Verify `wave_anchor_account_id` is present in `companies` columns and `wave_equity_account_id` is absent.
2. **[`test_wave_client.py`](file:///D:/src/personal/wrangler/api/tests/test_wave_client.py):**
   - Mock account list containing `DUE_TO_YOU_AND_OTHER_OWNERS` (Liability), `OWNERS_EQUITY` (Equity), and `CASH_AND_BANK` (Asset).
   - Assert `DUE_TO_YOU_AND_OTHER_OWNERS` and `CASH_AND_BANK` are returned in `anchor_accounts`.
   - Assert `OWNERS_EQUITY` is excluded from `anchor_accounts`.
3. **[`test_company_wave_config.py`](file:///D:/src/personal/wrangler/api/tests/test_company_wave_config.py):**
   - Test connecting with `anchor_account_id`.
   - Verify `wave_anchor_account_id` persists and returns in `CompanyResponse`.
4. **[`test_wave_sync_api.py`](file:///D:/src/personal/wrangler/api/tests/test_wave_sync_api.py):**
   - Verify transactions are created with `anchor.accountId == company.wave_anchor_account_id`.

### 7.2 Frontend Tests (`web/tests/`)
1. **[`waveStores.test.ts`](file:///D:/src/personal/wrangler/web/tests/waveStores.test.ts):**
   - Assert `connectWave` sends `anchor_account_id` payload and updates `company.wave_anchor_account_id`.
2. **[`waveUi.test.ts`](file:///D:/src/personal/wrangler/web/tests/waveUi.test.ts):**
   - Assert `CompanyFormDialog.vue` renders the updated anchor dropdown with "Due to You and Other Business Owners" accounts and connects successfully.
