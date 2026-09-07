export interface ManualEntryFormState {
  date: string
  company_id: string
  description: string
  total_amount: string
  receipt_file: File | null
}

export const dateRules = [
  (val: string) => (!!val && val.trim().length > 0) || "Date is required",
  (val: string) => /^\d{4}-\d{2}-\d{2}$/.test(val) || "Date must be in YYYY-MM-DD format",
]

export const companyRules = [(val: string) => (!!val && val.trim().length > 0) || "Company is required"]

export const descriptionRules = [(val: string) => (!!val && val.trim().length > 0) || "Description / Payee is required"]

export const amountRules = [
  (val: string) => (val !== "" && val !== null && val !== undefined) || "Total amount is required",
  (val: string) => !isNaN(Number(val)) || "Must be a valid number",
  (val: string) => Number(val) !== 0 || "Amount must be strictly non-zero",
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

export function createInitialManualEntryState(): ManualEntryFormState {
  return {
    date: "",
    company_id: "",
    description: "",
    total_amount: "",
    receipt_file: null,
  }
}
