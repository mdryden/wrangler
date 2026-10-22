import fs from "fs"
import path from "path"
import { beforeEach, describe, expect, it, vi } from "vitest"
import { defineComponent, h, nextTick } from "vue"
import { flushPromises } from "@vue/test-utils"
import { createPinia, setActivePinia } from "pinia"
import { QLayout, QPageContainer } from "quasar"
import { mountWithQuasar } from "../../../tests/utils/testHarness"
import { useCompanyStore } from "../../stores/companies"
import ImportView from "../ImportView.vue"
import {
  buildQuickAssignPayload,
  canRunImporter,
  formatImporterSummaryToast,
  getAcceptedFileTypesAttr,
  getQuickAssignValue,
  getReadyToAcceptTransactions,
  getStagedAllocationSummary,
  MARK_IMPORTED_CAPABILITY_LABEL,
  PERSONAL_QUICK_ASSIGN_VALUE,
  SOURCE_FILTER_OPTIONS,
  useStagingStore,
} from "../../stores/staging"
import { apiClient } from "../../api/client"
import type { Company } from "../../types/company"
import type { ImporterMetadata, StagedTransaction } from "../../types/staging"
import {
  formatStagedAmount,
  getSourceFriendlyName,
  handleStagingKeyboardShortcut,
  isRowPersonal,
  stagingTableColumns,
  type StagingShortcutContext,
} from "../importView"

vi.mock("../../api/client", () => ({
  apiClient: {
    get: vi.fn(),
    post: vi.fn(),
    put: vi.fn(),
    delete: vi.fn(),
  },
}))

const sampleCompanies: Company[] = [
  { id: "comp-1", name: "Alpha Consulting LLC" },
  { id: "comp-2", name: "Beta Ventures" },
]

function makeStagedTx(overrides: Partial<StagedTransaction> = {}): StagedTransaction {
  return {
    id: "staged-1",
    source: "capital_one_csv",
    external_id: "ext-101",
    date: "2026-10-15",
    description: "Cloud Server",
    total_amount: "120.00",
    receipt_file_path: null,
    url: null,
    status: "STAGED",
    is_marked_imported: false,
    ledger_transaction_id: null,
    created_at: "2026-10-15T12:00:00Z",
    allocations: [],
    is_ready: false,
    supports_mark_imported: false,
    mark_imported_error: null,
    ...overrides,
  }
}

