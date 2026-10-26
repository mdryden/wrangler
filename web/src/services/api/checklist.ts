import { apiClient } from "../../api/client"
import type {
  ChecklistConfig,
  ChecklistConfigUpdatePayload,
  MonthlyChecklist,
  MonthlyChecklistPatchPayload,
  RbcCsvSyncResult,
  TaxAccrualSyncPayload,
  WaveAccountsGrouped,
} from "../../types/checklist"

export async function fetchChecklistConfig(): Promise<ChecklistConfig> {
  return apiClient.get<ChecklistConfig>("/api/checklist/config")
}

export async function updateChecklistConfig(payload: ChecklistConfigUpdatePayload): Promise<ChecklistConfig> {
  return apiClient.put<ChecklistConfig>("/api/checklist/config", payload)
}

export async function fetchGroupedWaveAccounts(companyId: string): Promise<WaveAccountsGrouped> {
  return apiClient.get<WaveAccountsGrouped>(`/api/checklist/wave-accounts/${companyId}`)
}

export async function fetchMonthlyChecklist(yearMonth: string): Promise<MonthlyChecklist> {
  return apiClient.get<MonthlyChecklist>(`/api/checklist/months/${yearMonth}`)
}

export async function patchMonthlyChecklist(yearMonth: string, payload: MonthlyChecklistPatchPayload): Promise<MonthlyChecklist> {
  return apiClient.patch<MonthlyChecklist>(`/api/checklist/months/${yearMonth}`, payload)
}

export async function syncRbcCsv(yearMonth: string, accountType: "chequing" | "mastercard", file: File): Promise<RbcCsvSyncResult> {
  const formData = new FormData()
  formData.append("account_type", accountType)
  formData.append("file", file)
  return apiClient.post<RbcCsvSyncResult>(`/api/checklist/months/${yearMonth}/sync-rbc-csv`, formData)
}

export async function syncTaxAccrual(yearMonth: string, payload?: TaxAccrualSyncPayload): Promise<MonthlyChecklist> {
  return apiClient.post<MonthlyChecklist>(`/api/checklist/months/${yearMonth}/sync-tax-accrual`, payload)
}
