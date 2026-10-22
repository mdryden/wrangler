import fs from "fs"
import path from "path"
import { describe, it, expect } from "vitest"
import {
  acceptAiSuggestion,
  addStagedEditSplit,
  canSaveStagedTransactionEdit,
  clearStagedAllocations,
  clearStagedReceipt,
  computeAiSuggestions,
  createInitialAiSuggestionsState,
  createStagedTransactionEditState,
  dismissAiSuggestion,
  hasEffectiveStagedReceipt,
  markStagedReceiptForRemoval,
  prepareStagedTransactionEditPayload,
  removeStagedEditSplit,
  stageStagedReceiptFile,
  syncSingleStagedSplitAmount,
  toggleStagedPersonalExpense,
} from "../stagedTransactionEdit"
import type { StagedTransaction } from "../../types/staging"
import type { ReceiptParseResponse } from "../../types/transaction"

describe("stagedTransactionEdit", () => {
  const unallocatedStaged: StagedTransaction = {
    id: "stx-1",
    source: "wrangler_csv",
    external_id: "EXT-1",
    date: "2026-10-01",
    description: "Unallocated Staged Item",
    total_amount: "100.00",
    receipt_file_path: "stx-1_receipt.pdf",
    url: null,
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
    expect(state.url).toBe("")
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
      url: null,
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

  it("initializes and prepares investigation URL properly", () => {
    const stagedWithUrl: StagedTransaction = {
      ...unallocatedStaged,
      url: "https://amazon.ca/orders/123",
    }
    const state = createStagedTransactionEditState(stagedWithUrl)
    expect(state.url).toBe("https://amazon.ca/orders/123")

    // Trimmed URL in payload
    state.url = "   https://amazon.ca/orders/456   "
    expect(prepareStagedTransactionEditPayload(state).payload.url).toBe("https://amazon.ca/orders/456")

    // Empty or whitespace URL converted to null in payload
    state.url = "   "
    expect(prepareStagedTransactionEditPayload(state).payload.url).toBeNull()

    state.url = ""
    expect(prepareStagedTransactionEditPayload(state).payload.url).toBeNull()
  })

  it("computes AI suggestions correctly for date, total_amount, and description", () => {
    const state = createStagedTransactionEditState(unallocatedStaged)
    state.date = "2026-10-14"
    state.total_amount = "29.99"
    state.description = ""

    const parseResult: ReceiptParseResponse = {
      merchant: "Amazon",
      date: "2026-10-15",
      total_amount: 29.99,
      description: "Amazon - Anker Cable",
    }

    const suggestions = computeAiSuggestions(parseResult, state)

    // Differing date
    expect(suggestions.date).toEqual({
      extractedValue: "2026-10-15",
      displayValue: "2026-10-15",
      isMatch: false,
      isDismissed: false,
    })

    // Identical amount
    expect(suggestions.total_amount).toEqual({
      extractedValue: "29.99",
      displayValue: "29.99",
      isMatch: true,
      isDismissed: false,
    })

    // Differing description (empty form description vs AI value)
    expect(suggestions.description).toEqual({
      extractedValue: "Amazon - Anker Cable",
      displayValue: "Amazon - Anker Cable",
      isMatch: false,
      isDismissed: false,
    })

    // Missing / null AI fields produce null suggestions
    const emptyResult: ReceiptParseResponse = {
      merchant: null,
      date: null,
      total_amount: null,
      description: null,
    }
    const emptySuggestions = computeAiSuggestions(emptyResult, state)
    expect(emptySuggestions.date).toBeNull()
    expect(emptySuggestions.total_amount).toBeNull()
    expect(emptySuggestions.description).toBeNull()
  })

  it("accepts AI suggestions and updates form inputs and single split allocations", () => {
    const state = createStagedTransactionEditState(unallocatedStaged)
    state.splits = [
      {
        amount: "100.00",
        is_personal: false,
        company_id: "comp-1",
      },
    ]

    const suggestions = {
      date: {
        extractedValue: "2026-10-15",
        displayValue: "2026-10-15",
        isMatch: false,
        isDismissed: false,
      },
      total_amount: {
        extractedValue: "49.99",
        displayValue: "49.99",
        isMatch: false,
        isDismissed: false,
      },
      description: {
        extractedValue: "Amazon - New Mouse",
        displayValue: "Amazon - New Mouse",
        isMatch: false,
        isDismissed: false,
      },
    }

    acceptAiSuggestion(state, suggestions, "date")
    expect(state.date).toBe("2026-10-15")
    expect(suggestions.date.isMatch).toBe(true)

    acceptAiSuggestion(state, suggestions, "total_amount")
    expect(state.total_amount).toBe("49.99")
    expect(state.splits[0].amount).toBe("49.99")
    expect(suggestions.total_amount.isMatch).toBe(true)

    acceptAiSuggestion(state, suggestions, "description")
    expect(state.description).toBe("Amazon - New Mouse")
    expect(suggestions.description.isMatch).toBe(true)
  })

  it("dismisses AI suggestions without modifying form inputs", () => {
    const state = createStagedTransactionEditState(unallocatedStaged)
    state.date = "2026-10-14"

    const suggestions = {
      date: {
        extractedValue: "2026-10-15",
        displayValue: "2026-10-15",
        isMatch: false,
        isDismissed: false,
      },
      total_amount: null,
      description: null,
    }

    dismissAiSuggestion(suggestions, "date")
    expect(suggestions.date.isDismissed).toBe(true)
    expect(state.date).toBe("2026-10-14")
  })

  it("clears staged receipt and active suggestions state", () => {
    const state = createStagedTransactionEditState(unallocatedStaged)
    const suggestions = {
      date: {
        extractedValue: "2026-10-15",
        displayValue: "2026-10-15",
        isMatch: false,
        isDismissed: false,
      },
      total_amount: {
        extractedValue: "49.99",
        displayValue: "49.99",
        isMatch: false,
        isDismissed: false,
      },
      description: {
        extractedValue: "Test",
        displayValue: "Test",
        isMatch: false,
        isDismissed: false,
      },
    }

    clearStagedReceipt(state, suggestions)
    expect(state.staged_receipt_file).toBeNull()
    expect(state.remove_receipt).toBe(true)
    expect(suggestions.date).toBeNull()
    expect(suggestions.total_amount).toBeNull()
    expect(suggestions.description).toBeNull()
  })

  describe("StagedTransactionEditDialog Template & UI Affordances", () => {
    const dialogPath = path.resolve(__dirname, "../StagedTransactionEditDialog.vue")
    const dialogTemplate = fs.readFileSync(dialogPath, "utf-8")

    it("persistently renders receipt buttons without conditional v-if toggles", () => {
      expect(dialogTemplate).toContain('data-testid="btn-staged-view-receipt"')
      expect(dialogTemplate).toContain('data-testid="btn-staged-scan-receipt"')
      expect(dialogTemplate).not.toContain('data-testid="btn-staged-remove-receipt"')

      // Verify buttons do not have v-if
      const viewBtnRegex = /<q-btn[^>]*data-testid="btn-staged-view-receipt"[^>]*\/>/s
      const scanBtnRegex = /<q-btn[^>]*data-testid="btn-staged-scan-receipt"[^>]*\/>/s

      const viewMatch = dialogTemplate.match(viewBtnRegex)
      expect(viewMatch).not.toBeNull()
      expect(viewMatch![0]).not.toContain("v-if")
      expect(viewMatch![0]).toContain(':disable="!hasReceipt || saving || isParsingReceipt"')

      const scanMatch = dialogTemplate.match(scanBtnRegex)
      expect(scanMatch).not.toBeNull()
      expect(scanMatch![0]).not.toContain("v-if")
      expect(scanMatch![0]).toContain(':disable="!hasReceipt || saving || isParsingReceipt"')
      expect(scanMatch![0]).toContain(':loading="isParsingReceipt"')
    })

    it("configures clearable file picker to invoke onClearReceipt", () => {
      const fileInputRegex = /<q-file[^>]*data-testid="input-staged-receipt"[^>]*>/s
      const fileMatch = dialogTemplate.match(fileInputRegex)
      expect(fileMatch).not.toBeNull()
      expect(fileMatch![0]).toContain("clearable")
      expect(fileMatch![0]).toContain('@clear="onClearReceipt"')
    })

    it("includes inline suggestion and match banners for date, total_amount, and description", () => {
      // Date suggestion and match elements
      expect(dialogTemplate).toContain('data-testid="btn-accept-suggestion-date"')
      expect(dialogTemplate).toContain('data-testid="btn-dismiss-suggestion-date"')
      expect(dialogTemplate).toContain('data-testid="match-indicator-date"')

      // Total amount suggestion and match elements
      expect(dialogTemplate).toContain('data-testid="btn-accept-suggestion-total_amount"')
      expect(dialogTemplate).toContain('data-testid="btn-dismiss-suggestion-total_amount"')
      expect(dialogTemplate).toContain('data-testid="match-indicator-total_amount"')

      // Description suggestion and match elements
      expect(dialogTemplate).toContain('data-testid="btn-accept-suggestion-description"')
      expect(dialogTemplate).toContain('data-testid="btn-dismiss-suggestion-description"')
      expect(dialogTemplate).toContain('data-testid="match-indicator-description"')
    })

    it("configures investigation URL open button with click propagation stopped and link attributes", () => {
      const urlInputRegex = /<q-input[^>]*data-testid="input-staged-url"[^>]*>([\s\S]*?)<\/q-input>/
      const inputMatch = dialogTemplate.match(urlInputRegex)
      expect(inputMatch).not.toBeNull()
      const appendSlotContent = inputMatch![1]

      // Must have open URL button with stop propagation so Quasar's append slot does not cancel navigation
      expect(appendSlotContent).toContain('data-testid="btn-open-url"')
      expect(appendSlotContent).toContain("@click.stop")
      expect(appendSlotContent).toContain('target="_blank"')
      expect(appendSlotContent).toContain('rel="noopener noreferrer"')
      expect(appendSlotContent).toContain("<q-tooltip>Open URL</q-tooltip>")
    })
  })
})
