import fs from "fs"
import path from "path"
import { beforeEach, describe, expect, it, vi } from "vitest"
import { createPinia, setActivePinia } from "pinia"
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
import { formatStagedAmount, stagingTableColumns } from "../importView"

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
    currency_code: "CAD",
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
      expect(columnNames).toEqual(["select", "date", "description", "total_amount", "allocations", "receipt", "actions"])

      const selectCol = stagingTableColumns.find(c => c.name === "select")
      expect(selectCol?.align).toBe("center")

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

      const actionsCol = stagingTableColumns.find(c => c.name === "actions")
      expect(actionsCol?.align).toBe("right")
    })

    it("formats CAD currency amounts without redundant 'CA$' prefix", () => {
      expect(formatStagedAmount(96.04, "CAD")).toBe("$96.04")
      expect(formatStagedAmount(-15.0, "CAD")).toBe("-$15.00")
      expect(formatStagedAmount("1250.75", "CAD")).toBe("$1,250.75")
      expect(formatStagedAmount("0", "CAD")).toBe("$0.00")
      expect(formatStagedAmount(null, "CAD")).toBe("$0.00")
    })

    it("retains currency code for non-CAD currencies", () => {
      expect(formatStagedAmount(15.0, "USD")).toBe("USD 15.00")
      expect(formatStagedAmount(-15.0, "USD")).toBe("-USD 15.00")
      expect(formatStagedAmount("99.99", "EUR")).toBe("EUR 99.99")
    })

    it("verifies template layout optimizations in ImportView.vue", () => {
      const vueFilePath = path.resolve(__dirname, "../ImportView.vue")
      const templateContent = fs.readFileSync(vueFilePath, "utf-8")

      // Standalone source slot removed
      expect(templateContent).not.toContain("#body-cell-source")

      // Description slot contains source chip, external ID, and open_in_new button with tooltip
      expect(templateContent).toContain("props.row.source")
      expect(templateContent).toContain("ID: {{ props.row.external_id }}")
      expect(templateContent).toContain('data-testid="btn-open-url"')
      expect(templateContent).toContain("<q-tooltip>Open order in Amazon</q-tooltip>")
      expect(templateContent).toContain('target="_blank"')
      expect(templateContent).toContain('rel="noopener noreferrer"')

      // Total amount slot uses formatStagedAmount
      expect(templateContent).toContain("formatStagedAmount(props.row.total_amount, props.row.currency_code)")

      // Allocations slot contains call_split icon button with tooltip
      expect(templateContent).toContain('data-testid="btn-split-allocations"')
      expect(templateContent).toContain('icon="call_split"')
      expect(templateContent).toContain("<q-tooltip>Split Allocations</q-tooltip>")

      // Receipt slot contains attach receipt icon button with tooltip and no text label
      expect(templateContent).toContain('data-testid="btn-attach-staged-receipt"')
      expect(templateContent).toContain("<q-tooltip>Attach Receipt</q-tooltip>")

      // Actions slot contains edit, dismiss, and restore icon buttons with tooltips
      expect(templateContent).toContain('data-testid="btn-action-edit"')
      expect(templateContent).toContain("<q-tooltip>Edit Transaction</q-tooltip>")
      expect(templateContent).toContain('data-testid="btn-action-dismiss"')
      expect(templateContent).toContain("<q-tooltip>Dismiss Transaction</q-tooltip>")
      expect(templateContent).toContain('data-testid="btn-action-restore"')
      expect(templateContent).toContain("<q-tooltip>Restore Transaction</q-tooltip>")
    })
  })
})
