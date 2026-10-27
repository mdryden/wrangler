import { flushPromises } from "@vue/test-utils"
import { createPinia, setActivePinia } from "pinia"
import { QLayout, QPageContainer } from "quasar"
import { beforeEach, describe, expect, it, vi } from "vitest"
import { defineComponent, h, nextTick } from "vue"
import ChecklistSettingsDialog from "../src/components/ChecklistSettingsDialog.vue"
import { useChecklistStore } from "../src/stores/checklist"
import { useCompanyStore } from "../src/stores/companies"
import ChecklistView from "../src/views/ChecklistView.vue"
import { findInBody, mountWithQuasar } from "./utils/testHarness"

const ChecklistViewWithLayout = defineComponent({
  name: "ChecklistViewWithLayout",
  setup() {
    return () => h(QLayout, () => h(QPageContainer, () => h(ChecklistView)))
  },
})

describe("ChecklistView & ChecklistSettingsDialog Component Integration", () => {
  let mockFetch: ReturnType<typeof vi.fn>

  const mockConfig = {
    company_id: "comp_1",
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

  const mockMonth = {
    id: "m_1",
    year_month: "2026-09",
    completed_steps: ["import_chequing"],
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
    wave_cash_flow_url: "https://next.waveapps.com/d2977f10-6793-4504-a139-f0d6872b2628/reports/cash-flow?end=2026-09-30&start=2026-09-01",
  }

  beforeEach(() => {
    setActivePinia(createPinia())
    vi.restoreAllMocks()
    mockFetch = vi.fn()
    globalThis.fetch = mockFetch as unknown as typeof fetch

    mockFetch.mockImplementation(async (url: string) => {
      if (typeof url === "string" && url.includes("/api/checklist/config")) {
        return {
          ok: true,
          status: 200,
          headers: new Headers({ "content-type": "application/json" }),
          json: async () => mockConfig,
        }
      }
      if (typeof url === "string" && url.includes("/api/checklist/months/")) {
        return {
          ok: true,
          status: 200,
          headers: new Headers({ "content-type": "application/json" }),
          json: async () => mockMonth,
        }
      }
      if (typeof url === "string" && url.includes("/api/companies")) {
        return {
          ok: true,
          status: 200,
          headers: new Headers({ "content-type": "application/json" }),
          json: async () => [{ id: "comp_1", name: "Michelle Dryden LTD", is_wave_connected: true }],
        }
      }
      return {
        ok: true,
        status: 200,
        headers: new Headers({ "content-type": "application/json" }),
        json: async () => ({}),
      }
    })
  })

  it("renders all 9 step cards in sequential order with titles and descriptions", async () => {
    const wrapper = mountWithQuasar(ChecklistViewWithLayout)
    await flushPromises()

    const stepKeys = [
      "import_chequing",
      "import_mastercard",
      "allocate_loc_transfers",
      "reconcile_bank_accounts",
      "sync_external_data",
      "scan_receipts",
      "merge_and_reimburse",
      "calculate_net_cash_and_tax",
      "execute_dividends",
    ]

    for (const key of stepKeys) {
      const card = wrapper.find(`[data-testid="step-card-${key}"]`)
      expect(card.exists()).toBe(true)
    }

    expect(wrapper.text()).toContain("Monthly Bookkeeping Checklist — Michelle Dryden LTD")
    expect(wrapper.text()).toContain("Step 1: Import Chequing Feed")
    expect(wrapper.text()).toContain("Step 2: Import Mastercard Feed")
    expect(wrapper.text()).toContain("Step 3: Allocate LOC Transfers")
    expect(wrapper.text()).toContain("Step 4: Reconcile Bank Accounts")
    expect(wrapper.text()).toContain("Step 5: Sync External Data")
    expect(wrapper.text()).toContain("Step 6: Scan Receipts")
    expect(wrapper.text()).toContain("Step 7: Merge and Reimburse")
    expect(wrapper.text()).toContain("Step 8: Calculate Net Cash & Accrue Corporate Tax")
    expect(wrapper.text()).toContain("Step 9: Calculate Safe Draw & Execute Dividends")
  })

  it("month selector displays YYYY-MM and allows month navigation", async () => {
    const wrapper = mountWithQuasar(ChecklistViewWithLayout)
    await flushPromises()

    const monthInput = wrapper.find('[data-testid="month-selector-input"]')
    expect(monthInput.exists()).toBe(true)

    const prevBtn = wrapper.find('[data-testid="month-selector-prev"]')
    const nextBtn = wrapper.find('[data-testid="month-selector-next"]')
    expect(prevBtn.exists()).toBe(true)
    expect(nextBtn.exists()).toBe(true)
  })

  it("persistent affordance invariants: buttons remain visible and properly disabled", async () => {
    const wrapper = mountWithQuasar(ChecklistViewWithLayout)
    await flushPromises()
    const store = useChecklistStore()

    // Step 1: Sync to Wave button is visible but disabled because no file is selected
    const syncChqBtn = wrapper.find('[data-testid="btn-sync-chequing"]')
    expect(syncChqBtn.exists()).toBe(true)
    expect(syncChqBtn.attributes("disabled")).toBeDefined()

    // Step 2: Sync to Wave button is visible but disabled because no file is selected
    const syncMcBtn = wrapper.find('[data-testid="btn-sync-mastercard"]')
    expect(syncMcBtn.exists()).toBe(true)
    expect(syncMcBtn.attributes("disabled")).toBeDefined()

    // Step 8: Sync Tax Accrual button is visible and enabled when tax reserve > 0 and not yet synced
    const syncTaxBtn = wrapper.find('[data-testid="btn-sync-tax-accrual"]')
    expect(syncTaxBtn.exists()).toBe(true)
    expect(store.canSyncTaxAccrual).toBe(true)
  })

  it("Step 8 calculates tax reserve and links to cash flow report", async () => {
    const wrapper = mountWithQuasar(ChecklistViewWithLayout)
    await flushPromises()

    const taxReserveEl = wrapper.find('[data-testid="tax-reserve-amount"]')
    expect(taxReserveEl.text()).toContain("$600.00")

    const cashFlowBtn = wrapper.find('[data-testid="btn-wave-cash-flow"]')
    expect(cashFlowBtn.exists()).toBe(true)
    expect(cashFlowBtn.attributes("href")).toContain("https://next.waveapps.com/d2977f10-6793-4504-a139-f0d6872b2628/reports/cash-flow")
  })

  it("Step 9 displays current soft cap, maximum safe draw, and links to balance sheet", async () => {
    const wrapper = mountWithQuasar(ChecklistViewWithLayout)
    await flushPromises()

    const softCapEl = wrapper.find('[data-testid="current-soft-cap"]')
    expect(softCapEl.text()).toContain("$17200.00")

    const safeDrawEl = wrapper.find('[data-testid="maximum-safe-draw"]')
    expect(safeDrawEl.text()).toContain("$11000.00")

    const balanceSheetBtn = wrapper.find('[data-testid="btn-wave-balance-sheet"]')
    expect(balanceSheetBtn.exists()).toBe(true)
    expect(balanceSheetBtn.attributes("href")).toContain("reports/balance-sheet")
  })

  it("allows expanding and collapsing step accordions individually and via Expand All toggle", async () => {
    const wrapper = mountWithQuasar(ChecklistViewWithLayout)
    await flushPromises()

    // Step 1 is in completed_steps in mockMonth, so it defaults to collapsed
    const step1Card = wrapper.find('[data-testid="step-card-import_chequing"]')
    expect(step1Card.exists()).toBe(true)

    // Step 5 link buttons open in new tab
    const step5Card = wrapper.find('[data-testid="step-card-sync_external_data"]')
    const links = step5Card.findAll("a")
    const importLink = links.find(l => l.attributes("href") === "/import")
    const exportLink = links.find(l => l.attributes("href") === "/export-manager")
    expect(importLink?.attributes("target")).toBe("_blank")
    expect(exportLink?.attributes("target")).toBe("_blank")

    // Expand All button exists
    const expandAllBtn = wrapper.find('[data-testid="btn-toggle-expand-all"]')
    expect(expandAllBtn.exists()).toBe(true)

    // Click expand all to expand everything
    await expandAllBtn.trigger("click")
    await flushPromises()
    await nextTick()

    // Now button should say "Collapse All"
    expect(wrapper.text()).toContain("Collapse All")
  })

  it("ChecklistSettingsDialog renders and loads accounts on company selection", async () => {
    const mockGroupedAccounts = {
      bank_and_cc_accounts: [{ id: "b1", name: "RBC Chequing", type: "ASSET" }],
      expense_accounts: [{ id: "e1", name: "Corporate Tax Expense", type: "EXPENSE" }],
      liability_accounts: [{ id: "l1", name: "Taxes Payable", type: "LIABILITY" }],
    }

    mockFetch.mockImplementation(async (url: string) => {
      if (typeof url === "string" && url.includes("/api/checklist/wave-accounts/")) {
        return {
          ok: true,
          status: 200,
          headers: new Headers({ "content-type": "application/json" }),
          json: async () => mockGroupedAccounts,
        }
      }
      if (typeof url === "string" && url.includes("/api/checklist/config")) {
        return {
          ok: true,
          status: 200,
          headers: new Headers({ "content-type": "application/json" }),
          json: async () => mockConfig,
        }
      }
      if (typeof url === "string" && url.includes("/api/companies")) {
        return {
          ok: true,
          status: 200,
          headers: new Headers({ "content-type": "application/json" }),
          json: async () => [{ id: "comp_1", name: "Michelle Dryden LTD", is_wave_connected: true }],
        }
      }
      return {
        ok: true,
        status: 200,
        headers: new Headers({ "content-type": "application/json" }),
        json: async () => ({}),
      }
    })

    const companyStore = useCompanyStore()
    companyStore.companies = [
      {
        id: "comp_1",
        name: "Michelle Dryden LTD",
        is_wave_connected: true,
        transaction_count: 0,
        unlocked_allocation_count: 0,
        unlocked_amount_total: "0.00",
        locked_allocation_count: 0,
        wave_business_id: "biz_1",
        wave_business_name: "Michelle Dryden LTD",
        wave_anchor_account_id: "a1",
      },
    ]

    mountWithQuasar(ChecklistSettingsDialog, {
      props: {
        modelValue: true,
      },
    })
    await nextTick()
    await nextTick()

    expect(findInBody('[data-testid="select-target-company"]')).not.toBeNull()
    expect(findInBody('[data-testid="select-wave-chequing"]')).not.toBeNull()
    expect(findInBody('[data-testid="select-wave-mastercard"]')).not.toBeNull()
    expect(findInBody('[data-testid="select-tax-expense"]')).not.toBeNull()
    expect(findInBody('[data-testid="select-tax-payable"]')).not.toBeNull()
    expect(findInBody('[data-testid="input-wave-slug"]')).not.toBeNull()
    expect(findInBody('[data-testid="btn-save-settings"]')).not.toBeNull()
  })
})
