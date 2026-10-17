export interface AllocationCreateItem {
  id?: string
  amount: string | number
  is_personal?: boolean
  company_id?: string | null
  is_locked?: boolean
}

export interface AllocationUpdateItem {
  id?: string
  amount: string | number
  is_personal?: boolean
  company_id?: string | null
  is_locked?: boolean
}

export interface TransactionCreatePayload {
  date: string
  description: string
  total_amount: string | number
  currency_code?: string
  source?: string
  external_id?: string | null
  company_id?: string | null
  allocations: AllocationCreateItem[]
}

export interface TransactionUpdatePayload {
  date?: string
  description?: string
  total_amount?: string | number
  currency_code?: string
  source?: string
  external_id?: string | null
  receipt_file_path?: string | null
  allocations?: AllocationUpdateItem[]
  remove_receipt?: boolean
}

export interface Allocation {
  id: string
  transaction_id: string
  amount: string | number
  is_personal: boolean
  company_id: string | null
  is_locked: boolean
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
  start_date?: string
  end_date?: string
  company_id?: string | null
  transaction_id?: string | null
  include_locked?: boolean
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
