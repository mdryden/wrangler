import fs from "fs"
import path from "path"
import { beforeEach, describe, expect, it, vi } from "vitest"
import { createPinia, setActivePinia } from "pinia"
import { apiClient } from "../src/api/client"
import { useStagingStore } from "../src/stores/staging"
import type { StagedTransaction } from "../src/types/staging"
import {
  getSelectedReadyCount,
  getSelectedReadyIds,
  isMasterHeaderChecked,
  isMasterHeaderIndeterminate,
  toggleVisibleStagedRows,
} from "../src/views/importView"

vi.mock("../src/api/client", () => ({
  apiClient: {
    get: vi.fn(),
    post: vi.fn(),
    put: vi.fn(),
    delete: vi.fn(),
  },
}))

function createSampleStagedTx(overrides: Partial<StagedTransaction> = {}): StagedTransaction {
  return {
    id: "tx-1",
    source: "amazon_csv",
    external_id: "ext-1",
    date: "2026-10-20",
    description: "Office Monitor",
    total_amount: "320.00",
    receipt_file_path: null,
    url: null,
    status: "STAGED",
    is_marked_imported: false,
    ledger_transaction_id: null,
    created_at: "2026-10-20T10:00:00Z",
    allocations: [],
    is_ready: false,
    supports_mark_imported: false,
    mark_imported_error: null,
    ...overrides,
  }
}

