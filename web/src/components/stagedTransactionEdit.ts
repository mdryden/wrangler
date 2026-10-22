import type { StagedAllocationInput, StagedTransaction, StagedTransactionUpdatePayload } from "../types/staging"
import type { ReceiptParseResponse } from "../types/transaction"
import { calculateSplitRemainder, formatAmount } from "../views/manualEntry"

export interface EditableStagedSplitItem {
  id?: string
  amount: string
  is_personal: boolean
  company_id: string | null
}

export interface StagedTransactionEditFormState {
  date: string
  description: string
  total_amount: string
  url: string
  is_personal: boolean
  existing_receipt_path: string | null
  staged_receipt_file: File | null
  remove_receipt: boolean
  splits: EditableStagedSplitItem[]
}

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
    // Default to a single company split for standard company transaction (no 'Add Split' click required)
    splits = [
      {
        amount: formattedTotal,
        is_personal: false,
        company_id: defaultCompanyId ?? null,
      },
    ]
  }

  const isPersonal = splits.length === 1 && splits[0].is_personal

  return {
    date: staged.date || "",
    description: staged.description || "",
    total_amount: formattedTotal,
    url: staged.url || "",
    is_personal: isPersonal,
    existing_receipt_path: staged.receipt_file_path ?? null,
    staged_receipt_file: null,
    remove_receipt: false,
    splits,
  }
}

/**
 * Checks whether core transaction fields (date, amount, description) have missing or empty values.
 * Used to conditionally auto-trigger AI receipt scanning only when required fields need population.
 */
export function hasIncompleteStagedFields(state: StagedTransactionEditFormState): boolean {
  if (!state.date || !state.date.trim()) return true
  if (state.total_amount === "" || state.total_amount === null || state.total_amount === undefined) return true
  if (isNaN(Number(state.total_amount)) || Number(state.total_amount) === 0) return true
  if (!state.description || !state.description.trim()) return true
  return false
}

export function syncSingleStagedSplitAmount(state: StagedTransactionEditFormState): void {
  if (state.splits.length === 1) {
    state.splits[0].amount = state.total_amount
  }
}

export function toggleStagedPersonalExpense(
  state: StagedTransactionEditFormState,
  isPersonal: boolean,
  defaultCompanyId: string | null = null,
): boolean {
  if (state.splits.length > 1) {
    return false
  }

  state.is_personal = isPersonal
  if (state.splits.length === 0) {
    state.splits.push({
      amount: state.total_amount,
      is_personal: isPersonal,
      company_id: isPersonal ? null : defaultCompanyId,
    })
  } else {
    state.splits[0].is_personal = isPersonal
    state.splits[0].amount = state.total_amount
    if (isPersonal) {
      state.splits[0].company_id = null
    } else if (!state.splits[0].company_id && defaultCompanyId) {
      state.splits[0].company_id = defaultCompanyId
    }
  }
  return true
}

export function addStagedEditSplit(state: StagedTransactionEditFormState, defaultCompanyId: string | null = null): boolean {
  if (state.is_personal) {
    return false
  }

  if (state.splits.length === 0) {
    state.splits.push({
      amount: state.total_amount,
      is_personal: false,
      company_id: defaultCompanyId,
    })
    return true
  }

  const rem = calculateSplitRemainder(state.total_amount, state.splits)
  let initialAmount = ""
  if (rem.remainderCents !== 0 && !isNaN(Number(rem.remainderFormatted))) {
    initialAmount = rem.remainderFormatted
  }

  state.splits.push({
    amount: initialAmount,
    is_personal: false,
    company_id: defaultCompanyId,
  })
  return true
}

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

export function clearStagedAllocations(state: StagedTransactionEditFormState): void {
  state.splits = []
  state.is_personal = false
}

export function hasEffectiveStagedReceipt(state: StagedTransactionEditFormState): boolean {
  return Boolean(state.staged_receipt_file !== null || (state.existing_receipt_path && !state.remove_receipt))
}

export function stageStagedReceiptFile(state: StagedTransactionEditFormState, file: File | null): void {
  state.staged_receipt_file = file
  if (file !== null) {
    state.remove_receipt = false
  }
}

export function markStagedReceiptForRemoval(state: StagedTransactionEditFormState): void {
  state.staged_receipt_file = null
  if (state.existing_receipt_path !== null) {
    state.remove_receipt = true
  }
}

export function canSaveStagedTransactionEdit(state: StagedTransactionEditFormState): boolean {
  if (!state.date || !/^\d{4}-\d{2}-\d{2}$/.test(state.date.trim())) {
    return false
  }
  const isPersonal = state.is_personal || (state.splits.length === 1 && state.splits[0].is_personal)
  if (!isPersonal && (!state.description || !state.description.trim())) {
    return false
  }
  if (state.total_amount === "" || isNaN(Number(state.total_amount)) || Number(state.total_amount) === 0) {
    return false
  }

  // Zero splits (Unallocated) is allowed when saving a staged transaction
  if (state.splits.length === 0) {
    return true
  }

  const remainder = calculateSplitRemainder(state.total_amount, state.splits)
  if (!remainder.isBalanced || remainder.remainderCents !== 0) {
    return false
  }

  if (state.splits.length > 1 && (state.is_personal || state.splits.some(s => s.is_personal))) {
    return false
  }

  for (const s of state.splits) {
    const isPersonalSplit = state.is_personal || s.is_personal
    if (!isPersonalSplit && (!s.company_id || !String(s.company_id).trim())) {
      return false
    }
    if (s.amount === "" || isNaN(Number(s.amount)) || Number(s.amount) === 0) {
      return false
    }
  }

  return true
}

