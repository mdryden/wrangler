import fs from "fs"
import path from "path"
import { beforeEach, describe, expect, it, vi } from "vitest"
import { createPinia, setActivePinia } from "pinia"
import { useCompanyStore } from "../src/stores/companies"
import { useTransactionStore } from "../src/stores/transactions"
import { canSyncRowToWave, extractCompanyAllocationRows, isWaveAlreadySynced, type ExportAllocationRow } from "../src/views/exportManager"
import type { Company } from "../src/types/company"
import type { Transaction } from "../src/types/transaction"
import type { WaveBusiness, WaveBusinessAccountsResponse, WaveSyncResponse } from "../src/types/wave"

// Mock localStorage
const mockStorage = new Map<string, string>()
const mockLocalStorage = {
  getItem: (key: string): string | null => mockStorage.get(key) || null,
  setItem: (key: string, val: string): void => {
    mockStorage.set(key, String(val))
  },
  removeItem: (key: string): void => {
    mockStorage.delete(key)
  },
  clear: (): void => mockStorage.clear(),
  length: 0,
  key: () => null,
}

Object.defineProperty(globalThis, "localStorage", {
  value: mockLocalStorage,
  writable: true,
})

describe("Wave UI Integration & Adaptive Sync View (Tasks 6.1 - 6.4)", () => {
  let mockFetch: ReturnType<typeof vi.fn>

  beforeEach(() => {
    mockStorage.clear()
    setActivePinia(createPinia())
    vi.restoreAllMocks()
    mockFetch = vi.fn()
    globalThis.fetch = mockFetch as unknown as typeof fetch
  })

  describe("CompanyFormDialog.vue Wave Integration", () => {
    const dialogPath = path.resolve(__dirname, "../src/components/CompanyFormDialog.vue")
    const dialogTemplate = fs.readFileSync(dialogPath, "utf-8")

    it("includes Wave integration card with connection status chip and inputs", () => {
      expect(dialogTemplate).toContain('data-testid="wave-status-chip"')
      expect(dialogTemplate).toContain('data-testid="input-wave-token"')
      expect(dialogTemplate).toContain('data-testid="btn-test-token"')
      expect(dialogTemplate).toContain('data-testid="select-wave-business"')
      expect(dialogTemplate).toContain('data-testid="select-anchor-account"')
      expect(dialogTemplate).toContain('data-testid="btn-sync-categories"')
      expect(dialogTemplate).toContain('data-testid="btn-disconnect-wave"')
    })

    it("entering a token and clicking 'Test & Fetch Businesses' populates business list", async () => {
      const store = useCompanyStore()
      const mockBusinesses: WaveBusiness[] = [
        { id: "biz_1", name: "Alpha Consulting", is_personal: false },
        { id: "biz_2", name: "Beta Investments", is_personal: false },
      ]

      mockFetch.mockResolvedValueOnce({
        ok: true,
        status: 200,
        headers: new Headers({ "content-type": "application/json" }),
        json: async () => mockBusinesses,
      })

      const list = await store.testWaveToken("valid_full_access_token")
      expect(list).toEqual(mockBusinesses)
      expect(mockFetch).toHaveBeenCalledWith(
        "/api/companies/wave/test-token",
        expect.objectContaining({
          method: "POST",
          body: JSON.stringify({ token: "valid_full_access_token" }),
        }),
      )
    })

    it("selecting a business triggers accounts fetch and populates anchor candidates", async () => {
      const store = useCompanyStore()
      const mockAccounts: WaveBusinessAccountsResponse = {
        anchor_accounts: [
          { id: "acct_bank", name: "Operating Account", type: "ASSET", subtype: "CASH_AND_BANK" },
          { id: "acct_equity", name: "Owner Contributions", type: "EQUITY", subtype: "OWNERS_EQUITY" },
        ],
        expense_categories: [{ id: "cat_1", name: "Office Expense", type: "EXPENSE", subtype: null, is_uncategorized: false }],
      }

      mockFetch.mockResolvedValueOnce({
        ok: true,
        status: 200,
        headers: new Headers({ "content-type": "application/json" }),
        json: async () => mockAccounts,
      })

      const result = await store.fetchBusinessAccounts("token_123", "biz_1")
      expect(result.anchor_accounts).toHaveLength(2)
      expect(result.anchor_accounts[0].name).toBe("Operating Account")
      expect(result.anchor_accounts[1].name).toBe("Owner Contributions")
    })

    it("displays 'Connected to Wave', 'Sync Categories', and 'Disconnect Wave' when company is connected", () => {
      expect(dialogTemplate).toContain('{{ isWaveConnected ? "Connected to Wave" : "CSV Export Only" }}')
      expect(dialogTemplate).toContain('v-if="isWaveConnected"')
      expect(dialogTemplate).toContain('data-testid="btn-sync-categories"')
      expect(dialogTemplate).toContain('data-testid="btn-disconnect-wave"')
    })
  })

  describe("ExportManagerView.vue Adaptive Synchronization", () => {
    const exportViewPath = path.resolve(__dirname, "../src/views/ExportManagerView.vue")
    const exportTemplate = fs.readFileSync(exportViewPath, "utf-8")

    it("contains adaptive UI elements for Wave and CSV modes", () => {
      expect(exportTemplate).toContain('data-testid="btn-sync-to-wave"')
      expect(exportTemplate).toContain('data-testid="btn-export-csv"')
      expect(exportTemplate).toContain('data-testid="btn-quick-sync-categories"')
      expect(exportTemplate).toContain('data-testid="checkbox-select-all"')
      expect(exportTemplate).toContain('data-testid="badge-synced-to-wave"')
      expect(exportTemplate).toContain('data-testid="badge-already-in-wave"')
      expect(exportTemplate).toContain('data-testid="dialog-sync-summary"')
    })

    it("extracts wave_category_id and wave_transaction_id into export allocation rows", () => {
      const mockTxs: Transaction[] = [
        {
          id: "tx-1",
          source: "MANUAL",
          external_id: null,
          date: "2026-10-20",
          description: "Supplies",
          total_amount: "50.00",
          receipt_file_path: null,
          allocations: [
            {
              id: "alloc-1",
              transaction_id: "tx-1",
              amount: "50.00",
              is_personal: false,
              company_id: "comp-wave",
              is_locked: false,
              wave_category_id: "cat-1",
              wave_transaction_id: "wave-tx-123",
            },
          ],
        },
      ]

      const rows = extractCompanyAllocationRows(mockTxs, "comp-wave", true)
      expect(rows).toHaveLength(1)
      expect(rows[0].wave_category_id).toBe("cat-1")
      expect(rows[0].wave_transaction_id).toBe("wave-tx-123")
    })

    it("isWaveAlreadySynced identifies allocations pushed to Wave that were subsequently unlocked", () => {
      const alreadySyncedRow: ExportAllocationRow = {
        id: "alloc-1",
        transaction_id: "tx-1",
        date: "2026-10-20",
        description: "Old Pushed Tx",
        amount: "100.00",
        is_locked: false,
        company_id: "comp-1",
        receipt_file_path: null,
        wave_category_id: "cat-1",
        wave_transaction_id: "wave-old-id",
      }

      expect(isWaveAlreadySynced(alreadySyncedRow)).toBe(true)
      expect(canSyncRowToWave(alreadySyncedRow)).toBe(false)

      const normalUnlockedRow: ExportAllocationRow = {
        ...alreadySyncedRow,
        wave_transaction_id: null,
      }
      expect(isWaveAlreadySynced(normalUnlockedRow)).toBe(false)
      expect(canSyncRowToWave(normalUnlockedRow)).toBe(true)
    })

    it("canSyncRowToWave requires category assignment and unlocked state", () => {
      const uncategorizedRow: ExportAllocationRow = {
        id: "alloc-2",
        transaction_id: "tx-2",
        date: "2026-10-20",
        description: "Uncategorized Tx",
        amount: "50.00",
        is_locked: false,
        company_id: "comp-1",
        receipt_file_path: null,
        wave_category_id: null,
        wave_transaction_id: null,
      }

      expect(canSyncRowToWave(uncategorizedRow)).toBe(false)
    })

    it("changing row category dispatches updateAllocationCategory", async () => {
      const txStore = useTransactionStore()
      const allocId = "alloc-change-1"
      const newCatId = "cat-new-456"

      mockFetch.mockResolvedValueOnce({
        ok: true,
        status: 200,
        headers: new Headers({ "content-type": "application/json" }),
        json: async () => ({
          id: allocId,
          wave_category_id: newCatId,
        }),
      })

      const updated = await txStore.updateAllocationCategory(allocId, newCatId)
      expect(mockFetch).toHaveBeenCalledWith(
        `/api/allocations/${allocId}/category`,
        expect.objectContaining({
          method: "PATCH",
          body: JSON.stringify({ wave_category_id: newCatId }),
        }),
      )
      expect(updated.wave_category_id).toBe(newCatId)
    })

    it("syncing to Wave calls POST /api/companies/{id}/sync-wave and returns summary data", async () => {
      const companyStore = useCompanyStore()
      const mockResult: WaveSyncResponse = {
        total_processed: 2,
        synced_count: 2,
        failed_count: 0,
        errors: [],
      }

      mockFetch.mockResolvedValueOnce({
        ok: true,
        status: 200,
        headers: new Headers({ "content-type": "application/json" }),
        json: async () => mockResult,
      })

      const resp = await companyStore.syncCompanyToWave("comp-wave-1", ["a1", "a2"])
      expect(resp.synced_count).toBe(2)
      expect(resp.errors).toHaveLength(0)
      expect(mockFetch).toHaveBeenCalledWith(
        "/api/companies/comp-wave-1/sync-wave",
        expect.objectContaining({
          method: "POST",
          body: JSON.stringify({ allocation_ids: ["a1", "a2"] }),
        }),
      )
    })
  })
})
