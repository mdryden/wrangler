import type { StagedAllocationInput, StagedTransaction, StagedTransactionUpdatePayload } from "../types/staging"
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

export function createStagedTransactionEditState(staged: StagedTransaction): StagedTransactionEditFormState {
  const formattedTotal = formatAmount(staged.total_amount)
  const rawAllocations = staged.allocations ?? []

  const splits: EditableStagedSplitItem[] = rawAllocations.map(alloc => ({
    id: alloc.id,
    amount: formatAmount(alloc.amount),
    is_personal: Boolean(alloc.is_personal),
    company_id: alloc.is_personal ? null : (alloc.company_id ?? null),
  }))

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
  if (index < 0 || index >= state.splits.length) {
    return false
  }

  state.splits.splice(index, 1)
  if (state.splits.length === 0) {
    state.is_personal = false
  } else if (state.splits.length === 1) {
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
  if (!state.description || !state.description.trim()) {
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
    description: state.description.trim(),
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
