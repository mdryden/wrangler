---
status: Implemented
subsystems:
  - Accounting Export
amendments: []
supersedes: null
superseded_by: null
---

# Specification Amendment 3: Move Receipt Reference to Wave Transaction Notes

**Target Specification:** [`specs/9-wave-integration/spec.md`](file:///D:/src/personal/wrangler/specs/9-wave-integration/spec.md)  
**Status:** Implemented  
**Subsystems:** Accounting Export  
**Date:** 2026-10-26  

---

## 1. Context & Motivation

In the baseline Wave integration specification ([`specs/9-wave-integration/spec.md`](file:///D:/src/personal/wrangler/specs/9-wave-integration/spec.md), Sections 1.2 #6 and 4.2.3), when synchronizing an allocation with an attached receipt to Wave via the `moneyTransactionCreate` GraphQL mutation, the receipt filename was appended directly to the `description` field:
```
"{tx.description} [Receipt: {sanitized_filename}]"
```

In day-to-day bookkeeping inside Wave, appending `[Receipt: filename.pdf]` to the primary transaction `description` clutters the ledger table, truncates long vendor/order descriptions, and makes it harder to scan or match transactions. Wave's `MoneyTransactionCreateInput` GraphQL schema natively supports an optional `notes: String` field specifically intended for supplementary transaction metadata and memo annotations.

This amendment moves the receipt reference out of `description` and places it into the Wave transaction `notes` field (`"Receipt: {filename}"`), keeping `description` clean and identical to the Wrangler transaction description.

---

## 2. Summary of Changes

1. **Wave GraphQL Client ([`api/src/services/wave/client.py`](file:///D:/src/personal/wrangler/api/src/services/wave/client.py)):**
   - Add an optional `notes: str | None = None` parameter to [`WaveClient.create_money_transaction`](file:///D:/src/personal/wrangler/api/src/services/wave/client.py#L226-L236).
   - When `notes` is non-empty, include `"notes": notes` in the `MoneyTransactionCreateInput` GraphQL variable payload (`input_payload`).
2. **Wave Sync Endpoint ([`api/src/routers/companies.py`](file:///D:/src/personal/wrangler/api/src/routers/companies.py)):**
   - In [`sync_company_to_wave`](file:///D:/src/personal/wrangler/api/src/routers/companies.py#L474-L492), pass `description=alloc.transaction.description` unmodified.
   - If `alloc.transaction.receipt_file_path` is present, extract `filename = os.path.basename(alloc.transaction.receipt_file_path)` and pass `notes=f"Receipt: {filename}"` (otherwise `notes=None`) to `WaveClient.create_money_transaction`.
3. **Wave API Skill & Schema Reference Documentation:**
   - Update [`wave_schema_snippets.graphql`](file:///D:/src/personal/wrangler/.agents/skills/wave-api/references/wave_schema_snippets.graphql) and [`SKILL.md`](file:///D:/src/personal/wrangler/.agents/skills/wave-api/SKILL.md) during implementation to document `notes: String` on `MoneyTransactionCreateInput`.
4. **Zero Database Migration Required:**
   - This change affects only the outbound Wave GraphQL mutation payload. No SQLite schema changes or Alembic migrations are needed.

---

## 3. Backend Service & API Specification

### 3.1 Wave Client ([`api/src/services/wave/client.py`](file:///D:/src/personal/wrangler/api/src/services/wave/client.py))

Update `WaveClient.create_money_transaction` signature and payload construction:

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
    notes: str | None = None,
) -> str:
    """Execute Wave moneyTransactionCreate mutation with double-entry balance mappings."""
    float_amt = float(abs(amount))
    if amount > Decimal("0"):
        anchor_direction = "WITHDRAWAL"
        line_balance = "INCREASE"
    else:
        anchor_direction = "DEPOSIT"
        line_balance = "DECREASE"

    input_payload: dict[str, Any] = {
        "businessId": business_id,
        "externalId": external_id,
        "date": date,
        "description": description,
        "anchor": {
            "accountId": anchor_account_id,
            "amount": float_amt,
            "direction": anchor_direction,
        },
        "lineItems": [
            {
                "accountId": category_account_id,
                "amount": float_amt,
                "balance": line_balance,
            }
        ],
    }
    if notes:
        input_payload["notes"] = notes
```

### 3.2 Companies Router ([`api/src/routers/companies.py`](file:///D:/src/personal/wrangler/api/src/routers/companies.py))

In [`sync_company_to_wave`](file:///D:/src/personal/wrangler/api/src/routers/companies.py#L474-L492), replace the description concatenation logic:

```python
description = alloc.transaction.description
notes: str | None = None
if alloc.transaction.receipt_file_path:
    filename = os.path.basename(alloc.transaction.receipt_file_path)
    notes = f"Receipt: {filename}"

try:
    wave_tx_id = await WaveClient.create_money_transaction(
        token=company.wave_api_token,
        business_id=company.wave_business_id,
        external_id=f"wrangler_{alloc.id}",
        date=alloc.transaction.date.isoformat(),
        description=description,
        amount=alloc.amount,
        anchor_account_id=company.wave_anchor_account_id,
        category_account_id=category_account_id,
        notes=notes,
    )
```

---

## 4. Superseded Clauses in Base Specification

This amendment modifies and supersedes the following clauses of [`specs/9-wave-integration/spec.md`](file:///D:/src/personal/wrangler/specs/9-wave-integration/spec.md):

| Base Spec Section | Original Clause | Superseded Clause (Amendment 3) |
| :--- | :--- | :--- |
| **Section 1.2, Item 6** | *"Financial sync pushes structured ledger data to Wave via `moneyTransactionCreate`, annotating the transaction description with a receipt memo reference."* | Financial sync pushes structured ledger data to Wave via `moneyTransactionCreate`, keeping `description` clean and writing the receipt reference (`"Receipt: {filename}"`) into the transaction's `notes` field. |
| **Section 4.2.3 (Parameters)** | *"`description`: Formatted as `\"{tx.description} [Receipt: {sanitized_filename}]\"` if an attached receipt exists, otherwise `\"{tx.description}\"`."* | `description`: Always `"{tx.description}"`.<br>`notes`: Set to `"Receipt: {sanitized_filename}"` when `tx.receipt_file_path` is present; omitted (`None`) when no receipt is attached. |

---

## 5. Test Suite Updates & Acceptance Criteria

### 5.1 Backend Unit Tests (`api/tests/`)

1. **[`test_wave_client.py`](file:///D:/src/personal/wrangler/api/tests/test_wave_client.py):**
   - Update [`test_create_money_transaction_positive_expense`](file:///D:/src/personal/wrangler/api/tests/test_wave_client.py#L210-L255) to pass `description="Office Chairs"` and `notes="Receipt: chair.png"`. Assert `inp["description"] == "Office Chairs"` and `inp["notes"] == "Receipt: chair.png"`.
   - In [`test_create_money_transaction_negative_refund`](file:///D:/src/personal/wrangler/api/tests/test_wave_client.py#L258-L298) (where `notes` is omitted/`None`), assert `"notes" not in inp`.
2. **[`test_wave_sync_api.py`](file:///D:/src/personal/wrangler/api/tests/test_wave_sync_api.py):**
   - Update [`test_sync_wave_receipt_memo_formatting_and_partial_sync_resilience`](file:///D:/src/personal/wrangler/api/tests/test_wave_sync_api.py#L262-L356):
     - Verify `tx1` (with `receipt_file_path="/var/storage/receipts/receipt123.pdf"`) invokes `WaveClient.create_money_transaction` with `description="Tx With Receipt"` and `notes="Receipt: receipt123.pdf"`.
     - Verify `tx3` (without `receipt_file_path`) invokes `WaveClient.create_money_transaction` with `description="Tx Without Receipt"` and `notes=None`.
