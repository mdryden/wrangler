export type ImporterInputType = "file" | "none"

export interface ImporterMetadata {
  importer_id: string
  source_name: string
  display_name: string
  description: string
  input_type: ImporterInputType
  accepted_file_types: string[]
  supports_mark_imported: boolean
}

export type StagedStatus = "STAGED" | "ACCEPTED" | "DISMISSED"

export interface StagedAllocation {
  id: string
  staged_transaction_id: string
  amount: string | number
  is_personal: boolean
  company_id: string | null
}

export interface StagedAllocationInput {
  id?: string
  amount: string | number
  is_personal?: boolean
  company_id?: string | null
}

export interface StagedTransaction {
  id: string
  source: string
  external_id: string | null
  date: string
  description: string
  total_amount: string | number
  receipt_file_path: string | null
  url: string | null
  status: StagedStatus
  is_marked_imported: boolean
  ledger_transaction_id: string | null
  created_at: string
  allocations: StagedAllocation[]
  is_ready: boolean
  supports_mark_imported: boolean
  mark_imported_error?: string | null
}

export interface ImporterRunResponse {
  importer_id: string
  total_parsed: number
  staged_count: number
  skipped_duplicates: number
  items: StagedTransaction[]
}

export interface PaginatedStagedTransactions {
  items: StagedTransaction[]
  total: number
  page: number
  page_size: number
  total_pages: number
}

export interface StagedTransactionUpdatePayload {
  date?: string
  description?: string
  total_amount?: string | number
  url?: string | null
  allocations?: StagedAllocationInput[]
  remove_receipt?: boolean
}

export interface StagingQueryParams {
  status?: StagedStatus
  source?: string | null
  page?: number
  page_size?: number
}

export interface StagingAcceptResponse {
  accepted_count: number
  ledger_transaction_ids: string[]
  marked_imported_count: number
  mark_imported_errors: string[]
}
