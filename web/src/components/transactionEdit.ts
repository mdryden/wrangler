import type { AllocationUpdateItem, Transaction, TransactionUpdatePayload } from "../types/transaction"
import { calculateSplitRemainder, formatAmount } from "../views/manualEntry"

export const UNLOCK_WARNING_MESSAGE =
  "If this transaction has already been imported into an external accounting system, you must also adjust or remove it there manually."

export const PERSONAL_SPLIT_TOOLTIP = "Remove extra splits before marking this transaction as personal."

export const DELETE_LOCKED_TOOLTIP = "Unlock all locked allocations before deleting this transaction."

export interface EditableSplitItem {
  id?: string
  amount: string
  is_personal: boolean
  company_id: string | null
  is_locked: boolean
}

export interface TransactionEditFormState {
  date: string
  description: string
  total_amount: string
  is_personal: boolean
  existing_receipt_path: string | null
  staged_receipt_file: File | null
  remove_receipt: boolean
  splits: EditableSplitItem[]
}

export interface EditLockState {
  isFullyLocked: boolean
  isPartiallyLocked: boolean
  hasLockedSplits: boolean
  isDateDisabled: boolean
  isDescriptionDisabled: boolean
  isTotalAmountDisabled: boolean
  isPersonalToggleDisabled: boolean
  isAddSplitDisabled: boolean
}

/**
 Creates initial form state for TransactionEditDialog from a Transaction record.
 */
export function createTransactionEditState(tx: Transaction, defaultCompanyId: string | null = null): TransactionEditFormState {
  const formattedTotal = formatAmount(tx.total_amount)
  const rawAllocations = tx.allocations ?? []

  let splits: EditableSplitItem[]
  if (rawAllocations.length > 0) {
    splits = rawAllocations.map(alloc => ({
      id: alloc.id,
      amount: formatAmount(alloc.amount),
      is_personal: Boolean(alloc.is_personal),
      company_id: alloc.is_personal ? null : (alloc.company_id ?? null),
      is_locked: Boolean(alloc.is_locked),
    }))
  } else {
    splits = [
      {
        amount: formattedTotal,
        is_personal: false,
        company_id: defaultCompanyId,
        is_locked: false,
      },
    ]
  }

  const isPersonal = splits.length === 1 && splits[0].is_personal

  return {
    date: tx.date || "",
    description: tx.description || "",
    total_amount: formattedTotal,
    is_personal: isPersonal,
    existing_receipt_path: tx.receipt_file_path ?? null,
    staged_receipt_file: null,
    remove_receipt: false,
    splits,
  }
}

/**
 Computes lock flags and control disable states for the transaction editor.
 */
export function getEditLockState(state: TransactionEditFormState): EditLockState {
  const hasLockedSplits = state.splits.some(s => s.is_locked)
  const isFullyLocked = state.splits.length > 0 && state.splits.every(s => s.is_locked)
  const isPartiallyLocked = hasLockedSplits && !isFullyLocked

  return {
    isFullyLocked,
    isPartiallyLocked,
    hasLockedSplits,
    isDateDisabled: hasLockedSplits,
    isDescriptionDisabled: hasLockedSplits,
    isTotalAmountDisabled: isFullyLocked,
    isPersonalToggleDisabled: state.splits.length > 1 || hasLockedSplits,
    isAddSplitDisabled: isFullyLocked || state.is_personal,
  }
}

/**
 Toggles the personal expense flag when allowed (single unlocked allocation).
 */