export function prepareStagedTransactionEditPayload(state: StagedTransactionEditFormState): {
  payload: StagedTransactionUpdatePayload
  stagedReceiptFile: File | null
} {
  const formattedTotal = formatAmount(state.total_amount)
  const allocations: StagedAllocationInput[] = state.splits.map(s => {
    const isPersonalSplit = state.splits.length === 1 ? state.is_personal || s.is_personal : false
    return {
      ...(s.id ? { id: s.id } : {}),
      amount: formatAmount(s.amount),
      is_personal: isPersonalSplit,
      company_id: isPersonalSplit ? null : s.company_id,
    }
  })

  const payload: StagedTransactionUpdatePayload = {
    date: state.date.trim(),
    description: state.description.trim() || null,
    total_amount: formattedTotal,
    allocations,
    url: state.url?.trim() || null,
  }

  if (state.remove_receipt) {
    payload.remove_receipt = true
  }

  return {
    payload,
    stagedReceiptFile: state.staged_receipt_file,
  }
}

export interface FieldSuggestion<T = string> {
  extractedValue: T
  displayValue: string
  isMatch: boolean
  isDismissed: boolean
}

export interface StagedAiSuggestionsState {
  date: FieldSuggestion<string> | null
  total_amount: FieldSuggestion<string> | null
  description: FieldSuggestion<string> | null
}

export function createInitialAiSuggestionsState(): StagedAiSuggestionsState {
  return {
    date: null,
    total_amount: null,
    description: null,
  }
}

export function computeAiSuggestions(parseResult: ReceiptParseResponse, form: StagedTransactionEditFormState): StagedAiSuggestionsState {
  let dateSuggestion: FieldSuggestion<string> | null = null
  if (parseResult.date && parseResult.date.trim()) {
    const aiDate = parseResult.date.trim()
    const isMatch = Boolean(form.date && form.date.trim() === aiDate)
    dateSuggestion = {
      extractedValue: aiDate,
      displayValue: aiDate,
      isMatch,
      isDismissed: false,
    }
  }

  let amountSuggestion: FieldSuggestion<string> | null = null
  if (parseResult.total_amount !== null && parseResult.total_amount !== undefined && String(parseResult.total_amount).trim() !== "") {
    const aiAmountStr = formatAmount(parseResult.total_amount)
    const isMatch = Boolean(
      form.total_amount &&
      !isNaN(Number(form.total_amount)) &&
      !isNaN(Number(parseResult.total_amount)) &&
      Number(form.total_amount).toFixed(2) === Number(parseResult.total_amount).toFixed(2),
    )
    amountSuggestion = {
      extractedValue: aiAmountStr,
      displayValue: aiAmountStr,
      isMatch,
      isDismissed: false,
    }
  }

  let descSuggestion: FieldSuggestion<string> | null = null
  if (parseResult.description && parseResult.description.trim()) {
    const aiDesc = parseResult.description.trim()
    const isMatch = Boolean(form.description && form.description.trim().toLowerCase() === aiDesc.toLowerCase())
    descSuggestion = {
      extractedValue: aiDesc,
      displayValue: aiDesc,
      isMatch,
      isDismissed: false,
    }
  }

  return {
    date: dateSuggestion,
    total_amount: amountSuggestion,
    description: descSuggestion,
  }
}

export function acceptAiSuggestion(
  form: StagedTransactionEditFormState,
  suggestions: StagedAiSuggestionsState,
  field: "date" | "total_amount" | "description",
): void {
  if (field === "date" && suggestions.date) {
    form.date = suggestions.date.extractedValue
    suggestions.date.isMatch = true
  } else if (field === "total_amount" && suggestions.total_amount) {
    form.total_amount = formatAmount(suggestions.total_amount.extractedValue)
    syncSingleStagedSplitAmount(form)
    suggestions.total_amount.isMatch = true
  } else if (field === "description" && suggestions.description) {
    form.description = suggestions.description.extractedValue
    suggestions.description.isMatch = true
  }
}

export function dismissAiSuggestion(suggestions: StagedAiSuggestionsState, field: "date" | "total_amount" | "description"): void {
  if (suggestions[field]) {
    suggestions[field]!.isDismissed = true
  }
}

export function clearStagedReceipt(state: StagedTransactionEditFormState, suggestions?: StagedAiSuggestionsState): void {
  state.staged_receipt_file = null
  if (state.existing_receipt_path !== null) {
    state.remove_receipt = true
  }
  if (suggestions) {
    suggestions.date = null
    suggestions.total_amount = null
    suggestions.description = null
  }
}
