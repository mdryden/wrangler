export interface Company {
  id: string
  name: string
  transaction_count?: number
  unlocked_allocation_count?: number
  unlocked_amount_total?: string | number
  locked_allocation_count?: number
}

export interface CompanyCreatePayload {
  name: string
}

export interface CompanyUpdatePayload {
  name?: string
}

export interface CompanyExportOptions {
  include_locked?: boolean
  start_date?: string
  end_date?: string
}