export function togglePersonalExpense(
  state: TransactionEditFormState,
  isPersonal: boolean,
  defaultCompanyId: string | null = null,
): boolean {
  if (state.splits.length > 1 || state.splits.some(s => s.is_locked)) {
    return false
  }

  state.is_personal = isPersonal
  if (state.splits.length === 0) {
    state.splits.push({
      amount: state.total_amount,
      is_personal: isPersonal,
      company_id: isPersonal ? null : defaultCompanyId,
      is_locked: false,
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

/**
 Synchronizes split 0's amount with total_amount when there is only 1 unlocked split.
 */
export function syncSingleSplitAmount(state: TransactionEditFormState): void {
  if (state.splits.length === 1 && !state.splits[0].is_locked) {
    state.splits[0].amount = state.total_amount
  }
}

/**
 Adds a new business split row pre-populated with any unallocated remainder.
 */
export function addEditSplit(state: TransactionEditFormState, defaultCompanyId: string | null = null): boolean {
  const lockState = getEditLockState(state)
  if (lockState.isAddSplitDisabled) {
    return false
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
    is_locked: false,
  })
  return true
}

/**
 Removes an unlocked split row when more than one split exists.
 */
export function removeEditSplit(state: TransactionEditFormState, index: number): boolean {
  if (state.splits.length <= 1) {
    return false
  }
  const target = state.splits[index]
  if (!target || target.is_locked) {
    return false
  }

  state.splits.splice(index, 1)
  if (state.splits.length === 1 && !state.splits[0].is_locked) {
    state.splits[0].amount = state.total_amount
  }
  return true
}

/**
 Returns true if the transaction currently has an active receipt (existing and not marked for removal, or newly staged).
 */
export function hasEffectiveReceipt(state: TransactionEditFormState): boolean {
  return Boolean(state.staged_receipt_file !== null || (state.existing_receipt_path && !state.remove_receipt))
}

/**
 Returns true if a receipt upload/replacement or removal has been staged.
 */
export function hasReceiptChanges(state: TransactionEditFormState): boolean {
  return Boolean(state.staged_receipt_file !== null || (state.remove_receipt && state.existing_receipt_path !== null))
}

/**
 Stages a new or replacement receipt file.
 */
export function stageReceiptFile(state: TransactionEditFormState, file: File | null): void {
  state.staged_receipt_file = file
  if (file !== null) {
    state.remove_receipt = false
  }
}

/**
 Marks the current receipt for removal (or clears staged file).
 */
export function markReceiptForRemoval(state: TransactionEditFormState): void {
  state.staged_receipt_file = null
  if (state.existing_receipt_path !== null) {
    state.remove_receipt = true
  }
}

/**
 Validates whether the TransactionEditFormState can be submitted/saved.
 */
export function canSaveTransactionEdit(state: TransactionEditFormState): boolean {
  const lockState = getEditLockState(state)

  if (lockState.isFullyLocked) {
    return hasReceiptChanges(state)
  }

  if (!state.date || !/^\d{4}-\d{2}-\d{2}$/.test(state.date.trim())) {
    return false
  }
  if (!state.description || !state.description.trim()) {
    return false
  }
  if (state.total_amount === "" || isNaN(Number(state.total_amount)) || Number(state.total_amount) === 0) {
    return false
  }
  if (state.splits.length === 0) {
    return false
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

/**
 Builds the request payload (JSON or FormData) for PUT /api/transactions/{id}.
 */
export function prepareTransactionEditPayload(state: TransactionEditFormState): {
  isMultipart: boolean
  payload: FormData | TransactionUpdatePayload
} {
  const lockState = getEditLockState(state)

  if (lockState.isFullyLocked) {
    if (state.staged_receipt_file) {
      const fd = new FormData()
      fd.append("file", state.staged_receipt_file)
      return { isMultipart: true, payload: fd }
    }
    return {
      isMultipart: false,
      payload: {
        remove_receipt: Boolean(state.remove_receipt),
      },
    }
  }

  const formattedTotal = formatAmount(state.total_amount)
  const allocations: AllocationUpdateItem[] = state.splits.map(s => {
    const isPersonalSplit = state.splits.length === 1 ? state.is_personal || s.is_personal : false
    return {
      ...(s.id ? { id: s.id } : {}),
      amount: formatAmount(s.amount),
      is_personal: isPersonalSplit,
      company_id: isPersonalSplit ? null : s.company_id,
      is_locked: Boolean(s.is_locked),
    }
  })

  if (state.staged_receipt_file) {
    const fd = new FormData()
    if (!lockState.hasLockedSplits) {
      fd.append("date", state.date.trim())
      fd.append("description", state.description.trim())
    }
    fd.append("total_amount", formattedTotal)
    fd.append("allocations", JSON.stringify(allocations))
    fd.append("file", state.staged_receipt_file)
    return { isMultipart: true, payload: fd }
  }

  const payload: TransactionUpdatePayload = {
    total_amount: formattedTotal,
    allocations,
  }
  if (!lockState.hasLockedSplits) {
    payload.date = state.date.trim()
    payload.description = state.description.trim()
  }
  if (state.remove_receipt) {
    payload.remove_receipt = true
  }

  return { isMultipart: false, payload }
}
