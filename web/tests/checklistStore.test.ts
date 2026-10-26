import { createPinia, setActivePinia } from "pinia"
import { beforeEach, describe, expect, it, vi } from "vitest"
import { getDefaultPreviousMonth, shiftMonth, useChecklistStore } from "../src/stores/checklist"
import type { ChecklistConfig, MonthlyChecklist, RbcCsvSyncResult, WaveAccountsGrouped } from "../src/types/checklist"

describe("Checklist Store", () => {
  let mockFetch: ReturnType<typeof vi.fn>

  beforeEach(() => {
    setActivePinia(createPinia())
    vi.restoreAllMocks()
    mockFetch = vi.fn()
    globalThis.fetch = mockFetch as unknown as typeof fetch
  })

  describe("Date Helper Functions", () => {
    it("getDefaultPreviousMonth computes prior calendar month correctly", () => {
      const oct2026 = new Date(2026, 9, 26) // October is month index 9
      expect(getDefaultPreviousMonth(oct2026)).toBe("2026-09")

      const jan2026 = new Date(2026, 0, 15) // January is month index 0
      expect(getDefaultPreviousMonth(jan2026)).toBe("2025-12")
    })

    it("shiftMonth increments and decrements YYYY-MM correctly", () => {
      expect(shiftMonth("2026-09", 1)).toBe("2026-10")
      expect(shiftMonth("2026-09", -1)).toBe("2026-08")
      expect(shiftMonth("2026-12", 1)).toBe("2027-01")
      expect(shiftMonth("2026-01", -1)).toBe("2025-12")
    })
  })

  describe("Store Actions & Reactivity", () => {
    it("fetchConfig retrieves checklist configuration and sets state", async () => {
      const mockConfig: ChecklistConfig = {
        company_id: "comp_123",
        company_name: "Michelle Dryden LTD",
        is_wave_connected: true,
        chequing_wave_account_id: "acct_chq",
        chequing_wave_account_name: "RBC Chequing",
        mastercard_wave_account_id: "acct_mc",
        mastercard_wave_account_name: "RBC Mastercard",
        tax_expense_wave_account_id: "acct_tax_exp",
        tax_expense_wave_account_name: "Taxes - Corporate Tax",
        tax_payable_wave_account_id: "acct_tax_pay",
        tax_payable_wave_account_name: "Taxes Payable",
        wave_web_business_slug: "d2977f10-6793-4504-a139-f0d6872b2628",
        last_chequing_tx_date: "2026-09-28",
        last_mastercard_tx_date: "2026-09-24",
      }

      mockFetch.mockResolvedValueOnce({
        ok: true,
        status: 200,
        headers: new Headers({ "content-type": "application/json" }),
        json: async () => mockConfig,
      })

      const store = useChecklistStore()
      const result = await store.fetchConfig()

      expect(mockFetch).toHaveBeenCalledWith("/api/checklist/config", expect.anything())
      expect(result).toEqual(mockConfig)
      expect(store.config).toEqual(mockConfig)
      expect(store.isChequingConfigured).toBe(true)
      expect(store.isMastercardConfigured).toBe(true)
    })

    it("fetchWaveAccounts loads grouped accounts for company", async () => {
      const mockAccounts: WaveAccountsGrouped = {
        bank_and_cc_accounts: [{ id: "b1", name: "Chequing", type: "ASSET" }],
        expense_accounts: [{ id: "e1", name: "Supplies", type: "EXPENSE" }],
        liability_accounts: [{ id: "l1", name: "Taxes Payable", type: "LIABILITY" }],
      }

      mockFetch.mockResolvedValueOnce({
        ok: true,
        status: 200,
        headers: new Headers({ "content-type": "application/json" }),
        json: async () => mockAccounts,
      })

      const store = useChecklistStore()
      const result = await store.fetchWaveAccounts("comp_123")

      expect(mockFetch).toHaveBeenCalledWith("/api/checklist/wave-accounts/comp_123", expect.anything())
      expect(result).toEqual(mockAccounts)
      expect(store.groupedWaveAccounts).toEqual(mockAccounts)
    })

    it("fetchMonth loads monthly checklist and updates getters", async () => {
      const mockMonth: MonthlyChecklist = {
        id: "m_1",
        year_month: "2026-09",
        completed_steps: ["import_chequing", "import_mastercard"],
        net_operating_cash: "5000.00",
        tax_rate: "12.00",
        tax_reserve_amount: "600.00",
        tax_accrual_wave_tx_id: null,
        prior_soft_cap: "17600.00",
        monthly_loc_reduction: "400.00",
        current_soft_cap: "17200.00",
        tax_liability: "1200.00",
        actual_loc_balance: "5000.00",
        maximum_safe_draw: "11000.00",
        wave_cash_flow_url: "https://next.waveapps.com/slug/reports/cash-flow",
      }

      mockFetch.mockResolvedValueOnce({
        ok: true,
        status: 200,
        headers: new Headers({ "content-type": "application/json" }),
        json: async () => mockMonth,
      })

      const store = useChecklistStore()
      const result = await store.fetchMonth("2026-09")

      expect(result.year_month).toBe("2026-09")
      expect(store.currentMonth).toEqual(mockMonth)
      expect(store.selectedYearMonth).toBe("2026-09")
      expect(store.completedStepsCount).toBe(2)
      expect(store.isStepCompleted("import_chequing")).toBe(true)
      expect(store.isStepCompleted("scan_receipts")).toBe(false)
    })

    it("toggleStep applies optimistic update and dispatches patch", async () => {
      const mockMonth: MonthlyChecklist = {
        id: "m_1",
        year_month: "2026-09",
        completed_steps: ["import_chequing"],
        net_operating_cash: null,
        tax_rate: "12.00",
        tax_reserve_amount: null,
        tax_accrual_wave_tx_id: null,
        prior_soft_cap: "17600.00",
        monthly_loc_reduction: "400.00",
        current_soft_cap: "17200.00",
        tax_liability: null,
        actual_loc_balance: null,
        maximum_safe_draw: null,
        wave_cash_flow_url: "",
      }

      const store = useChecklistStore()
      store.currentMonth = { ...mockMonth }

      const updatedMonth: MonthlyChecklist = {
        ...mockMonth,
        completed_steps: ["import_chequing", "allocate_loc_transfers"],
      }

      mockFetch.mockResolvedValueOnce({
        ok: true,
        status: 200,
        headers: new Headers({ "content-type": "application/json" }),
        json: async () => updatedMonth,
      })

      await store.toggleStep("allocate_loc_transfers", true)

      expect(mockFetch).toHaveBeenCalledWith(
        "/api/checklist/months/2026-09",
        expect.objectContaining({
          method: "PATCH",
          body: JSON.stringify({
            completed_steps: ["import_chequing", "allocate_loc_transfers"],
          }),
        }),
      )
      expect(store.completedStepsCount).toBe(2)

      // Untoggle step
      const untoggledMonth: MonthlyChecklist = {
        ...mockMonth,
        completed_steps: ["allocate_loc_transfers"],
      }
      mockFetch.mockResolvedValueOnce({
        ok: true,
        status: 200,
        headers: new Headers({ "content-type": "application/json" }),
        json: async () => untoggledMonth,
      })

      await store.toggleStep("import_chequing", false)
      expect(store.isStepCompleted("import_chequing")).toBe(false)
    })

    it("syncRbcCsv manages loading state and refreshes data on completion", async () => {
      const store = useChecklistStore()
      const mockResult: RbcCsvSyncResult = {
        total_rows: 5,
        synced_count: 5,
        failed_count: 0,
        auto_categorized_count: 2,
        uncategorized_count: 3,
        latest_transaction_date: "2026-09-28",
        errors: [],
      }

      // Mock sequence: 1) sync call, 2) fetchConfig, 3) fetchMonth
      mockFetch
        .mockResolvedValueOnce({
          ok: true,
          status: 200,
          headers: new Headers({ "content-type": "application/json" }),
          json: async () => mockResult,
        })
        .mockResolvedValueOnce({
          ok: true,
          status: 200,
          headers: new Headers({ "content-type": "application/json" }),
          json: async () => ({ last_chequing_tx_date: "2026-09-28" }),
        })
        .mockResolvedValueOnce({
          ok: true,
          status: 200,
          headers: new Headers({ "content-type": "application/json" }),
          json: async () => ({
            year_month: "2026-09",
            completed_steps: ["import_chequing"],
          }),
        })

      const file = new File(["test-content"], "test.csv", { type: "text/csv" })
      const promise = store.syncRbcCsv("2026-09", "chequing", file)
      expect(store.isSyncingCsv).toBe(true)

      const res = await promise
      expect(store.isSyncingCsv).toBe(false)
      expect(res.synced_count).toBe(5)
    })

    it("syncTaxAccrual manages loading state and updates currentMonth", async () => {
      const store = useChecklistStore()
      const mockUpdatedMonth: MonthlyChecklist = {
        id: "m_1",
        year_month: "2026-09",
        completed_steps: ["calculate_net_cash_and_tax"],
        net_operating_cash: "10000.00",
        tax_rate: "12.00",
        tax_reserve_amount: "1200.00",
        tax_accrual_wave_tx_id: "wave_tx_123",
        prior_soft_cap: "17600.00",
        monthly_loc_reduction: "400.00",
        current_soft_cap: "17200.00",
        tax_liability: null,
        actual_loc_balance: null,
        maximum_safe_draw: null,
        wave_cash_flow_url: "",
      }

      mockFetch.mockResolvedValueOnce({
        ok: true,
        status: 200,
        headers: new Headers({ "content-type": "application/json" }),
        json: async () => mockUpdatedMonth,
      })

      const promise = store.syncTaxAccrual("2026-09", "10000.00", "12.00")
      expect(store.isSyncingTax).toBe(true)

      const result = await promise
      expect(store.isSyncingTax).toBe(false)
      expect(result.tax_accrual_wave_tx_id).toBe("wave_tx_123")
      expect(store.currentMonth?.tax_accrual_wave_tx_id).toBe("wave_tx_123")
    })
  })
})
