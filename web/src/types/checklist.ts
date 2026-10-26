export interface ChecklistConfig {
  company_id: string | null
  company_name: string | null
  is_wave_connected: boolean
  chequing_wave_account_id: string | null
  chequing_wave_account_name: string | null
  mastercard_wave_account_id: string | null
  mastercard_wave_account_name: string | null
  tax_expense_wave_account_id: string | null
  tax_expense_wave_account_name: string | null
  tax_payable_wave_account_id: string | null
  tax_payable_wave_account_name: string | null
  wave_web_business_slug: string
  last_chequing_tx_date: string | null
  last_mastercard_tx_date: string | null
}

export interface ChecklistConfigUpdatePayload {
  company_id?: string | null
  chequing_wave_account_id?: string | null
  chequing_wave_account_name?: string | null
  mastercard_wave_account_id?: string | null
  mastercard_wave_account_name?: string | null
  tax_expense_wave_account_id?: string | null
  tax_expense_wave_account_name?: string | null
  tax_payable_wave_account_id?: string | null
  tax_payable_wave_account_name?: string | null
  wave_web_business_slug?: string
  last_chequing_tx_date?: string | null
  last_mastercard_tx_date?: string | null
}

export interface WaveAccountItem {
  id: string
  name: string
  type: string
  subtype?: string | null
  is_uncategorized?: boolean
}

export interface WaveAccountsGrouped {
  bank_and_cc_accounts: WaveAccountItem[]
  expense_accounts: WaveAccountItem[]
  liability_accounts: WaveAccountItem[]
}

export interface MonthlyChecklist {
  id: string
  year_month: string
  completed_steps: string[]
  net_operating_cash: string | number | null
  tax_rate: string | number
  tax_reserve_amount: string | number | null
  tax_accrual_wave_tx_id: string | null
  prior_soft_cap: string | number
  monthly_loc_reduction: string | number
  current_soft_cap: string | number
  tax_liability: string | number | null
  actual_loc_balance: string | number | null
  maximum_safe_draw: string | number | null
  wave_cash_flow_url: string
}

export interface MonthlyChecklistPatchPayload {
  completed_steps?: string[]
  net_operating_cash?: string | number | null
  tax_rate?: string | number | null
  prior_soft_cap?: string | number | null
  monthly_loc_reduction?: string | number | null
  tax_liability?: string | number | null
  actual_loc_balance?: string | number | null
}

export interface RbcCsvSyncResult {
  total_rows: number
  synced_count: number
  failed_count: number
  auto_categorized_count: number
  uncategorized_count: number
  latest_transaction_date: string | null
  errors: string[]
}

export interface TaxAccrualSyncPayload {
  net_operating_cash?: string | number | null
  tax_rate?: string | number | null
}
