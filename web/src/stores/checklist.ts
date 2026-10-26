import { defineStore } from "pinia"
import { computed, ref } from "vue"
import {
  fetchChecklistConfig,
  fetchGroupedWaveAccounts,
  fetchMonthlyChecklist,
  patchMonthlyChecklist,
  syncRbcCsv as apiSyncRbcCsv,
  syncTaxAccrual as apiSyncTaxAccrual,
  updateChecklistConfig,
} from "../services/api/checklist"
import type {
  ChecklistConfig,
  ChecklistConfigUpdatePayload,
  MonthlyChecklist,
  MonthlyChecklistPatchPayload,
  RbcCsvSyncResult,
  WaveAccountsGrouped,
} from "../types/checklist"

export function getDefaultPreviousMonth(referenceDate = new Date()): string {
  const d = new Date(referenceDate.getFullYear(), referenceDate.getMonth() - 1, 1)
  const year = d.getFullYear()
  const month = String(d.getMonth() + 1).padStart(2, "0")
  return `${year}-${month}`
}

export function shiftMonth(yearMonth: string, offset: -1 | 1): string {
  const [yearStr, monthStr] = yearMonth.split("-")
  const year = parseInt(yearStr, 10)
  const month = parseInt(monthStr, 10)
  const target = new Date(year, month - 1 + offset, 1)
  const targetYear = target.getFullYear()
  const targetMonth = String(target.getMonth() + 1).padStart(2, "0")
  return `${targetYear}-${targetMonth}`
}

export const useChecklistStore = defineStore("checklist", () => {
  const config = ref<ChecklistConfig | null>(null)
  const currentMonth = ref<MonthlyChecklist | null>(null)
  const selectedYearMonth = ref<string>(getDefaultPreviousMonth())
  const groupedWaveAccounts = ref<WaveAccountsGrouped | null>(null)
  const isLoading = ref<boolean>(false)
  const isSyncingCsv = ref<boolean>(false)
  const isSyncingTax = ref<boolean>(false)

  const completedStepsCount = computed(() => currentMonth.value?.completed_steps.length ?? 0)

  function isStepCompleted(stepKey: string): boolean {
    return currentMonth.value?.completed_steps.includes(stepKey) ?? false
  }

  const isChequingConfigured = computed(() => Boolean(config.value?.chequing_wave_account_id))
  const isMastercardConfigured = computed(() => Boolean(config.value?.mastercard_wave_account_id))

  const canSyncTaxAccrual = computed(() => {
    return Boolean(
      config.value?.tax_expense_wave_account_id &&
      config.value?.tax_payable_wave_account_id &&
      Number(currentMonth.value?.tax_reserve_amount || 0) > 0 &&
      !currentMonth.value?.tax_accrual_wave_tx_id,
    )
  })

  async function fetchConfig(): Promise<ChecklistConfig> {
    const data = await fetchChecklistConfig()
    config.value = data
    return data
  }

  async function updateConfig(payload: ChecklistConfigUpdatePayload): Promise<ChecklistConfig> {
    const data = await updateChecklistConfig(payload)
    config.value = data
    return data
  }

  async function fetchWaveAccounts(companyId: string): Promise<WaveAccountsGrouped> {
    const data = await fetchGroupedWaveAccounts(companyId)
    groupedWaveAccounts.value = data
    return data
  }

  async function fetchMonth(yearMonth: string): Promise<MonthlyChecklist> {
    isLoading.value = true
    try {
      const data = await fetchMonthlyChecklist(yearMonth)
      currentMonth.value = data
      selectedYearMonth.value = yearMonth
      return data
    } finally {
      isLoading.value = false
    }
  }

  async function updateMonth(yearMonth: string, payload: MonthlyChecklistPatchPayload): Promise<MonthlyChecklist> {
    const data = await patchMonthlyChecklist(yearMonth, payload)
    currentMonth.value = data
    return data
  }

  async function toggleStep(stepKey: string, completed: boolean): Promise<MonthlyChecklist | null> {
    if (!currentMonth.value) return null
    let steps = [...currentMonth.value.completed_steps]
    if (completed) {
      if (!steps.includes(stepKey)) {
        steps.push(stepKey)
      }
    } else {
      steps = steps.filter(k => k !== stepKey)
    }

    // Optimistic local update
    currentMonth.value.completed_steps = steps
    const data = await patchMonthlyChecklist(currentMonth.value.year_month, {
      completed_steps: steps,
    })
    currentMonth.value = data
    return data
  }

  async function syncRbcCsv(yearMonth: string, accountType: "chequing" | "mastercard", file: File): Promise<RbcCsvSyncResult> {
    isSyncingCsv.value = true
    try {
      const result = await apiSyncRbcCsv(yearMonth, accountType, file)
      await fetchConfig()
      await fetchMonth(yearMonth)
      return result
    } finally {
      isSyncingCsv.value = false
    }
  }

  async function syncTaxAccrual(
    yearMonth: string,
    netCash?: string | number | null,
    taxRate?: string | number | null,
  ): Promise<MonthlyChecklist> {
    isSyncingTax.value = true
    try {
      const payload = netCash !== undefined || taxRate !== undefined ? { net_operating_cash: netCash, tax_rate: taxRate } : undefined
      const data = await apiSyncTaxAccrual(yearMonth, payload)
      currentMonth.value = data
      return data
    } finally {
      isSyncingTax.value = false
    }
  }

  async function setSelectedYearMonth(yearMonth: string): Promise<MonthlyChecklist> {
    return fetchMonth(yearMonth)
  }

  async function navigateMonth(offset: -1 | 1): Promise<MonthlyChecklist> {
    const newMonth = shiftMonth(selectedYearMonth.value, offset)
    return fetchMonth(newMonth)
  }

  return {
    config,
    currentMonth,
    selectedYearMonth,
    groupedWaveAccounts,
    isLoading,
    isSyncingCsv,
    isSyncingTax,
    completedStepsCount,
    isStepCompleted,
    isChequingConfigured,
    isMastercardConfigured,
    canSyncTaxAccrual,
    fetchConfig,
    updateConfig,
    fetchWaveAccounts,
    fetchMonth,
    updateMonth,
    toggleStep,
    syncRbcCsv,
    syncTaxAccrual,
    setSelectedYearMonth,
    navigateMonth,
  }
})
