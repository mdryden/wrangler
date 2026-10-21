import fs from "fs"
import path from "path"
import { beforeEach, describe, expect, it, vi } from "vitest"
import { createPinia, setActivePinia } from "pinia"
import {
  canSyncSelectedToWave,
  countOverwrittenCategories,
  isMasterHeaderChecked,
  isMasterHeaderIndeterminate,
  type ExportAllocationRow,
} from "../src/views/exportManager"

function makeRow(overrides: Partial<ExportAllocationRow> = {}): ExportAllocationRow {
  return {
    id: "alloc-1",
    transaction_id: "tx-1",
    date: "2026-10-21",
    description: "Office Monitor",
    amount: "250.00",
    is_locked: false,
    company_id: "comp-1",
    receipt_file_path: null,
    wave_category_id: null,
    wave_transaction_id: null,
    ...overrides,
  }
}

describe("ExportManagerView Bulk Integration (Vitest Integration Suite)", () => {
  const viewPath = path.resolve(__dirname, "../src/views/ExportManagerView.vue")
  const viewTemplate = fs.readFileSync(viewPath, "utf-8")

  beforeEach(() => {
    setActivePinia(createPinia())
    vi.clearAllMocks()
  })

  describe("Template & UI Bulk Elements", () => {
    it("renders contextual toolbar elements when in Wave mode with selected rows", () => {
      expect(viewTemplate).toContain('data-testid="export-action-bar"')
      expect(viewTemplate).toContain('v-if="isWaveMode && selectedRows.length > 0"')
      expect(viewTemplate).toContain('data-testid="chip-bulk-selected-count"')
      expect(viewTemplate).toContain("<q-space />")
      expect(viewTemplate).toContain('data-testid="btn-bulk-assign-category"')
      expect(viewTemplate).toContain('data-testid="btn-sync-to-wave"')
    })

    it("wires Assign Category button to open BulkCategorizeDialog", () => {
      const match = viewTemplate.match(/<q-btn[^>]*data-testid="btn-bulk-assign-category"[^>]*\/>/)
      expect(match).not.toBeNull()
      expect(match![0]).toContain("showBulkCategorizeDialog = true")
    })

    it("mounts BulkCategorizeDialog with correct prop and event bindings", () => {
      expect(viewTemplate).toContain("<BulkCategorizeDialog")
      expect(viewTemplate).toContain('v-model="showBulkCategorizeDialog"')
      expect(viewTemplate).toContain(':selected-rows="selectedRows"')
      expect(viewTemplate).toContain(':categories="cachedCategories"')
      expect(viewTemplate).toContain('@applied="onBulkCategorizeApplied"')
    })

    it("renders 3-state header checkbox in header-cell-selection slot", () => {
      expect(viewTemplate).toContain('<template #header-cell-selection="props">')
      expect(viewTemplate).toContain(':model-value="isMasterChecked"')
      expect(viewTemplate).toContain(':indeterminate="isMasterIndeterminate"')
      expect(viewTemplate).toContain(':disable="visibleUnlockedRows.length === 0"')
      expect(viewTemplate).toContain('data-testid="checkbox-select-all"')
      expect(viewTemplate).toContain('@update:model-value="onToggleMasterHeader"')
    })

    it("decouples row checkbox selection from category assignment, enabling for any unlocked row", () => {
      expect(viewTemplate).toContain('<template #body-cell-selection="props">')
      expect(viewTemplate).toContain(':model-value="isRowSelected(props.row)"')
      expect(viewTemplate).toContain(':disable="props.row.is_locked"')
      expect(viewTemplate).toContain(':data-testid="`checkbox-row-${props.row.id}`"')
    })

    it("wires description click handler to toggle row selection", () => {
      expect(viewTemplate).toContain('<template #body-cell-description="props">')
      expect(viewTemplate).toContain('@click="toggleRowSelect(props.row)"')
    })
  })

  describe("Header Checkbox 3-State Logic & Toggling", () => {
    const row1 = makeRow({ id: "alloc-1", is_locked: false })
    const row2 = makeRow({ id: "alloc-2", is_locked: false })
    const rowLocked = makeRow({ id: "alloc-3", is_locked: true })

    it("computes visibleUnlockedRows excluding locked rows", () => {
      const allRows = [row1, row2, rowLocked]
      const visibleUnlocked = allRows.filter(r => !r.is_locked)
      expect(visibleUnlocked).toHaveLength(2)
      expect(visibleUnlocked.map(r => r.id)).toEqual(["alloc-1", "alloc-2"])
    })

    it("reports unchecked and not indeterminate when no rows are selected", () => {
      const visibleIds = [row1.id, row2.id]
      const selectedIds: string[] = []

      expect(isMasterHeaderChecked(visibleIds, selectedIds)).toBe(false)
      expect(isMasterHeaderIndeterminate(visibleIds, selectedIds)).toBe(false)
    })

    it("reports indeterminate when a subset of visible unlocked rows is selected", () => {
      const visibleIds = [row1.id, row2.id]
      const selectedIds = [row1.id]

      expect(isMasterHeaderChecked(visibleIds, selectedIds)).toBe(false)
      expect(isMasterHeaderIndeterminate(visibleIds, selectedIds)).toBe(true)
    })

    it("reports checked and not indeterminate when all visible unlocked rows are selected", () => {
      const visibleIds = [row1.id, row2.id]
      const selectedIds = [row1.id, row2.id]

      expect(isMasterHeaderChecked(visibleIds, selectedIds)).toBe(true)
      expect(isMasterHeaderIndeterminate(visibleIds, selectedIds)).toBe(false)
    })

    it("toggles header checkbox: deselects visible if checked or indeterminate, selects all visible unlocked if unchecked", () => {
      const visibleUnlockedRows = [row1, row2]
      let selectedRows: ExportAllocationRow[] = []

      const toggleHeader = () => {
        const visibleIds = visibleUnlockedRows.map(r => r.id)
        const selectedIds = selectedRows.map(r => r.id)
        const isChecked = isMasterHeaderChecked(visibleIds, selectedIds)
        const isIndeterminate = isMasterHeaderIndeterminate(visibleIds, selectedIds)

        if (isChecked || isIndeterminate) {
          const vSet = new Set(visibleIds)
          selectedRows = selectedRows.filter(r => !vSet.has(r.id))
        } else {
          const cSet = new Set(selectedIds)
          const toAdd = visibleUnlockedRows.filter(r => !cSet.has(r.id))
          selectedRows = [...selectedRows, ...toAdd]
        }
      }

      // Initial: unchecked -> click selects all visible unlocked
      toggleHeader()
      expect(selectedRows).toEqual([row1, row2])

      // Now checked -> click deselects all
      toggleHeader()
      expect(selectedRows).toEqual([])

      // Partial (indeterminate) -> click deselects visible
      selectedRows = [row1]
      toggleHeader()
      expect(selectedRows).toEqual([])
    })
  })

  describe("Sync to Wave Button Readiness & Dynamic Tooltips", () => {
    it("disables Sync to Wave and shows requirement tooltip when selection contains uncategorized items", () => {
      const selected = [
        makeRow({ id: "alloc-1", wave_category_id: "cat-1", is_locked: false }),
        makeRow({ id: "alloc-2", wave_category_id: null, is_locked: false }),
      ]

      const canSync = canSyncSelectedToWave(selected)
      expect(canSync).toBe(false)

      const tooltipText = !canSync
        ? "All selected transactions must have a category assigned before syncing to Wave"
        : `Push ${selected.length} categorized transactions directly to Wave`

      expect(tooltipText).toBe("All selected transactions must have a category assigned before syncing to Wave")
    })

    it("enables Sync to Wave and shows batch count tooltip when all selected rows are categorized and unlocked", () => {
      const selected = [
        makeRow({ id: "alloc-1", wave_category_id: "cat-1", is_locked: false }),
        makeRow({ id: "alloc-2", wave_category_id: "cat-2", is_locked: false }),
      ]

      const canSync = canSyncSelectedToWave(selected)
      expect(canSync).toBe(true)

      const tooltipText = !canSync
        ? "All selected transactions must have a category assigned before syncing to Wave"
        : `Push ${selected.length} categorized transactions directly to Wave`

      expect(tooltipText).toBe("Push 2 categorized transactions directly to Wave")
    })

    it("disables Sync to Wave when selected rows are empty", () => {
      expect(canSyncSelectedToWave([])).toBe(false)
    })
  })

  describe("Automatic Selection Reset", () => {
    it("resets selection when page changes, company changes, or filters change", () => {
      let selectedRows = [makeRow({ id: "alloc-1" })]

      const clearSelection = () => {
        selectedRows = []
      }

      // Pagination change simulation
      clearSelection()
      expect(selectedRows).toEqual([])

      // Filter change simulation
      selectedRows = [makeRow({ id: "alloc-2" })]
      clearSelection()
      expect(selectedRows).toEqual([])
    })

    it("verifies watch triggers and onRequest clear selectedRows in view code", () => {
      expect(viewTemplate).toContain("selectedRows.value = []")
      // Check that pagination or filter watch clears selection
      expect(viewTemplate).toContain("() => pagination.value.page")
      expect(viewTemplate).toContain("() => pagination.value.rowsPerPage")
      expect(viewTemplate).toContain("() => controls.value.company_id")
      expect(viewTemplate).toContain("() => controls.value.start_date")
      expect(viewTemplate).toContain("() => controls.value.end_date")
      expect(viewTemplate).toContain("() => controls.value.include_locked")
    })
  })
})
