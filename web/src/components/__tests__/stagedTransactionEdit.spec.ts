import { describe, it, expect } from "vitest"
import {
  addStagedEditSplit,
  canSaveStagedTransactionEdit,
  clearStagedAllocations,
  createStagedTransactionEditState,
  hasEffectiveStagedReceipt,
  markStagedReceiptForRemoval,
  prepareStagedTransactionEditPayload,
  removeStagedEditSplit,
  stageStagedReceiptFile,
  syncSingleStagedSplitAmount,
  toggleStagedPersonalExpense,
} from "../stagedTransactionEdit"
import type { StagedTransaction } from "../../types/staging"

describe("stagedTransactionEdit", () => {
  const unallocatedStaged: StagedTransaction = {
    id: "stx-1",
    source: "wrangler_csv",
    external_id: "EXT-1",
    date: "2026-10-01",
    description: "Unallocated Staged Item",
    total_amount: "100.00",
    currency_code: "USD",
    receipt_file_path: "stx-1_receipt.pdf",
    status: "STAGED",
    is_marked_imported: false,
    ledger_transaction_id: null,
    created_at: "2026-10-01T10:00:00Z",
    allocations: [],
    is_ready: false,
    supports_mark_imported: false,
  }

  it("initializes unallocated rows with 0 splits and allows saving as unallocated", () => {
    const state = createStagedTransactionEditState(unallocatedStaged)
    expect(state.date).toBe("2026-10-01")
    expect(state.description).toBe("Unallocated Staged Item")
    expect(state.total_amount).toBe("100.00")
    expect(state.is_personal).toBe(false)
    expect(state.splits).toEqual([])
    expect(canSaveStagedTransactionEdit(state)).toBe(true)

    const { payload, stagedReceiptFile } = prepareStagedTransactionEditPayload(state)
    expect(stagedReceiptFile).toBeNull()
    expect(payload).toEqual({
      date: "2026-10-01",
      description: "Unallocated Staged Item",
      total_amount: "100.00",
      allocations: [],
    })
  })

  it("supports personal/business toggling from 0 or 1 split", () => {
    const state = createStagedTransactionEditState(unallocatedStaged)

    // Toggle to personal from 0 splits -> creates 1 personal split
    expect(toggleStagedPersonalExpense(state, true, "comp-1")).toBe(true)
    expect(state.is_personal).toBe(true)
    expect(state.splits).toEqual([
      {
        amount: "100.00",
        is_personal: true,
        company_id: null,
      },
    ])
    expect(canSaveStagedTransactionEdit(state)).toBe(true)

    // Toggle back to business -> assigns defaultCompanyId
    expect(toggleStagedPersonalExpense(state, false, "comp-1")).toBe(true)
    expect(state.is_personal).toBe(false)
    expect(state.splits[0].company_id).toBe("comp-1")
    expect(canSaveStagedTransactionEdit(state)).toBe(true)
  })

  it("validates multi-company splits, syncs single split amount, and supports clearing allocations", () => {
    const state = createStagedTransactionEditState(unallocatedStaged)

    // Add first split
    expect(addStagedEditSplit(state, "comp-1")).toBe(true)
    expect(state.splits).toHaveLength(1)
    expect(state.splits[0].amount).toBe("100.00")

    // Adjust split 0 to 60.00 -> unbalanced
    state.splits[0].amount = "60.00"
    expect(canSaveStagedTransactionEdit(state)).toBe(false)

    // Add second split -> pre-populated with 40.00 remainder
    expect(addStagedEditSplit(state, "comp-2")).toBe(true)
    expect(state.splits).toHaveLength(2)
    expect(state.splits[1].amount).toBe("40.00")
    expect(canSaveStagedTransactionEdit(state)).toBe(true)

    // Personal toggle is blocked when multiple splits exist
    expect(toggleStagedPersonalExpense(state, true)).toBe(false)

    // Remove second split -> remaining single split syncs to 100.00
    expect(removeStagedEditSplit(state, 1)).toBe(true)
    expect(state.splits).toHaveLength(1)
    expect(state.splits[0].amount).toBe("100.00")

    // Update total_amount -> syncs single split
    state.total_amount = "125.00"
    syncSingleStagedSplitAmount(state)
    expect(state.splits[0].amount).toBe("125.00")

    // Clear all allocations back to []
    clearStagedAllocations(state)
    expect(state.splits).toEqual([])
    expect(state.is_personal).toBe(false)
    expect(canSaveStagedTransactionEdit(state)).toBe(true)
  })

  it("handles receipt staging and removal in payload", () => {
    const state = createStagedTransactionEditState(unallocatedStaged)
    expect(hasEffectiveStagedReceipt(state)).toBe(true)

    markStagedReceiptForRemoval(state)
    expect(hasEffectiveStagedReceipt(state)).toBe(false)
    expect(prepareStagedTransactionEditPayload(state).payload.remove_receipt).toBe(true)

    const newFile = new File(["pdf"], "new.pdf", { type: "application/pdf" })
    stageStagedReceiptFile(state, newFile)
    expect(hasEffectiveStagedReceipt(state)).toBe(true)
    const { payload, stagedReceiptFile } = prepareStagedTransactionEditPayload(state)
    expect(stagedReceiptFile).toBe(newFile)
    expect(payload.remove_receipt).toBeUndefined()
  })
})