describe("ImportView Logic & Workflow", () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.clearAllMocks()
  })

  describe("Importer selection & dynamic file vs. integration input controls", () => {
    const csvImporter: ImporterMetadata = {
      importer_id: "capital_one",
      source_name: "capital_one_csv",
      display_name: "Capital One CSV",
      description: "Import transactions from a Capital One CSV file.",
      input_type: "file",
      accepted_file_types: [".csv", ".txt"],
      supports_mark_imported: false,
    }

    const integrationImporter: ImporterMetadata = {
      importer_id: "amazon_orders",
      source_name: "amazon",
      display_name: "Amazon Orders",
      description: "Pull transactions directly from Amazon order sync.",
      input_type: "none",
      accepted_file_types: [],
      supports_mark_imported: true,
    }

    it("evaluates canRunImporter and acceptedFileTypes for file vs. no-input importers", () => {
      expect(canRunImporter(null, null)).toBe(false)

      // File importer requires a file
      expect(canRunImporter(csvImporter, null)).toBe(false)
      const file = new File(["Date,Amount\n2026-10-15,50.00"], "statement.csv", { type: "text/csv" })
      expect(canRunImporter(csvImporter, file)).toBe(true)
      expect(getAcceptedFileTypesAttr(csvImporter)).toBe(".csv,.txt")

      // Integration importer (input_type === "none") does not require a file
      expect(canRunImporter(integrationImporter, null)).toBe(true)
      expect(getAcceptedFileTypesAttr(integrationImporter)).toBe("")
      expect(MARK_IMPORTED_CAPABILITY_LABEL).toBe("Automatically marks items as imported in source upon acceptance")
    })

    it("formats importer run summary toast message", () => {
      const msg = formatImporterSummaryToast({
        importer_id: "capital_one",
        total_parsed: 15,
        staged_count: 12,
        skipped_duplicates: 3,
        items: [],
      })
      expect(msg).toBe("Imported 12 new transactions into staging (3 duplicates skipped)")
    })
  })

  describe("Allocation summary badges & inline quick assignment", () => {
    it("renders Unallocated warning badge when row has 0 allocations or is not ready", () => {
      const unallocated = makeStagedTx({ allocations: [], is_ready: false })
      expect(getStagedAllocationSummary(unallocated, sampleCompanies)).toEqual({
        label: "Unallocated",
        isReady: false,
        color: "orange-2",
        textColor: "orange-10",
      })
      expect(getQuickAssignValue(unallocated)).toBeNull()
    })

    it("renders Personal or Company name(s) positive badge when is_ready is true", () => {
      const personalTx = makeStagedTx({
        is_ready: true,
        allocations: [
          {
            id: "a-1",
            staged_transaction_id: "staged-1",
            amount: "120.00",
            is_personal: true,
            company_id: null,
          },
        ],
      })
      expect(getStagedAllocationSummary(personalTx, sampleCompanies)).toEqual({
        label: "Personal",
        isReady: true,
        color: "green-1",
        textColor: "positive",
      })
      expect(getQuickAssignValue(personalTx)).toBe(PERSONAL_QUICK_ASSIGN_VALUE)

      const singleCompanyTx = makeStagedTx({
        is_ready: true,
        allocations: [
          {
            id: "a-2",
            staged_transaction_id: "staged-1",
            amount: "120.00",
            is_personal: false,
            company_id: "comp-1",
          },
        ],
      })
      expect(getStagedAllocationSummary(singleCompanyTx, sampleCompanies)).toEqual({
        label: "Alpha Consulting LLC",
        isReady: true,
        color: "green-1",
        textColor: "positive",
      })
      expect(getQuickAssignValue(singleCompanyTx)).toBe("comp-1")

      const multiSplitTx = makeStagedTx({
        is_ready: true,
        allocations: [
          {
            id: "a-3",
            staged_transaction_id: "staged-1",
            amount: "70.00",
            is_personal: false,
            company_id: "comp-1",
          },
          {
            id: "a-4",
            staged_transaction_id: "staged-1",
            amount: "50.00",
            is_personal: false,
            company_id: "comp-2",
          },
        ],
      })
      expect(getStagedAllocationSummary(multiSplitTx, sampleCompanies)).toEqual({
        label: "Alpha Consulting LLC, Beta Ventures",
        isReady: true,
        color: "green-1",
        textColor: "positive",
      })
      expect(getQuickAssignValue(multiSplitTx)).toBeNull()
    })

    it("builds quick assign payloads for Personal, Company, and clearing back to Unallocated", () => {
      const tx = makeStagedTx({ total_amount: "85.50" })

      expect(buildQuickAssignPayload(tx, PERSONAL_QUICK_ASSIGN_VALUE)).toEqual({
        allocations: [
          {
            amount: "85.50",
            is_personal: true,
            company_id: null,
          },
        ],
      })

      expect(buildQuickAssignPayload(tx, "comp-2")).toEqual({
        allocations: [
          {
            amount: "85.50",
            is_personal: false,
            company_id: "comp-2",
          },
        ],
      })

      expect(buildQuickAssignPayload(tx, null)).toEqual({
        allocations: [],
      })
    })
  })

  describe("Dismissal, restoration, and batch acceptance workflow", () => {
    it("filters ready STAGED transactions for batch acceptance (all ready vs. selected subset)", () => {
      const r1 = makeStagedTx({ id: "s-1", status: "STAGED", is_ready: true })
      const r2 = makeStagedTx({ id: "s-2", status: "STAGED", is_ready: false })
      const r3 = makeStagedTx({ id: "s-3", status: "STAGED", is_ready: true })
      const r4 = makeStagedTx({ id: "s-4", status: "DISMISSED", is_ready: false })

      const rows = [r1, r2, r3, r4]

      // When no rows explicitly selected, returns all ready STAGED rows
      expect(getReadyToAcceptTransactions(rows, []).map(r => r.id)).toEqual(["s-1", "s-3"])

      // When subset selected, returns only selected ready STAGED rows
      expect(getReadyToAcceptTransactions(rows, ["s-3"]).map(r => r.id)).toEqual(["s-3"])
    })

    it("executes dismiss, restore, and batch acceptance through stagingStore and surfaces mark_imported errors", async () => {
      const store = useStagingStore()
      const txReady = makeStagedTx({
        id: "s-1",
        status: "STAGED",
        is_ready: true,
        supports_mark_imported: true,
      })
      store.stagedTransactions = [txReady]

      const dismissedTx: StagedTransaction = {
        ...txReady,
        status: "DISMISSED",
        is_ready: false,
        allocations: [],
        mark_imported_error: "External API timeout",
      }
      vi.mocked(apiClient.post).mockResolvedValueOnce(dismissedTx)
      const dismissResult = await store.dismissStagedTransaction("s-1")
      expect(dismissResult.status).toBe("DISMISSED")
      expect(dismissResult.mark_imported_error).toBe("External API timeout")

      const restoredTx: StagedTransaction = {
        ...dismissedTx,
        status: "STAGED",
        mark_imported_error: null,
      }
      vi.mocked(apiClient.post).mockResolvedValueOnce(restoredTx)
      const restoreResult = await store.restoreStagedTransaction("s-1")
      expect(restoreResult.status).toBe("STAGED")

      vi.mocked(apiClient.post).mockResolvedValueOnce({
        accepted_count: 1,
        ledger_transaction_ids: ["ledger-tx-1"],
        marked_imported_count: 0,
        mark_imported_errors: ["amazon: Connection refused"],
      })
      const acceptResult = await store.acceptStagedTransactions(["s-1"])
      expect(acceptResult.accepted_count).toBe(1)
      expect(acceptResult.mark_imported_errors).toEqual(["amazon: Connection refused"])
    })
  })

  describe("Source filter options and MCP integration filtering", () => {
    it("contains expected source options including mcp and standard channels", () => {
      const optionValues = SOURCE_FILTER_OPTIONS.map(opt => opt.value)
      expect(optionValues).toContain("")
      expect(optionValues).toContain("manual")
      expect(optionValues).toContain("wrangler_csv")
      expect(optionValues).toContain("amazon_csv")
      expect(optionValues).toContain("google_groups")
      expect(optionValues).toContain("mcp")

      expect(SOURCE_FILTER_OPTIONS).toContainEqual({ label: "MCP", value: "mcp" })
    })

    it("queries staged transactions filtered by mcp source", async () => {
      const store = useStagingStore()
      const mcpTx = makeStagedTx({
        id: "s-mcp-1",
        source: "mcp",
        external_id: "amazon:114-1234567-8901234",
        description: "[Amazon] Wireless Mouse",
        total_amount: "24.99",
      })

      vi.mocked(apiClient.get).mockResolvedValueOnce({
        items: [mcpTx],
        total: 1,
        page: 1,
        page_size: 50,
        total_pages: 1,
      })

      await store.fetchStagedTransactions({ status: "STAGED", source: "mcp" })

      expect(apiClient.get).toHaveBeenCalledWith(
        "/api/staging",
        expect.objectContaining({
          params: expect.objectContaining({
            source: "mcp",
            status: "STAGED",
          }),
        }),
      )
      expect(store.stagedTransactions).toHaveLength(1)
      expect(store.stagedTransactions[0].source).toBe("mcp")
      expect(store.stagedTransactions[0].external_id).toBe("amazon:114-1234567-8901234")
    })
  })

  describe("Responsive Staging Review Table Redesign (~1200px Viewport)", () => {
    it("does not include standalone source column and maintains required column configuration", () => {
      const columnNames = stagingTableColumns.map(c => c.name)
      expect(columnNames).not.toContain("source")
      expect(columnNames).toEqual(["select", "url", "actions", "allocations", "date", "description", "total_amount", "receipt"])

      const selectCol = stagingTableColumns.find(c => c.name === "select")
      expect(selectCol?.align).toBe("center")

      const urlCol = stagingTableColumns.find(c => c.name === "url")
      expect(urlCol?.align).toBe("center")

      const actionsCol = stagingTableColumns.find(c => c.name === "actions")
      expect(actionsCol?.align).toBe("left")

      const dateCol = stagingTableColumns.find(c => c.name === "date")
      expect(dateCol?.align).toBe("left")

      const descCol = stagingTableColumns.find(c => c.name === "description")
      expect(descCol?.align).toBe("left")

      const amountCol = stagingTableColumns.find(c => c.name === "total_amount")
      expect(amountCol?.align).toBe("right")

      const allocCol = stagingTableColumns.find(c => c.name === "allocations")
      expect(allocCol?.align).toBe("left")

      const receiptCol = stagingTableColumns.find(c => c.name === "receipt")
      expect(receiptCol?.align).toBe("center")
    })

    it("formats CAD currency amounts without redundant 'CA$' prefix", () => {
      expect(formatStagedAmount(96.04)).toBe("$96.04")
      expect(formatStagedAmount(-15.0)).toBe("-$15.00")
      expect(formatStagedAmount("1250.75")).toBe("$1,250.75")
      expect(formatStagedAmount("0")).toBe("$0.00")
      expect(formatStagedAmount(null)).toBe("$0.00")
    })

    it("verifies template layout optimizations in ImportView.vue", () => {
      const vueFilePath = path.resolve(__dirname, "../ImportView.vue")
      const templateContent = fs.readFileSync(vueFilePath, "utf-8")

      // Standalone source slot removed
      expect(templateContent).not.toContain("#body-cell-source")

      // URL slot contains open_in_new button with tooltip
      expect(templateContent).toContain('data-testid="btn-open-url"')
      expect(templateContent).toContain("<q-tooltip>Open URL</q-tooltip>")
      expect(templateContent).toContain('target="_blank"')
      expect(templateContent).toContain('rel="noopener noreferrer"')

      // Description slot contains source chip
      expect(templateContent).toContain("props.row.source")

      // Total amount slot uses formatStagedAmount
      expect(templateContent).toContain("formatStagedAmount(props.row.total_amount)")

      // Allocations slot contains read-only badge summary with click-to-edit
      expect(templateContent).toContain('data-testid="badge-staged-allocation"')
      expect(templateContent).toContain(
        "<q-tooltip>{{ getStagedAllocationSummary(props.row, companyMap).label }} (Click to edit)</q-tooltip>",
      )

      // Receipt slot contains view receipt button when present, and dash when absent; attach button removed
      expect(templateContent).toContain('data-testid="btn-view-staged-receipt"')
      expect(templateContent).toContain("<q-tooltip>View Receipt</q-tooltip>")
      expect(templateContent).not.toContain('data-testid="btn-attach-staged-receipt"')
      expect(templateContent).not.toContain('data-testid="btn-remove-staged-receipt"')

      // Active row indicator applied via tableRowClass and scoped styling
      expect(templateContent).toContain(':table-row-class-fn="tableRowClass"')
      expect(templateContent).toContain("active-staged-row")

      // Actions slot contains mark personal and edit buttons (dismiss moved to batch toolbar with confirmation dialog); restore button shown when dismissed
      expect(templateContent).toContain("btn-mark-personal-")
      expect(templateContent).toContain('data-testid="btn-action-edit"')
      expect(templateContent).toContain("<q-tooltip>Edit Transaction</q-tooltip>")
      expect(templateContent).not.toContain('data-testid="btn-action-dismiss"')
      expect(templateContent).toContain('data-testid="btn-dismiss-selected"')
      expect(templateContent).toContain('data-testid="btn-action-restore"')
      expect(templateContent).toContain("<q-tooltip>Restore Transaction</q-tooltip>")

      // Double-click row affordance to open edit dialog
      expect(templateContent).toContain('@row-dblclick="(_evt, row) => openEditDialog(row)"')

      // Quick triage action strip sub-row, quick action buttons, tooltips, and defaultCompanyId dialog binding
      expect(templateContent).toContain('data-testid="row-staged-action-strip"')
      expect(templateContent).toContain('data-testid="btn-action-strip-personal"')
      expect(templateContent).toContain("<q-tooltip>Mark 100% Personal (Shortcut: X)</q-tooltip>")
      expect(templateContent).toContain('data-testid="btn-action-strip-company"')
      expect(templateContent).toContain("<q-tooltip>Open Edit Dialog (Shortcut: C)</q-tooltip>")
      expect(templateContent).toContain(':data-testid="`btn-action-strip-comp-${comp.id}`"')
      expect(templateContent).toContain('data-testid="btn-action-strip-close"')
      expect(templateContent).toContain("<q-tooltip>Close quick actions (Esc)</q-tooltip>")
      expect(templateContent).toContain(':default-company-id="editDialogDefaultCompanyId"')
    })

    it("verifies isRowPersonal identifies 100% personal staged transactions", () => {
      const personalTx = makeStagedTx({
        allocations: [{ id: "a1", staged_transaction_id: "s1", amount: "50.00", is_personal: true, company_id: null }],
      })
      expect(isRowPersonal(personalTx)).toBe(true)

      const companyTx = makeStagedTx({
        allocations: [{ id: "a2", staged_transaction_id: "s2", amount: "50.00", is_personal: false, company_id: "c1" }],
      })
      expect(isRowPersonal(companyTx)).toBe(false)

      const splitTx = makeStagedTx({
        allocations: [
          { id: "a3", staged_transaction_id: "s3", amount: "25.00", is_personal: true, company_id: null },
          { id: "a4", staged_transaction_id: "s3", amount: "25.00", is_personal: false, company_id: "c1" },
        ],
      })
      expect(isRowPersonal(splitTx)).toBe(false)

      const unallocatedTx = makeStagedTx({ allocations: [] })
      expect(isRowPersonal(unallocatedTx)).toBe(false)
    })
  })

  describe("Source friendly names and personal staged readiness", () => {
    it("maps source identifiers to human-friendly display names", () => {
      expect(getSourceFriendlyName("amazon_csv")).toBe("Amazon")
      expect(getSourceFriendlyName("receipt_parser")).toBe("Receipt")
      expect(getSourceFriendlyName("ai_receipt")).toBe("Receipt")
      expect(getSourceFriendlyName("mcp")).toBe("AI Assistant")
      expect(getSourceFriendlyName("manual")).toBe("Manual")
      expect(getSourceFriendlyName("wrangler_csv")).toBe("Wrangler")
      expect(getSourceFriendlyName("google_groups")).toBe("Google Groups")
      expect(getSourceFriendlyName("custom_unknown_importer")).toBe("Custom Unknown Importer")
    })

    it("verifies template renders pending personal fallback description for unlabelled personal staged rows", () => {
      const vueFilePath = path.resolve(__dirname, "../ImportView.vue")
      const templateContent = fs.readFileSync(vueFilePath, "utf-8")

      expect(templateContent).toContain(
        "props.row.allocations && props.row.allocations.length === 1 && props.row.allocations[0].is_personal",
      )
      expect(templateContent).toContain("getSourceFriendlyName(props.row.source)")
      expect(templateContent).toContain(": Personal (Pending)")
    })

    it("updates is_ready to true when quick-assigning Personal to an unlabelled staged transaction", () => {
      const unlabelledStaged = makeStagedTx({
        description: "",
        allocations: [],
        is_ready: false,
      })
      const payload = buildQuickAssignPayload(unlabelledStaged, PERSONAL_QUICK_ASSIGN_VALUE)
      expect(payload.allocations).toEqual([
        {
          amount: unlabelledStaged.total_amount,
          is_personal: true,
          company_id: null,
        },
      ])

      const updatedPersonalTx: StagedTransaction = {
        ...unlabelledStaged,
        allocations: [
          {
            id: "a-pers-1",
            staged_transaction_id: unlabelledStaged.id,
            amount: unlabelledStaged.total_amount,
            is_personal: true,
            company_id: null,
          },
        ],
        is_ready: true,
      }
      expect(getStagedAllocationSummary(updatedPersonalTx, sampleCompanies)).toEqual({
        label: "Personal",
        isReady: true,
        color: "green-1",
        textColor: "positive",
      })
      expect(getQuickAssignValue(updatedPersonalTx)).toBe(PERSONAL_QUICK_ASSIGN_VALUE)
    })
  })

  describe("handleStagingKeyboardShortcut", () => {
    function createMockEvent(key: string, overrides: Partial<KeyboardEvent> = {}): KeyboardEvent {
      const preventDefault = vi.fn()
      return {
        key,
        ctrlKey: false,
        metaKey: false,
        altKey: false,
        target: document.body,
        preventDefault,
        ...overrides,
      } as unknown as KeyboardEvent
    }

    it("dispatches onPersonal and calls preventDefault on 'x' and 'X'", () => {
      const activeRow = makeStagedTx({ id: "staged-1", status: "STAGED" })
      const onPersonal = vi.fn()
      const context: StagingShortcutContext = {
        activeActionRowId: "staged-1",
        stagedTransactions: [activeRow],
        companies: sampleCompanies,
        isDialogOpen: false,
        onPersonal,
        onCompanyEdit: vi.fn(),
        onDismissStrip: vi.fn(),
      }

      const evtLower = createMockEvent("x")
      const handledLower = handleStagingKeyboardShortcut(evtLower, context)
      expect(handledLower).toBe(true)
      expect(evtLower.preventDefault).toHaveBeenCalled()
      expect(onPersonal).toHaveBeenCalledWith(activeRow)

      const evtUpper = createMockEvent("X")
      const handledUpper = handleStagingKeyboardShortcut(evtUpper, context)
      expect(handledUpper).toBe(true)
      expect(evtUpper.preventDefault).toHaveBeenCalled()
      expect(onPersonal).toHaveBeenCalledTimes(2)
    })

    it("dispatches onCompanyEdit with null company ID and calls preventDefault on 'c' and 'C'", () => {
      const activeRow = makeStagedTx({ id: "staged-1", status: "STAGED" })
      const onCompanyEdit = vi.fn()
      const context: StagingShortcutContext = {
        activeActionRowId: "staged-1",
        stagedTransactions: [activeRow],
        companies: sampleCompanies,
        isDialogOpen: false,
        onPersonal: vi.fn(),
        onCompanyEdit,
        onDismissStrip: vi.fn(),
      }

      const evtLower = createMockEvent("c")
      const handledLower = handleStagingKeyboardShortcut(evtLower, context)
      expect(handledLower).toBe(true)
      expect(evtLower.preventDefault).toHaveBeenCalled()
      expect(onCompanyEdit).toHaveBeenCalledWith(activeRow, null)

      const evtUpper = createMockEvent("C")
      const handledUpper = handleStagingKeyboardShortcut(evtUpper, context)
      expect(handledUpper).toBe(true)
      expect(evtUpper.preventDefault).toHaveBeenCalled()
      expect(onCompanyEdit).toHaveBeenCalledWith(activeRow, null)
    })

    it("dispatches onCompanyEdit with matching company ID on digit keys 1..N and ignores out-of-range digits", () => {
      const activeRow = makeStagedTx({ id: "staged-1", status: "STAGED" })
      const onCompanyEdit = vi.fn()
      const context: StagingShortcutContext = {
        activeActionRowId: "staged-1",
        stagedTransactions: [activeRow],
        companies: sampleCompanies, // length = 2: comp-1, comp-2
        isDialogOpen: false,
        onPersonal: vi.fn(),
        onCompanyEdit,
        onDismissStrip: vi.fn(),
      }

      const evt1 = createMockEvent("1")
      expect(handleStagingKeyboardShortcut(evt1, context)).toBe(true)
      expect(evt1.preventDefault).toHaveBeenCalled()
      expect(onCompanyEdit).toHaveBeenCalledWith(activeRow, "comp-1")

      const evt2 = createMockEvent("2")
      expect(handleStagingKeyboardShortcut(evt2, context)).toBe(true)
      expect(evt2.preventDefault).toHaveBeenCalled()
      expect(onCompanyEdit).toHaveBeenCalledWith(activeRow, "comp-2")

      const evt3 = createMockEvent("3")
      expect(handleStagingKeyboardShortcut(evt3, context)).toBe(false)
      expect(evt3.preventDefault).not.toHaveBeenCalled()
      expect(onCompanyEdit).toHaveBeenCalledTimes(2)
    })

    it("dispatches onDismissStrip and calls preventDefault on 'Escape'", () => {
      const activeRow = makeStagedTx({ id: "staged-1", status: "STAGED" })
      const onDismissStrip = vi.fn()
      const context: StagingShortcutContext = {
        activeActionRowId: "staged-1",
        stagedTransactions: [activeRow],
        companies: sampleCompanies,
        isDialogOpen: false,
        onPersonal: vi.fn(),
        onCompanyEdit: vi.fn(),
        onDismissStrip,
      }

      const evt = createMockEvent("Escape")
      expect(handleStagingKeyboardShortcut(evt, context)).toBe(true)
      expect(evt.preventDefault).toHaveBeenCalled()
      expect(onDismissStrip).toHaveBeenCalled()
    })

    it("returns false when isDialogOpen is true, activeActionRowId is null, or active row status is not STAGED", () => {
      const activeRow = makeStagedTx({ id: "staged-1", status: "STAGED" })
      const dismissedRow = makeStagedTx({ id: "staged-2", status: "DISMISSED" })
      const onPersonal = vi.fn()

      // Dialog open
      const ctxDialog: StagingShortcutContext = {
        activeActionRowId: "staged-1",
        stagedTransactions: [activeRow],
        companies: sampleCompanies,
        isDialogOpen: true,
        onPersonal,
        onCompanyEdit: vi.fn(),
        onDismissStrip: vi.fn(),
      }
      expect(handleStagingKeyboardShortcut(createMockEvent("x"), ctxDialog)).toBe(false)
      expect(onPersonal).not.toHaveBeenCalled()

      // activeActionRowId is null
      const ctxNoActive: StagingShortcutContext = {
        ...ctxDialog,
        activeActionRowId: null,
        isDialogOpen: false,
      }
      expect(handleStagingKeyboardShortcut(createMockEvent("x"), ctxNoActive)).toBe(false)

      // Active row status is DISMISSED
      const ctxDismissed: StagingShortcutContext = {
        ...ctxDialog,
        activeActionRowId: "staged-2",
        stagedTransactions: [dismissedRow],
        isDialogOpen: false,
      }
      expect(handleStagingKeyboardShortcut(createMockEvent("x"), ctxDismissed)).toBe(false)

      // Active row not found in list
      const ctxNotFound: StagingShortcutContext = {
        ...ctxDialog,
        activeActionRowId: "nonexistent",
        stagedTransactions: [activeRow],
        isDialogOpen: false,
      }
      expect(handleStagingKeyboardShortcut(createMockEvent("x"), ctxNotFound)).toBe(false)
    })

    it("returns false when focused element is INPUT, TEXTAREA, SELECT, or contenteditable", () => {
      const activeRow = makeStagedTx({ id: "staged-1", status: "STAGED" })
      const context: StagingShortcutContext = {
        activeActionRowId: "staged-1",
        stagedTransactions: [activeRow],
        companies: sampleCompanies,
        isDialogOpen: false,
        onPersonal: vi.fn(),
        onCompanyEdit: vi.fn(),
        onDismissStrip: vi.fn(),
      }

      const inputEl = document.createElement("input")
      expect(handleStagingKeyboardShortcut(createMockEvent("x", { target: inputEl }), context)).toBe(false)

      const textareaEl = document.createElement("textarea")
      expect(handleStagingKeyboardShortcut(createMockEvent("x", { target: textareaEl }), context)).toBe(false)

      const selectEl = document.createElement("select")
      expect(handleStagingKeyboardShortcut(createMockEvent("x", { target: selectEl }), context)).toBe(false)

      const divEditable = document.createElement("div")
      divEditable.contentEditable = "true"
      expect(handleStagingKeyboardShortcut(createMockEvent("x", { target: divEditable }), context)).toBe(false)
    })

    it("returns false when ctrlKey, metaKey, or altKey is pressed", () => {
      const activeRow = makeStagedTx({ id: "staged-1", status: "STAGED" })
      const context: StagingShortcutContext = {
        activeActionRowId: "staged-1",
        stagedTransactions: [activeRow],
        companies: sampleCompanies,
        isDialogOpen: false,
        onPersonal: vi.fn(),
        onCompanyEdit: vi.fn(),
        onDismissStrip: vi.fn(),
      }

      expect(handleStagingKeyboardShortcut(createMockEvent("c", { ctrlKey: true }), context)).toBe(false)
      expect(handleStagingKeyboardShortcut(createMockEvent("c", { metaKey: true }), context)).toBe(false)
      expect(handleStagingKeyboardShortcut(createMockEvent("c", { altKey: true }), context)).toBe(false)
    })
  })

  describe("Quick Triage Action Strip & Keyboard Component Integration", () => {
    const LayoutWrapper = defineComponent({
      setup: () => () => h(QLayout, () => h(QPageContainer, () => h(ImportView))),
    })

    it("opens action strip on URL button click and executes personal, company, indexed company, and dismiss actions", async () => {
      const pinia = createPinia()
      setActivePinia(pinia)
      const stagingStore = useStagingStore(pinia)
      const companyStore = useCompanyStore(pinia)

      companyStore.companies = [...sampleCompanies]

      const stagedWithUrl = makeStagedTx({
        id: "staged-101",
        status: "STAGED",
        url: "https://amazon.ca/orders/123",
        total_amount: "55.00",
        allocations: [],
      })
      stagingStore.stagedTransactions = [stagedWithUrl]

      vi.mocked(apiClient.get).mockImplementation(async (url: string) => {
        if (url === "/api/companies") {
          return sampleCompanies
        }
        if (url === "/api/staging/importers") {
          return []
        }
        if (url.startsWith("/api/staging")) {
          return {
            items: [stagedWithUrl],
            total: 1,
            page: 1,
            page_size: 50,
            total_pages: 1,
          }
        }
        return []
      })

      const wrapper = mountWithQuasar(LayoutWrapper, { pinia })
      await flushPromises()
      const importView = wrapper.findComponent(ImportView)

      // 1. Initial state: action strip is not rendered
      expect(wrapper.find('[data-testid="row-staged-action-strip"]').exists()).toBe(false)

      // 2. Click URL button -> opens action strip
      const urlBtn = wrapper.find('[data-testid="btn-open-url"]')
      expect(urlBtn.exists()).toBe(true)
      await urlBtn.trigger("click")
      await nextTick()

      expect(importView.vm.activeActionRowId).toBe("staged-101")
      expect(wrapper.find('[data-testid="row-staged-action-strip"]').exists()).toBe(true)

      // Verify buttons exist in strip
      expect(wrapper.find('[data-testid="btn-action-strip-personal"]').exists()).toBe(true)
      expect(wrapper.find('[data-testid="btn-action-strip-company"]').exists()).toBe(true)
      expect(wrapper.find('[data-testid="btn-action-strip-comp-comp-1"]').exists()).toBe(true)
      expect(wrapper.find('[data-testid="btn-action-strip-comp-comp-2"]').exists()).toBe(true)
      expect(wrapper.find('[data-testid="btn-action-strip-close"]').exists()).toBe(true)

      // 3. Click btn-action-strip-personal -> updates allocation and dismisses strip
      vi.mocked(apiClient.put).mockResolvedValueOnce({
        ...stagedWithUrl,
        allocations: [{ id: "a-1", staged_transaction_id: "staged-101", amount: "55.00", is_personal: true, company_id: null }],
        is_ready: true,
      })
      await wrapper.find('[data-testid="btn-action-strip-personal"]').trigger("click")
      await nextTick()

      expect(importView.vm.activeActionRowId).toBeNull()
      expect(apiClient.put).toHaveBeenCalledWith(
        "/api/staging/staged-101",
        expect.objectContaining({
          allocations: [{ amount: "55.00", is_personal: true, company_id: null }],
        }),
      )

      // 4. Re-open strip and test Company Edit button
      importView.vm.activeActionRowId = "staged-101"
      await nextTick()
      expect(wrapper.find('[data-testid="row-staged-action-strip"]').exists()).toBe(true)

      await wrapper.find('[data-testid="btn-action-strip-company"]').trigger("click")
      await nextTick()

      expect(importView.vm.activeActionRowId).toBeNull()
      expect(importView.vm.editDialogVisible).toBe(true)
      expect(importView.vm.editDialogDefaultCompanyId).toBeNull()

      // Close dialog
      importView.vm.editDialogVisible = false
      await nextTick()

      // 5. Re-open strip and test direct Numbered Company button
      importView.vm.activeActionRowId = "staged-101"
      await nextTick()

      await wrapper.find('[data-testid="btn-action-strip-comp-comp-2"]').trigger("click")
      await nextTick()

      expect(importView.vm.activeActionRowId).toBeNull()
      expect(importView.vm.editDialogVisible).toBe(true)
      expect(importView.vm.editDialogDefaultCompanyId).toBe("comp-2")

      // Close dialog
      importView.vm.editDialogVisible = false
      await nextTick()

      // 6. Re-open strip and test Close button
      importView.vm.activeActionRowId = "staged-101"
      await nextTick()

      await wrapper.find('[data-testid="btn-action-strip-close"]').trigger("click")
      await nextTick()

      expect(importView.vm.activeActionRowId).toBeNull()
      expect(wrapper.find('[data-testid="row-staged-action-strip"]').exists()).toBe(false)
      wrapper.unmount()
    })

    it("evaluates window keyboard shortcuts when triage strip is active", async () => {
      const pinia = createPinia()
      setActivePinia(pinia)
      const stagingStore = useStagingStore(pinia)
      const companyStore = useCompanyStore(pinia)

      companyStore.companies = [...sampleCompanies]

      const stagedWithUrl = makeStagedTx({
        id: "staged-102",
        status: "STAGED",
        url: "https://amazon.ca/orders/456",
        total_amount: "80.00",
        allocations: [],
      })
      stagingStore.stagedTransactions = [stagedWithUrl]

      vi.mocked(apiClient.get).mockImplementation(async (url: string) => {
        if (url === "/api/companies") {
          return sampleCompanies
        }
        if (url === "/api/staging/importers") {
          return []
        }
        if (url.startsWith("/api/staging")) {
          return {
            items: [stagedWithUrl],
            total: 1,
            page: 1,
            page_size: 50,
            total_pages: 1,
          }
        }
        return []
      })

      const wrapper = mountWithQuasar(LayoutWrapper, { pinia })
      await flushPromises()
      const importView = wrapper.findComponent(ImportView)

      // 1. Activate strip
      importView.vm.activeActionRowId = "staged-102"
      await nextTick()

      // Press 'x' on window
      vi.mocked(apiClient.put).mockResolvedValueOnce({
        ...stagedWithUrl,
        allocations: [{ id: "a-2", staged_transaction_id: "staged-102", amount: "80.00", is_personal: true, company_id: null }],
        is_ready: true,
      })
      window.dispatchEvent(new KeyboardEvent("keydown", { key: "x" }))
      await nextTick()

      expect(importView.vm.activeActionRowId).toBeNull()
      expect(apiClient.put).toHaveBeenCalledWith(
        "/api/staging/staged-102",
        expect.objectContaining({
          allocations: [{ amount: "80.00", is_personal: true, company_id: null }],
        }),
      )

      // 2. Activate strip and press 'c' on window
      importView.vm.activeActionRowId = "staged-102"
      await nextTick()
      window.dispatchEvent(new KeyboardEvent("keydown", { key: "c" }))
      await nextTick()

      expect(importView.vm.activeActionRowId).toBeNull()
      expect(importView.vm.editDialogVisible).toBe(true)
      expect(importView.vm.editDialogDefaultCompanyId).toBeNull()

      importView.vm.editDialogVisible = false
      await nextTick()

      // 3. Activate strip and press '1' on window
      importView.vm.activeActionRowId = "staged-102"
      await nextTick()
      window.dispatchEvent(new KeyboardEvent("keydown", { key: "1" }))
      await nextTick()

      expect(importView.vm.activeActionRowId).toBeNull()
      expect(importView.vm.editDialogVisible).toBe(true)
      expect(importView.vm.editDialogDefaultCompanyId).toBe("comp-1")

      importView.vm.editDialogVisible = false
      await nextTick()

      // 4. Activate strip and press 'Escape' on window
      importView.vm.activeActionRowId = "staged-102"
      await nextTick()
      window.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape" }))
      await nextTick()

      expect(importView.vm.activeActionRowId).toBeNull()

      // 5. Unmount cleans up listener
      wrapper.unmount()
      // Dispatch keydown after unmount should not trigger errors
      window.dispatchEvent(new KeyboardEvent("keydown", { key: "x" }))
    })
  })
})
