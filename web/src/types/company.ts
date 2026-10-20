export interface Company {
  id: string
  name: string
  transaction_count?: number
  unlocked_allocation_count?: number
  unlocked_amount_total?: string | number
  locked_allocation_count?: number
  wave_business_id?: string | null
  wave_business_name?: string | null
  wave_equity_account_id?: string | null
  is_wave_connected?: boolean
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
