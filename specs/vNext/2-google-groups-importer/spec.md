# Google Groups Mailbox Importer Specification

> [!WARNING]
> **STATUS: INCOMPLETE / DRAFT — PENDING INTEGRATION & EMAIL PARSING DETAILS**
> This specification defines the architectural adapter contract and framework integration for the Google Groups Mailbox Importer, but intentionally leaves the Google API authentication/transport details, email-to-transaction extraction rules, and conversation-locking mechanics incomplete for future refinement.

---

## 1. Goal & Overview
The **Google Groups Mailbox Importer** (`GoogleGroupsImporter`) is an adapter implementation of [`BaseImporter`](file:///D:/src/personal/wrangler/specs/v2/1-importer-framework/spec.md) that:
1. Connects to a designated Google Groups mailbox (`input_type = ImporterInputType.NONE` — requires no uploaded file from the user).
2. Reads unlocked/unprocessed email conversations representing receipts, bills, or transaction notifications.
3. Extracts transaction metadata (`external_id`, `date`, `description`, `total_amount`, `currency_code`) and attaches any receipt file (`ImporterReceiptData`, e.g., PDF/image attachment or rendered email receipt).
4. Supports marking conversations as imported (`supports_mark_imported = True`) by locking the corresponding conversations in Google Groups when `mark_as_imported(external_ids)` is invoked automatically upon staging acceptance or dismissal.

---

## 2. Importer Adapter Contract (`api/src/services/importers/google_groups.py`)

### 2.1 Class Metadata & Capabilities
- **Class Name:** `GoogleGroupsImporter(BaseImporter)`
- **`importer_id`:** `"google_groups"`
- **`source_name`:** `"google_groups"`
- **`display_name`:** `"Google Groups Mailbox"`
- **`description`:** `"Imports transaction emails and receipt attachments from a Google Groups mailbox and locks processed conversations."`
- **`input_type`:** `ImporterInputType.NONE`
- **`accepted_file_types`:** `[]`
- **`supports_mark_imported`:** `True`

### 2.2 Integration with Importer Framework
1. **Registration:** Registered in `ImporterRegistry` (`api/src/services/importers/registry.py`) under `"google_groups"`.
2. **Deduplication (`external_id`):**
   - Each email conversation/thread or message maps to a deterministic `external_id` (e.g., Google Thread ID / Message ID).
   - Even if a conversation has not yet been locked in Google Groups (or if locking previously failed), Wrangler's `staged_transactions` and `transactions` tables enforce uniqueness on `("google_groups", external_id)` so the conversation will not be duplicated.
3. **Receipt Supply (`ImporterReceiptData`):**
   - Unlike CSV importers, `GoogleGroupsImporter` populates `ImportedTransactionData.receipt = ImporterReceiptData(filename=..., content=..., content_type=...)` when a receipt attachment (PDF, PNG, JPEG) or printable email body is extracted.
   - The framework persists this file into `settings.RECEIPT_STORAGE_DIR` and links `StagedTransaction.receipt_file_path` automatically during `POST /api/importers/google_groups/run`.
4. **Automatic Post-Import Marking (`mark_as_imported`):**
   - Implements `async def mark_as_imported(self, external_ids: list[str]) -> None`.
   - Invoked automatically by `POST /api/staging/accept` and `POST /api/staging/{id}/dismiss` to lock the corresponding conversations in Google Groups so future runs only need to inspect unlocked conversations.

---

## 3. Open / Incomplete Sections (To Be Refined)

> [!IMPORTANT]
> The following sections must be completed before implementing `GoogleGroupsImporter`:

### 3.1 Google Groups Authentication & API Transport — **[TBD]**
- **Authentication Mechanism:** Determine whether access uses a Google Workspace Service Account with Domain-Wide Delegation, OAuth 2.0 Client Credentials / Refresh Token in `.env`, or another mechanism.
- **Required Environment Variables:** Define configuration keys in `api/src/core/config.py` (e.g., `GOOGLE_GROUPS_EMAIL`, credentials path/token).
- **Querying Conversations:** Specify the exact API or protocol used to list unlocked conversations in the target group.

### 3.2 Email & Receipt Parsing Rules — **[TBD]**
- **`external_id` Mapping:** Confirm whether `external_id` is the Thread ID or Message ID, and whether a single thread can contain multiple transactions.
- **Field Extraction (`date`, `description`, `total_amount`, `currency_code`):** Define how sender, subject, and body content are parsed to extract the transaction amount, date, and description, and how unparseable emails should be handled.
- **Receipt Extraction:** Specify whether receipts come strictly from MIME attachments (`.pdf`, `.png`, `.jpg`) or whether HTML email bodies should be converted/saved as receipt files when no attachment is present.

### 3.3 Conversation Locking Mechanism (`mark_as_imported`) — **[TBD]**
- **Locking API Call:** Specify the exact API call/mutation used to lock a conversation thread in Google Groups given its `external_id`.
