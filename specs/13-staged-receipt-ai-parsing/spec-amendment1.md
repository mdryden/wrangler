---
status: Implemented
subsystems:
  - Staging Layer
  - Frontend UI/UX
amendments: []
supersedes: null
superseded_by: null
---

# Specification Amendment 1: Receipt-First Layout & Streamlined Staged Allocation Flow

**Target Specification:** [`specs/13-staged-receipt-ai-parsing/spec.md`](file:///D:/src/personal/wrangler/specs/13-staged-receipt-ai-parsing/spec.md)  
**Status:** Implemented  
**Subsystems:** Staging Layer & Frontend UI/UX  
**Date:** 2026-10-22  

---

## 1. Context & Motivation

In the initial implementation of [`specs/13-staged-receipt-ai-parsing/spec.md`](file:///D:/src/personal/wrangler/specs/13-staged-receipt-ai-parsing/spec.md), the Staged Transaction Edit Dialog (`StagedTransactionEditDialog.vue`) placed receipt attachment and scanning controls near the bottom of the form (below Date, Amount, Description, and Investigation URL).

During actual intake workflows, this layout introduced unnecessary visual and operational friction:
1. **Backwards Scan Flow:** Because OCR/AI parsing from the receipt directly generates suggestions for Date, Total Amount, and Description, placing the receipt below those fields forced users to scroll past blank inputs, attach a receipt, manually trigger scanning, and scroll back up to review suggestions.
2. **Missing Auto-Scan on Upload:** Attaching or replacing a file did not trigger extraction automatically when fields were empty, requiring an additional click on "Scan with AI".
3. **Unnecessary "Add Split" Step for Company Expenses:** Unallocated transactions opened with 0 splits (`splits: []`), requiring the user to locate and click "Add Split" merely to reveal the Company dropdown for a standard 100% single-company transaction.
4. **Header Clutter & Overlap:** The "Clear Allocations" button consumed excessive horizontal space in the allocations header, causing the subtext to wrap into the real-time balance chip.
5. **Accidental Deletion of the Only Split:** Deleting the single company split left the transaction unallocated with no visible fields, rather than enforcing a clean single-split baseline matching `ManualEntryView.vue`.

This amendment documents the refined receipt-first ergonomics and streamlined allocation flow.

---

## 2. Summary of Ergonomic & Architectural Changes

| Area | Prior Architecture (Spec 13) | Amended Architecture (Amendment 1) |
| :--- | :--- | :--- |
| **Receipt Form Position** | Row 4 (below URL, above Allocations). | **Row 1 (Top of Form):** Directly beneath dialog title/error banner, before Date and Amount. |
| **Receipt Button Order** | `[ File Input ] [ View Receipt ] [ Scan with AI ]` | `[ File Input ] [ Scan with AI ] [ View Receipt ]` |
| **Auto-Scan on Upload** | None (always manual click). | **Conditional Auto-Scan:** Automatically calls AI parse upon selecting/dropping a receipt file if any required field (`date`, `total_amount`, `description`) is empty/missing. Bypassed if fields are already complete. |
| **Initial Company Splits** | `splits: []` on unallocated staged transactions. | **Default 100% Split:** Initializes with 1 company split (`amount = total_amount`, `company_id = defaultCompanyId ?? null`). Auto-selects company if only one exists in workspace. |
| **"Add Split" Affordance** | Required to create the first split. | Reserved strictly for adding secondary splits (multi-company splits). |
| **Single Split Deletion** | Permitted (cleared back to 0 splits). | **Disabled (`:disable="splits.length <= 1"`):** Enforces at least 1 split. Tooltip: `"At least one split is required"`. "Personal Expense" toggle remains the single source of truth for personal attribution. |
| **Allocations Header** | Contained "Clear Allocations" button; overlapped balance chip on narrow widths. | Removed "Clear Allocations" button. Clean responsive flex columns (`col` and `col-auto` with `q-col-gutter-sm`) prevent text/chip collisions. |

---

## 3. Component & State Implementation

### 3.1 Conditional Auto-Scan Pure Helper (`web/src/components/stagedTransactionEdit.ts`)

```typescript
export function hasIncompleteStagedFields(state: StagedTransactionEditFormState): boolean {
  if (!state.date || !state.date.trim()) return true
  if (state.total_amount === "" || state.total_amount === null || state.total_amount === undefined) return true
  if (isNaN(Number(state.total_amount)) || Number(state.total_amount) === 0) return true
  if (!state.description || !state.description.trim()) return true
  return false
}
```

When a file is staged via `onReceiptSelected(file)`:
- If `file !== null && hasIncompleteStagedFields(form.value)`, triggers `onScanReceipt()`.
- If fields are already complete, stages the file quietly without overwriting or triggering background scans.

### 3.2 Default 100% Split Initialization (`web/src/components/stagedTransactionEdit.ts`)

```typescript
export function createStagedTransactionEditState(
  staged: StagedTransaction,
  defaultCompanyId: string | null = null,
): StagedTransactionEditFormState {
  const formattedTotal = formatAmount(staged.total_amount)
  const rawAllocations = staged.allocations ?? []

  let splits: EditableStagedSplitItem[]
  if (rawAllocations.length > 0) {
    splits = rawAllocations.map(alloc => ({
      id: alloc.id,
      amount: formatAmount(alloc.amount),
      is_personal: Boolean(alloc.is_personal),
      company_id: alloc.is_personal ? null : (alloc.company_id ?? null),
    }))
  } else {
    splits = [
      {
        amount: formattedTotal,
        is_personal: false,
        company_id: defaultCompanyId ?? null,
      },
    ]
  }

  const isPersonal = splits.length === 1 && splits[0].is_personal
  // ...
}
```

### 3.3 Guarding Split Removal (`web/src/components/stagedTransactionEdit.ts`)

```typescript
export function removeStagedEditSplit(state: StagedTransactionEditFormState, index: number): boolean {
  if (state.splits.length <= 1) {
    return false
  }
  if (index < 0 || index >= state.splits.length) {
    return false
  }
  state.splits.splice(index, 1)
  if (state.splits.length === 1) {
    state.splits[0].amount = state.total_amount
  }
  return true
}
```

---

## 4. Verification & Validation

1. **Unit & Spec Tests (`stagedTransactionEdit.test.ts`, `StagedTransactionEditDialog.spec.ts`):**
   - Asserts DOM ordering: `input-staged-receipt` precedes `staged-edit-input-date`.
   - Asserts button ordering: `btn-staged-scan-receipt` precedes `btn-staged-view-receipt`.
   - Asserts conditional auto-scan triggers when `hasIncompleteStagedFields` is true and does not trigger when fields are complete.
   - Asserts unallocated company transactions initialize with 1 split row and its delete button is disabled.
2. **Monorepo Checks:**
   - Full test suite passes cleanly (`pnpm test`).
   - Linting and format checks pass (`pnpm lint`, `pnpm format`).
