export type SyncStatus = "PENDING" | "SYNCED"

export interface Allocation {
  id: string
  transaction_id: string
  amount: string | number
  is_personal: boolean
  company_id: string | null
  sync_status: SyncStatus
}

export interface Transaction {
  id: string
  source: string
  external_id: string | null
  date: string
  description: string
  total_amount: string | number
  currency_code: string
  receipt_file_path: string | null
  is_approved: boolean
  allocations: Allocation[]
}

export interface PaginatedTransactionsResponse {
  items: Transaction[]
  total: number
  page: number
  page_size: number
  total_pages: number
}

export interface TransactionFilterParams {
  source?: string
  is_approved?: boolean | null
  start_date?: string
  end_date?: string
  company_id?: string | null
}

export interface TransactionQueryParams extends TransactionFilterParams {
  page?: number
  page_size?: number
  rowsPerPage?: number
  sort_by?: string
  sortBy?: string
  descending?: boolean
  order?: "asc" | "desc"
}
