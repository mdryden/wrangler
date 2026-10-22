# Implementation Plan: Staged Receipt AI Parsing & Inline Field Suggestions

This implementation plan details the engineering deliverables required to deliver on-demand AI receipt parsing and inline field suggestions within the Staged Transaction Edit Dialog, as specified in [`specs/13-staged-receipt-ai-parsing/spec.md`](file:///D:/src/personal/wrangler/specs/13-staged-receipt-ai-parsing/spec.md) and aligned with [`specs/ARCHITECTURE.md`](file:///D:/src/personal/wrangler/specs/ARCHITECTURE.md).

---

## Phase 1: Backend Staged Receipt AI Parsing Endpoint & Tests

### 1.1 Backend Staged Receipt Parse Endpoint
- **Target File:** [`api/src/routers/staging.py`](file:///D:/src/personal/wrangler/api/src/routers/staging.py)
- **Description:** Implement `POST /api/staging/{staged_id}/parse-receipt` (`parse_staged_receipt`) to parse an existing receipt file on disk associated with a staged transaction:
  1. Retrieve `StagedTransaction` by `staged_id` using `_get_staged_tx_or_404(db, staged_id)`.
  2. Verify transaction status is `"STAGED"`. If not (e.g. `"ACCEPTED"` or `"DISMISSED"`), raise `HTTPException(status_code=400, detail=f"Cannot parse receipt for staged transaction with status '{staged_tx.status}'")`.
  3. Verify `staged_tx.receipt_file_path` is not `None` or empty. If missing, raise `HTTPException(status_code=400, detail="No receipt attached to staged transaction")`.
  4. Resolve the physical receipt file path using [`get_receipt_file_path(staged_tx.receipt_file_path)`](file:///D:/src/personal/wrangler/api/src/services/receipts.py#L33-L50). Catch `ValueError` or `FileNotFoundError` and raise `HTTPException(status_code=400, detail=str(exc))`.
  5. Read file bytes from disk. Validate that `len(file_bytes) <= settings.MAX_RECEIPT_FILE_SIZE` (20MB). If exceeded, raise `HTTPException(status_code=413, detail="Receipt file exceeds 20MB limit")`.
  6. Determine MIME type from file extension using `EXTENSION_TO_MIME` (or `mimetypes.guess_type`). If the extension is not in `ALLOWED_RECEIPT_MIME_TYPES` (`.jpg`, `.jpeg`, `.png`, `.webp`, `.pdf`), raise `HTTPException(status_code=400, detail="Unsupported file type. Allowed: .jpg, .jpeg, .png, .webp, .pdf")`.
  7. Retrieve the configured AI parser via [`services.ai.factory.get_receipt_parser()`](file:///D:/src/personal/wrangler/api/src/services/ai/factory.py#L8-L22) and invoke `await parser.parse_receipt(file_bytes=file_bytes, filename=path.name, mime_type=mime_type)`.
  8. Handle exceptions:
     - Catch `ValueError` and re-raise as `HTTPException(status_code=400, detail=str(exc))`.
     - Catch `RuntimeError` and re-raise as `HTTPException(status_code=503, detail=str(exc))`.
  9. Return the [`ReceiptParseResult`](file:///D:/src/personal/wrangler/api/src/services/ai/base.py#L8-L19) containing `merchant`, `date`, `total_amount`, and `description`.

### 1.2 Backend Pytest Suite for Staged Receipt Parse
- **Target File:** [`api/tests/test_staging_ai_receipt.py`](file:///D:/src/personal/wrangler/api/tests/test_staging_ai_receipt.py)
- **Description:** Implement comprehensive test cases covering stored staged receipt parsing:
  - `test_parse_staged_receipt_happy_path`: Create a `StagedTransaction` with status `STAGED` and write a sample dummy receipt file into `settings.RECEIPT_STORAGE_DIR`. Configure mock AI provider. Send `POST /api/staging/{id}/parse-receipt` with authenticated headers. Verify HTTP 200 and normalized structured fields (`merchant`, `date`, `total_amount`, `description`).
  - `test_parse_staged_receipt_missing_receipt_path`: Staged transaction with `receipt_file_path = None` returns HTTP 400 with `"No receipt attached to staged transaction"`.
  - `test_parse_staged_receipt_file_missing_on_disk`: Staged transaction referencing a missing file on disk returns HTTP 400.
  - `test_parse_staged_receipt_nonexistent_id`: Random non-existent UUID returns HTTP 404.
  - `test_parse_staged_receipt_non_staged_status`: Staged transaction with `status = "ACCEPTED"` or `"DISMISSED"` returns HTTP 400.
  - `test_parse_staged_receipt_unsupported_mime`: Staged transaction with `.zip` or `.txt` receipt file returns HTTP 400 with `"Unsupported file type"`.
  - `test_parse_staged_receipt_payload_too_large`: Staged receipt file exceeding 20MB returns HTTP 413.
  - `test_parse_staged_receipt_ai_runtime_error`: Mock provider or parser raising `RuntimeError` returns HTTP 503 Service Unavailable.
  - `test_parse_staged_receipt_ai_value_error`: Mock provider or parser raising `ValueError` returns HTTP 400 Bad Request.
  - `test_parse_staged_receipt_unauthenticated`: Request without JWT bearer token returns HTTP 401 Unauthorized.

---

## Phase 2: Frontend Data Layer & Suggestions Engine

### 2.1 Staged Transaction Suggestions Types & Pure Logic
- **Target File:** [`web/src/components/stagedTransactionEdit.ts`](file:///D:/src/personal/wrangler/web/src/components/stagedTransactionEdit.ts)
- **Description:** Implement data structures and pure functions for transient field suggestions and match calculations:
  - **Interfaces:**
    - `FieldSuggestion<T = string>`: `{ extractedValue: T; displayValue: string; isMatch: boolean; isDismissed: boolean }`
    - `StagedAiSuggestionsState`: `{ date: FieldSuggestion<string> | null; total_amount: FieldSuggestion<string> | null; description: FieldSuggestion<string> | null }`
  - **Functions:**
    - `createInitialAiSuggestionsState(): StagedAiSuggestionsState`: Returns initial state with `date`, `total_amount`, and `description` set to `null`.
    - `computeAiSuggestions(parseResult: ReceiptParseResponse, form: StagedTransactionEditFormState): StagedAiSuggestionsState`:
      - **Date:** If `parseResult.date` is truthy, compare `form.date.trim() === parseResult.date.trim()`. Set `isMatch` to true if identical. `displayValue = parseResult.date.trim()`.
      - **Total Amount:** If `parseResult.total_amount` is truthy, format to 2-decimal string `aiAmountStr = formatAmount(parseResult.total_amount)`. Check match condition: `form.total_amount && Number(form.total_amount).toFixed(2) === Number(parseResult.total_amount).toFixed(2)`. Set `isMatch` to true if identical. `displayValue = aiAmountStr`.
      - **Description:** If `parseResult.description` is truthy, compare `form.description.trim().toLowerCase() === parseResult.description.trim().toLowerCase()`. Set `isMatch` to true if identical. `displayValue = parseResult.description.trim()`.
      - If a field is missing, null, or empty in `parseResult`, set the corresponding suggestion to `null`.
    - `acceptAiSuggestion(form: StagedTransactionEditFormState, suggestions: StagedAiSuggestionsState, field: 'date' | 'total_amount' | 'description'): void`:
      - For `date`: set `form.date = suggestions.date.extractedValue` and update `suggestions.date.isMatch = true`.
      - For `total_amount`: set `form.total_amount = formatAmount(suggestions.total_amount.extractedValue)`, invoke [`syncSingleStagedSplitAmount(form)`](file:///D:/src/personal/wrangler/web/src/components/stagedTransactionEdit.ts#L49-L53), and update `suggestions.total_amount.isMatch = true`.
      - For `description`: set `form.description = suggestions.description.extractedValue` and update `suggestions.description.isMatch = true`.
    - `dismissAiSuggestion(suggestions: StagedAiSuggestionsState, field: 'date' | 'total_amount' | 'description'): void`:
      - Sets `suggestions[field].isDismissed = true`.
    - `clearStagedReceipt(state: StagedTransactionEditFormState, suggestions?: StagedAiSuggestionsState): void`:
      - Sets `state.staged_receipt_file = null`.
      - If `state.existing_receipt_path !== null`, sets `state.remove_receipt = true`.
      - If `suggestions` is provided, resets `date`, `total_amount`, and `description` to `null`.

### 2.2 Staging Pinia Store Action for Staged Receipt Parsing
- **Target File:** [`web/src/stores/staging.ts`](file:///D:/src/personal/wrangler/web/src/stores/staging.ts)
- **Description:** Add `parseStagedReceipt` method to `useStagingStore`:
  - Function signature: `async function parseStagedReceipt(stagedId: string): Promise<ReceiptParseResponse>`.
  - Reset `error.value = null`.
  - Dispatch `POST /api/staging/${stagedId}/parse-receipt` via [`apiClient.post`](file:///D:/src/personal/wrangler/web/src/api/client.ts).
  - Return the parsed `ReceiptParseResponse`.
  - In `catch`, extract error message, assign to `error.value`, and re-throw.

### 2.3 Staged Suggestions Engine & Store Vitest Suite
- **Target Files:**
  - [`web/src/components/__tests__/stagedTransactionEdit.spec.ts`](file:///D:/src/personal/wrangler/web/src/components/__tests__/stagedTransactionEdit.spec.ts)
  - [`web/src/stores/__tests__/staging.spec.ts`](file:///D:/src/personal/wrangler/web/src/stores/__tests__/staging.spec.ts)
- **Description:** Implement unit tests for suggestions calculation, acceptance, dismissal, receipt clearing, and store integration:
  - `computeAiSuggestions`:
    - Differing date (`"2026-10-14"` vs `"2026-10-15"`) yields `isMatch: false`, `isDismissed: false`.
    - Identical amount (`"29.99"` vs `29.99`) yields `isMatch: true`, `isDismissed: false`.
    - Empty form description + AI returned `"Amazon - Anker Cable"` yields `isMatch: false`.
    - Null / omitted AI fields result in `null` suggestion objects.
  - `acceptAiSuggestion`:
    - Accepting date overwrites `form.date` and sets `isMatch: true`.
    - Accepting total amount overwrites `form.total_amount`, synchronizes single split amount via `syncSingleStagedSplitAmount`, and sets `isMatch: true`.
    - Accepting description overwrites `form.description` and sets `isMatch: true`.
  - `dismissAiSuggestion`:
    - Dismissing suggestion sets `isDismissed: true` without altering input field values.
  - `clearStagedReceipt`:
    - Sets `staged_receipt_file = null`, marks `remove_receipt = true` when an existing receipt path was present, and clears active suggestions state.
  - `parseStagedReceipt`:
    - Verifies store action dispatches `POST /api/staging/{id}/parse-receipt` and handles response and network error states.

---

## Phase 3: Staged Transaction Edit Dialog UI Implementation

### 3.1 Persistent Receipt Controls & AI Scan Integration
- **Target File:** [`web/src/components/StagedTransactionEditDialog.vue`](file:///D:/src/personal/wrangler/web/src/components/StagedTransactionEditDialog.vue)
- **Description:** Refactor the Receipt Attachment section to enforce spatial stability and persistent affordances (Section 4 of `AGENTS.md` and Section 4.1 of the spec):
  1. **Control Group Layout:**
     - Render controls permanently without toggling visibility via `v-if`:
       - `q-file` input (`class="col"`, `dense`, `outlined`, `clearable`, `accept=".pdf,.png,.jpg,.jpeg,application/pdf,image/png,image/jpeg"`).
       - `[ View Receipt ]` button (`q-btn outline dense color="primary" icon="open_in_new"`, `data-testid="btn-staged-view-receipt"`).
       - `[ ✨ Scan with AI ]` button (`q-btn outline dense color="primary" icon="auto_awesome"`, `data-testid="btn-staged-scan-receipt"`).
  2. **File Picker Display & Removal:**
     - Replace separate red `[ Remove Receipt ]` button with native clearable `(✕)` behavior.
     - When no receipt is attached: label is `"Upload Receipt (.pdf, .png, .jpg)"`.
     - When a receipt is attached (either `existing_receipt_path` or `staged_receipt_file`): label is `"Replace Receipt (.pdf, .png, .jpg)"`. If an existing receipt is attached and no replacement file is chosen, display text indicates the attached receipt file name (e.g. `basename(existing_receipt_path)`).
     - Hook `@clear="onClearReceipt"` and `@update:model-value="onReceiptSelected"` to handle clearing and file selection.
  3. **Button Disabling & Loading:**
     - `[ View Receipt ]` disabled when `:disable="!hasReceipt || saving || isParsingReceipt"`.
     - `[ ✨ Scan with AI ]` disabled when `:disable="!hasReceipt || saving || isParsingReceipt"` with `:loading="isParsingReceipt"`.
  4. **Scan Execution (`onScanReceipt`):**
     - Sets `isParsingReceipt = true`.
     - If `form.staged_receipt_file` is present: invoke [`transactionStore.parseReceipt(form.staged_receipt_file)`](file:///D:/src/personal/wrangler/web/src/stores/transactions.ts#L219-L231) (`POST /api/receipts/parse`).
     - Else if `form.existing_receipt_path && !form.remove_receipt`: invoke `stagingStore.parseStagedReceipt(props.stagedTransaction.id)` (`POST /api/staging/{id}/parse-receipt`).
     - Update `aiSuggestions.value = computeAiSuggestions(res, form.value)`.
     - Show success notification `"Receipt parsed with AI"`.
     - On error, surface user-friendly notification without clearing input fields.
     - In `finally`, set `isParsingReceipt = false`.

### 3.2 Inline Field Suggestion & Match Banners
- **Target File:** [`web/src/components/StagedTransactionEditDialog.vue`](file:///D:/src/personal/wrangler/web/src/components/StagedTransactionEditDialog.vue)
- **Description:** Implement inline suggestion banners rendered directly beneath Date, Total Amount, and Description fields:
  1. **Reactive Suggestions State:**
     - Maintain `const aiSuggestions = ref<StagedAiSuggestionsState>(createInitialAiSuggestionsState())`.
     - Reset suggestions to `createInitialAiSuggestionsState()` on dialog open (in the `props.modelValue` watcher) and dialog close.
  2. **Banner Rendering (per field: `date`, `total_amount`, `description`):**
     - **Differing / Blank Value (`suggestion && !suggestion.isMatch && !suggestion.isDismissed`):**
       - Compact banner directly below `<q-input>` with sparkle icon and text `✨ AI Suggestion: {displayValue}` (prefixed by `$` for total amount).
       - Action button `[ ✓ Accept ]` (`data-testid="btn-accept-suggestion-{field}"`, flat dense color="positive" icon="check"). Clicking invokes `acceptAiSuggestion(form, aiSuggestions, field)`.
       - Action button `[ ✕ Dismiss ]` (`data-testid="btn-dismiss-suggestion-{field}"`, flat dense color="grey-7" icon="close"). Clicking invokes `dismissAiSuggestion(aiSuggestions, field)`.
     - **Exact Match (`suggestion && suggestion.isMatch && !suggestion.isDismissed`):**
       - Subtle green caption banner with text `✨ AI Match: {displayValue} (✓)` (`data-testid="match-indicator-{field}"`) without action buttons.
     - **Missing Value (`suggestion === null` or `suggestion.isDismissed`):**
       - No banner rendered.
  3. **Dialog Submission & Expose:**
     - Form save (`onSubmit`) validates and submits whatever values currently reside in form inputs; unaccepted suggestions are ignored.
     - Expose `aiSuggestions`, `isParsingReceipt`, `onScanReceipt`, and `onClearReceipt` via `defineExpose` for testing.

### 3.3 Component Template & Affordance Vitest Suite
- **Target File:** [`web/src/components/__tests__/stagedTransactionEdit.spec.ts`](file:///D:/src/personal/wrangler/web/src/components/__tests__/stagedTransactionEdit.spec.ts)
- **Description:** Add component template inspection tests (following the established pattern from [`BulkAllocateDialog.spec.ts`](file:///D:/src/personal/wrangler/web/src/components/__tests__/BulkAllocateDialog.spec.ts)) to verify:
  - `btn-staged-view-receipt` and `btn-staged-scan-receipt` are persistently rendered without conditional `v-if` toggles.
  - Buttons have `:disable` bindings that include `!hasReceipt`, `saving`, and `isParsingReceipt`.
  - The redundant `btn-staged-remove-receipt` button is eliminated.
  - Clearable file input triggers `onClearReceipt`.
  - Template includes suggestion rows and buttons with `data-testid` attributes: `btn-accept-suggestion-date`, `btn-dismiss-suggestion-date`, `match-indicator-date`, `btn-accept-suggestion-total_amount`, `btn-dismiss-suggestion-total_amount`, `match-indicator-total_amount`, `btn-accept-suggestion-description`, `btn-dismiss-suggestion-description`, `match-indicator-description`.
