export interface Company {
  id: string
  name: string
  transaction_count?: number
}

export interface CompanyCreatePayload {
  name: string
}

export interface CompanyUpdatePayload {
  name?: string
}
