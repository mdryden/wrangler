export interface WaveBusiness {
  id: string
  name: string
  is_personal: boolean
}

export interface WaveAccount {
  id: string
  name: string
  type: string
  subtype?: string | null
  is_uncategorized?: boolean
}

export interface WaveBusinessAccountsResponse {
  anchor_accounts: WaveAccount[]
  expense_categories: WaveAccount[]
}

export interface WaveConnectPayload {
  token: string
  business_id: string
  business_name: string
  equity_account_id: string
}

export interface WaveCategory {
  id: string
  company_id: string
  wave_account_id: string
  name: string
  account_type: string
  account_subtype?: string | null
  is_uncategorized: boolean
}

export interface WaveSyncErrorItem {
  allocation_id: string
  description: string
  error: string
}

export interface WaveSyncResponse {
  total_processed: number
  synced_count: number
  failed_count: number
  errors: WaveSyncErrorItem[]
}
