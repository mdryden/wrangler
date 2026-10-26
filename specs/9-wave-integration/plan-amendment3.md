# Implementation Plan: Amendment 3 - Move Receipt Reference to Wave Transaction Notes

This implementation plan defines the deliverables required to separate receipt file references from transaction descriptions when synchronizing allocations to Wave, as specified in [`specs/9-wave-integration/spec-amendment3.md`](file:///D:/src/personal/wrangler/specs/9-wave-integration/spec-amendment3.md).

In earlier implementations, when synchronizing an allocation with an attached receipt to Wave via the `moneyTransactionCreate` GraphQL mutation, Wrangler appended `[Receipt: <filename>]` directly into the `description` string. In Wave's ledger, this cluttered vendor descriptions and complicated transaction matching. Wave's `MoneyTransactionCreateInput` schema natively supports an optional `notes: String` field intended for memo annotations. Under Amendment 3, Wrangler leaves `description` untouched and places receipt references in `notes` (`Receipt: <filename>`), or omits `notes` entirely if no receipt is attached.

The plan is divided into sequential, deliverable-driven phases with atomic implementation tasks in dependency order. Automated test coverage is incorporated directly into each task adhering to [`AGENTS.md`](file:///D:/src/personal/wrangler/AGENTS.md) and [`specs/ARCHITECTURE.md`](file:///D:/src/personal/wrangler/specs/ARCHITECTURE.md).

---

## Phase 1: Wave Client Service & Unit Tests

*Goal:* Update the low-level Wave GraphQL client to support the optional `notes` parameter in `create_money_transaction` and verify payload serialization with unit tests.

### 1.1 Add `notes` Parameter to `WaveClient.create_money_transaction` and Update Client Unit Tests
- In [`api/src/services/wave/client.py`](file:///D:/src/personal/wrangler/api/src/services/wave/client.py):
  - In `WaveClient.create_money_transaction`:
    - Add optional parameter `notes: str | None = None` to the method signature.
    - Conditionally include `"notes": notes` in `input_payload` when `notes` is truthy:
      ```python
      if notes:
          input_payload["notes"] = notes
      ```
    - Preserve existing double-entry balance mappings, `externalId`, `date`, `description`, `anchor`, and `lineItems` constructions.
- In [`api/tests/test_wave_client.py`](file:///D:/src/personal/wrangler/api/tests/test_wave_client.py):
  - In `test_create_money_transaction_positive_expense`:
    - Call `WaveClient.create_money_transaction` with `description="Office Chairs"` and `notes="Receipt: chair.png"`.
    - Assert `inp["description"] == "Office Chairs"`.
    - Assert `inp["notes"] == "Receipt: chair.png"`.
  - In `test_create_money_transaction_negative_refund`:
    - Call `WaveClient.create_money_transaction` with `notes` omitted / default `None`.
    - Assert `"notes" not in inp`.

---

## Phase 2: Company Wave Sync Endpoint & Integration Tests

*Goal:* Update the company Wave synchronization router endpoint to pass clean transaction descriptions and attach receipt references via `notes`, verifying end-to-end sync behavior with API integration tests.

### 2.1 Update `POST /api/companies/{company_id}/sync-wave` to Populate `notes` with Receipt Memo and Update Sync API Tests
- In [`api/src/routers/companies.py`](file:///D:/src/personal/wrangler/api/src/routers/companies.py):
  - In `sync_company_to_wave` (`POST /api/companies/{company_id}/sync-wave`):
    - Retain `description = alloc.transaction.description` without appending receipt memos.
    - Extract receipt note if attached:
      ```python
      notes: str | None = None
      if alloc.transaction.receipt_file_path:
          filename = os.path.basename(alloc.transaction.receipt_file_path)
          notes = f"Receipt: {filename}"
      ```
    - Pass `notes=notes` and `description=description` to `WaveClient.create_money_transaction(...)`.
    - Retain atomic per-transaction DB commit, error accumulation, and lock state transitions (`is_locked = True`, `wave_transaction_id = wave_tx_id`).
- In [`api/tests/test_wave_sync_api.py`](file:///D:/src/personal/wrangler/api/tests/test_wave_sync_api.py):
  - In `test_sync_wave_receipt_memo_formatting_and_partial_sync_resilience`:
    - Update `mock_create` helper to capture `description` and `notes` kwargs.
    - Assert call for `tx1` (with `receipt_file_path="/var/storage/receipts/receipt123.pdf"`) receives `description="Tx With Receipt"` and `notes="Receipt: receipt123.pdf"`.
    - Assert call for `tx2` (failing transaction without receipt) receives `description="Failing Tx"` and `notes=None`.
    - Assert call for `tx3` (without receipt) receives `description="Tx Without Receipt"` and `notes=None`.
    - Retain assertions for partial failure handling: `synced_count: 2`, `failed_count: 1`, with `alloc1` and `alloc3` locked and `alloc2` unlocked.

---

## Phase 3: Wave API Reference Documentation & Skill Schema

*Goal:* Synchronize internal Wave GraphQL schema definitions and skill documentation with the official Wave API contract.

### 3.1 Update Wave GraphQL Schema Snippets and Skill Documentation for `MoneyTransactionCreateInput.notes`
- In [`.agents/skills/wave-api/references/wave_schema_snippets.graphql`](file:///D:/src/personal/wrangler/.agents/skills/wave-api/references/wave_schema_snippets.graphql):
  - Add `notes: String` to `input MoneyTransactionCreateInput`:
    ```graphql
    input MoneyTransactionCreateInput {
      businessId: ID!
      externalId: String
      date: Date!
      description: String!
      anchor: MoneyTransactionAnchorInput!
      lineItems: [MoneyTransactionLineItemInput!]!
      notes: String
    }
    ```
- In [`.agents/skills/wave-api/SKILL.md`](file:///D:/src/personal/wrangler/.agents/skills/wave-api/SKILL.md):
  - Under Section 3 ("Transaction Mutations -> Creating a Money Transaction -> Input Payload Construction"):
    - Add `- **notes**: Optional memo / annotation string (e.g. "Receipt: filename.pdf").`
    - Update description formatting note to clarify that descriptions remain clean and receipt references belong in `notes`.
