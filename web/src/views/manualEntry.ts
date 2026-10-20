import type { ReceiptParseResponse, TransactionCreatePayload } from "../types/transaction"

export interface ManualSplitItem {
  id?: string
  company_id: string
  amount: string
}

export interface ManualEntryFormState {
  date: string
  description: string
  total_amount: string
  receipt_file: File | null
  splits: ManualSplitItem[]
}

export const dateRules = [
  (val: string) => (!!val && val.trim().length > 0) || "Date is required",
  (val: string) => /^\d{4}-\d{2}-\d{2}$/.test(val) || "Date must be in YYYY-MM-DD format",
]

export const descriptionRules = [(val: string) => (!!val && val.trim().length > 0) || "Description / Payee is required"]

export const amountRules = [
  (val: string) => (val !== "" && val !== null && val !== undefined) || "Total amount is required",
  (val: string) => !isNaN(Number(val)) || "Must be a valid number",
  (val: string) => Number(val) !== 0 || "Amount must be strictly non-zero",
]

export const splitCompanyRules = [(val: string) => (!!val && val.trim().length > 0) || "Split company is required"]

export const splitAmountRules = [
  (val: string) => (val !== "" && val !== null && val !== undefined) || "Split amount is required",
  (val: string) => !isNaN(Number(val)) || "Must be a valid number",
  (val: string) => Number(val) !== 0 || "Split amount must be strictly non-zero",
]

export function formatAmount(val: string | number): string {
  if (val !== "" && val !== null && val !== undefined && !isNaN(Number(val))) {
    const num = Number(val)
    if (num !== 0) {
      return num.toFixed(2)
    }
  }
  return String(val ?? "")
}

/**
 * Converts a numeric string or number to an integer number of cents.
 * Returns null if the value is empty or not a valid number.
 */
export function toCents(val: string | number): number | null {
  if (val === "" || val === null || val === undefined) return null
  const num = Number(val)
  if (isNaN(num)) return null
  return Math.round(num * 100)
}

export interface SplitRemainderResult {
  remainderCents: number
  remainderFormatted: string
  isBalanced: boolean
}

/**
 * Calculates the remainder: Total Amount - sum(splits).
 * Returns balance status and formatted remainder string.
 */
export function calculateSplitRemainder(totalAmount: string | number, splits: Array<{ amount: string | number }>): SplitRemainderResult {
  const totalCents = toCents(totalAmount)
  if (totalCents === null || totalCents === 0) {
    return { remainderCents: 0, remainderFormatted: "0.00", isBalanced: false }
  }

  if (!splits || splits.length === 0) {
    return {
      remainderCents: totalCents,
      remainderFormatted: (totalCents / 100).toFixed(2),
      isBalanced: false,
    }
  }

  let splitsSumCents = 0
  let hasIncompleteSplit = false
  for (const s of splits) {
    const sCents = toCents(s.amount)
    if (sCents === null || sCents === 0) {
      hasIncompleteSplit = true
    } else {
      splitsSumCents += sCents
    }
  }

  const remainderCents = totalCents - splitsSumCents
  const isBalanced = !hasIncompleteSplit && remainderCents === 0
  const remainderFormatted = (remainderCents / 100).toFixed(2)

  return {
    remainderCents,
    remainderFormatted,
    isBalanced,
  }
}

/**
 * Returns today's date formatted as YYYY-MM-DD in local time.
 */
export function getTodayDateString(date = new Date()): string {
  const year = date.getFullYear()
  const month = String(date.getMonth() + 1).padStart(2, "0")
  const day = String(date.getDate()).padStart(2, "0")
  return `${year}-${month}-${day}`
}

export function createInitialManualEntryState(companyId = ""): ManualEntryFormState {
  return {
    date: "",
    description: "",
    total_amount: "",
    receipt_file: null,
    splits: [
      {
        company_id: companyId,
        amount: "",
      },
    ],
  }
}

/**
 * Prepares the transaction submission payload as FormData (if receipt attached)
 * or JSON TransactionCreatePayload.
 */
export function prepareTransactionPayload(form: ManualEntryFormState): {
  isMultipart: boolean
  payload: FormData | TransactionCreatePayload
} {
  const allocations = form.splits.map(s => ({
    company_id: s.company_id,
    amount: s.amount,
    is_personal: false,
    is_locked: false,
  }))

  if (form.receipt_file) {
    const fd = new FormData()
    fd.append("date", form.date)
    fd.append("description", form.description)
    fd.append("total_amount", form.total_amount)
    fd.append("source", "manual")
    fd.append("receipt", form.receipt_file)
    fd.append("allocations", JSON.stringify(allocations))
    return { isMultipart: true, payload: fd }
  }

  const jsonPayload: TransactionCreatePayload = {
    date: form.date,
    description: form.description,
    total_amount: form.total_amount,
    source: "manual",
    allocations,
  }
  return { isMultipart: false, payload: jsonPayload }
}

/**
 * Cascades parsed receipt fields downward into manual entry form state.
 */
export function applyParsedReceiptToForm(form: ManualEntryFormState, parsed: ReceiptParseResponse): void {
  if (parsed.date) {
    form.date = parsed.date
  }
  if (parsed.description) {
    form.description = parsed.description
  } else if (parsed.merchant) {
    form.description = parsed.merchant
  }
  if (parsed.total_amount !== null && parsed.total_amount !== undefined) {
    form.total_amount = String(parsed.total_amount)
    if (form.splits.length === 1) {
      form.splits[0].amount = String(parsed.total_amount)
    }
  }
}

/**
 * Focuses the Date input element on mount or form reset for keyboard-first workflow.
 */
export function focusDateInputElement(inputRef: { focus?: () => void; $el?: HTMLElement } | null | undefined): void {
  if (!inputRef) return
  if (typeof inputRef.focus === "function") {
    inputRef.focus()
  } else {
    const inputEl = inputRef.$el?.querySelector("input")
    inputEl?.focus()
  }
}

/**
 * Checks whether a selected file is a PDF based on MIME type or filename extension.
 */
export function isPdfFile(file: File | null): boolean {
  if (!file) return false
  return file.type === "application/pdf" || file.name.toLowerCase().endsWith(".pdf")
}

/**
 * Creates an object URL for a file and opens it in a new window/tab.
 */
export function openBlobPreview(file: File): string {
  const blobUrl = URL.createObjectURL(file)
  if (typeof window !== "undefined" && typeof window.open === "function") {
    window.open(blobUrl, "_blank")
  } else if (typeof globalThis.open === "function") {
    globalThis.open(blobUrl, "_blank")
  }
  return blobUrl
}