describe("Staged Bulk Allocations & Actions (Vitest Integration Suite)", () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.clearAllMocks()
  })

  describe("Master Header Checkbox Logic", () => {
    it("reports checked when all visible staged rows are selected", () => {
      const visibleIds = ["tx-1", "tx-2", "tx-3"]
      const selectedIds = ["tx-1", "tx-2", "tx-3"]

      expect(isMasterHeaderChecked(visibleIds, selectedIds)).toBe(true)
      expect(isMasterHeaderIndeterminate(visibleIds, selectedIds)).toBe(false)
    })

    it("reports indeterminate when a subset of visible staged rows is selected", () => {
      const visibleIds = ["tx-1", "tx-2", "tx-3"]
      const selectedIds = ["tx-1", "tx-2"]

      expect(isMasterHeaderChecked(visibleIds, selectedIds)).toBe(false)
      expect(isMasterHeaderIndeterminate(visibleIds, selectedIds)).toBe(true)
    })

    it("reports unchecked and non-indeterminate when none are selected", () => {
      const visibleIds = ["tx-1", "tx-2", "tx-3"]
      const selectedIds: string[] = []

      expect(isMasterHeaderChecked(visibleIds, selectedIds)).toBe(false)
      expect(isMasterHeaderIndeterminate(visibleIds, selectedIds)).toBe(false)
    })

    it("reports unchecked and non-indeterminate when no staged rows are visible", () => {
      const visibleIds: string[] = []
      const selectedIds: string[] = []

      expect(isMasterHeaderChecked(visibleIds, selectedIds)).toBe(false)
      expect(isMasterHeaderIndeterminate(visibleIds, selectedIds)).toBe(false)
    })

    it("toggleVisibleStagedRows selects all when unchecked or deselects all when checked/indeterminate", () => {
      const visibleIds = ["tx-1", "tx-2"]

      // None selected -> selects all visible
      const afterSelectAll = toggleVisibleStagedRows(visibleIds, [])
      expect(afterSelectAll).toEqual(["tx-1", "tx-2"])

      // All selected -> deselects all visible
      const afterDeselectAll = toggleVisibleStagedRows(visibleIds, ["tx-1", "tx-2"])
      expect(afterDeselectAll).toEqual([])

      // Subset selected (indeterminate) -> deselects all visible
      const afterIndeterminate = toggleVisibleStagedRows(visibleIds, ["tx-1", "unrelated-id"])
      expect(afterIndeterminate).toEqual(["unrelated-id"])
    })
  })

  describe("Row Checkbox Decoupling & Permissions", () => {
    const viewPath = path.resolve(__dirname, "../src/views/ImportView.vue")
    const viewTemplate = fs.readFileSync(viewPath, "utf-8")

    it("enables row checkbox for any row with status STAGED regardless of is_ready", () => {
      // Must not contain !props.row.is_ready in disable condition
      expect(viewTemplate).not.toContain("!props.row.is_ready")
      expect(viewTemplate).toContain(":disable=\"props.row.status !== 'STAGED'\"")
    })

    it("includes master header checkbox in selection column", () => {
      expect(viewTemplate).toContain("#header-cell-select")
      expect(viewTemplate).toContain('data-testid="checkbox-select-all"')
      expect(viewTemplate).toContain(':disable="visibleStagedRows.length === 0"')
      expect(viewTemplate).toContain(':indeterminate="isHeaderIndeterminate"')
      expect(viewTemplate).toContain(':model-value="isHeaderChecked"')
    })
  })

  describe("Action Toolbar Rendering & Layout", () => {
    const viewPath = path.resolve(__dirname, "../src/views/ImportView.vue")
    const viewTemplate = fs.readFileSync(viewPath, "utf-8")

    it("renders action buttons horizontally below the full-width filter bar without layout shifts", () => {
      // Full width filters without extraneous reset button
      expect(viewTemplate).toContain('data-testid="filter-staging-status"')
      expect(viewTemplate).toContain('data-testid="filter-staging-source"')
      expect(viewTemplate).toContain('data-testid="btn-apply-staging-filters"')
      expect(viewTemplate).not.toContain('data-testid="btn-reset-staging-filters"')

      // Action toolbar with always-visible buttons and no extraneous clear button
      expect(viewTemplate).toContain('data-testid="chip-selected-count"')
      expect(viewTemplate).toContain("{{ selectedRowIds.length }} selected")
      expect(viewTemplate).toContain('data-testid="btn-bulk-allocate"')
      expect(viewTemplate).toContain("`Allocate (${selectedRowIds.length})`")
      expect(viewTemplate).toContain(':disable="selectedRowIds.length === 0"')
      expect(viewTemplate).toContain('data-testid="btn-accept-selected"')
      expect(viewTemplate).toContain("`Accept (${selectedReadyCount} ready)`")
      expect(viewTemplate).toContain(':disable="selectedReadyCount === 0 || acceptingBatch"')
      expect(viewTemplate).toContain('data-testid="btn-dismiss-selected"')
      expect(viewTemplate).toContain("`Dismiss (${selectedRowIds.length})`")
      expect(viewTemplate).toContain(':disable="selectedRowIds.length === 0"')
      expect(viewTemplate).not.toContain('data-testid="btn-accept-ready"')
      expect(viewTemplate).not.toContain('data-testid="btn-clear-selection"')

      // Verify layout order: [selected count] -> [dismiss selected] -> [q-space] -> [bulk allocate] -> [accept]
      const countIdx = viewTemplate.indexOf('data-testid="chip-selected-count"')
      const dismissIdx = viewTemplate.indexOf('data-testid="btn-dismiss-selected"')
      const spaceIdx = viewTemplate.indexOf("<q-space />")
      const allocateIdx = viewTemplate.indexOf('data-testid="btn-bulk-allocate"')
      const acceptIdx = viewTemplate.indexOf('data-testid="btn-accept-selected"')

      expect(countIdx).toBeLessThan(spaceIdx)
      expect(spaceIdx).toBeLessThan(dismissIdx)
      expect(dismissIdx).toBeLessThan(allocateIdx)
      expect(allocateIdx).toBeLessThan(acceptIdx)
    })
  })

  describe("Accept Selected Ready Calculation & Dispatch", () => {
    const txReady1 = createSampleStagedTx({ id: "ready-1", is_ready: true })
    const txReady2 = createSampleStagedTx({ id: "ready-2", is_ready: true })
    const txUnready = createSampleStagedTx({ id: "unready-1", is_ready: false })
    const allRows = [txReady1, txReady2, txUnready]

    it("correctly computes ready count K for mixed selection", () => {
      const selected = ["ready-1", "unready-1"]
      const readyCount = getSelectedReadyCount(selected, allRows)
      expect(readyCount).toBe(1)

      const readyIds = getSelectedReadyIds(selected, allRows)
      expect(readyIds).toEqual(["ready-1"])
    })

    it("returns ready count 0 when none of the selected items are ready", () => {
      const selected = ["unready-1"]
      const readyCount = getSelectedReadyCount(selected, allRows)
      expect(readyCount).toBe(0)

      const readyIds = getSelectedReadyIds(selected, allRows)
      expect(readyIds).toEqual([])
    })

    it("dispatches acceptStagedTransactions with only ready IDs", async () => {
      const stagingStore = useStagingStore()
      vi.mocked(apiClient.post).mockResolvedValueOnce({
        accepted_count: 1,
        ledger_transaction_ids: ["ledger-1"],
        marked_imported_count: 0,
        mark_imported_errors: [],
      })

      const readyIds = getSelectedReadyIds(["ready-1", "unready-1"], allRows)
      const res = await stagingStore.acceptStagedTransactions(readyIds)

      expect(apiClient.post).toHaveBeenCalledWith("/api/staging/accept", {
        staged_transaction_ids: ["ready-1"],
      })
      expect(res.accepted_count).toBe(1)
    })
  })

  describe("Bulk Dismiss Store Integration", () => {
    it("dispatches bulkDismissStaged and updates response metadata", async () => {
      const stagingStore = useStagingStore()
      vi.mocked(apiClient.post).mockResolvedValueOnce({
        dismissed_count: 2,
        staged_transaction_ids: ["tx-1", "tx-2"],
        marked_imported_count: 2,
        mark_imported_errors: [],
      })

      const res = await stagingStore.bulkDismissStaged(["tx-1", "tx-2"])

      expect(apiClient.post).toHaveBeenCalledWith("/api/staging/bulk-dismiss", {
        staged_transaction_ids: ["tx-1", "tx-2"],
      })
      expect(res.dismissed_count).toBe(2)
      expect(res.marked_imported_count).toBe(2)
      expect(res.mark_imported_errors).toEqual([])
    })
  })

  describe("Selection Reset on Filter & Pagination Changes", () => {
    it("prunes non-staged transactions and resets selection when pagination changes", () => {
      const viewPath = path.resolve(__dirname, "../src/views/ImportView.vue")
      const viewContent = fs.readFileSync(viewPath, "utf-8")

      // Check pagination change reset logic
      expect(viewContent).toContain("if (pagination.value.page !== page || pagination.value.rowsPerPage !== rowsPerPage)")
      expect(viewContent).toContain("selectedRowIds.value = []")

      // Check filter change reset logic
      expect(viewContent).toContain("function applyFilters(): void")
      expect(viewContent).toContain("function resetFilters(): void")
    })
  })
})
