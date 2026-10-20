import fs from "fs"
import path from "path"
import { beforeEach, describe, expect, it, vi } from "vitest"
import { createPinia, setActivePinia } from "pinia"
import {
  applyParsedReceiptToForm,
  createInitialManualEntryState,
  focusDateInputElement,
  isPdfFile,
  openBlobPreview,
  type ManualEntryFormState,
} from "../src/views/manualEntry"
import { getImportNotificationType } from "../src/views/importView"
import { formatImporterSummaryToast } from "../src/stores/staging"
import type { ImporterRunResponse } from "../src/types/staging"
import type { ReceiptParseResponse } from "../src/types/transaction"

describe("Phase 4 Receipt UI & Integration Tests", () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.clearAllMocks()
  })

  describe("ManualEntryView Layout & Receipt-First Intake Architecture", () => {
    const manualEntryPath = path.resolve(__dirname, "../src/views/ManualEntryView.vue")
    const templateContent = fs.readFileSync(manualEntryPath, "utf-8")

    it("renders receipt attachment input in Row 1 before date and amount inputs", () => {
      // Row 1: Receipt Attachment
      expect(templateContent).toContain('data-testid="input-receipt-file"')
      expect(templateContent).toContain('label="Receipt Attachment (Optional - Drop to Auto-Fill)"')
      expect(templateContent).toContain('accept=".pdf,.png,.jpg,.jpeg,.webp"')
      expect(templateContent).toContain('@update:model-value="onReceiptSelected"')

      // Row 2: Date & Amount
      expect(templateContent).toContain('data-testid="input-date"')
      expect(templateContent).toContain('data-testid="input-total-amount"')

      // Row 3: Description / Payee
      expect(templateContent).toContain('data-testid="input-description"')

      // Row 4: Allocations (Splits)
      expect(templateContent).toContain('data-testid="btn-add-split"')

      // Verify DOM ordering: Row 1 < Row 2 < Row 3 < Row 4
      const receiptIndex = templateContent.indexOf('data-testid="input-receipt-file"')
      const dateIndex = templateContent.indexOf('data-testid="input-date"')
      const descIndex = templateContent.indexOf('data-testid="input-description"')
      const splitIndex = templateContent.indexOf('data-testid="btn-add-split"')

      expect(receiptIndex).toBeGreaterThan(-1)
      expect(dateIndex).toBeGreaterThan(-1)
      expect(descIndex).toBeGreaterThan(-1)
      expect(splitIndex).toBeGreaterThan(-1)

      expect(receiptIndex).toBeLessThan(dateIndex)
      expect(dateIndex).toBeLessThan(descIndex)
      expect(descIndex).toBeLessThan(splitIndex)
    })

    it("renders AI scan trigger button in receipt input #after slot with proper styling and tooltip", () => {
      expect(templateContent).toContain('data-testid="btn-scan-receipt"')
      expect(templateContent).toContain('icon="auto_awesome"')
      expect(templateContent).toContain('color="primary"')
      expect(templateContent).toContain(':loading="isParsingReceipt"')
      expect(templateContent).toContain(':disable="!form.receipt_file"')
      expect(templateContent).toContain("<q-tooltip>Scan & Auto-Fill with AI</q-tooltip>")
      expect(templateContent).toContain('@click="parseCurrentReceipt"')
    })

    it("renders view receipt in new tab and toggle inline preview buttons in receipt input #after slot", () => {
      expect(templateContent).toContain('data-testid="btn-view-receipt"')
      expect(templateContent).toContain('icon="open_in_new"')
      expect(templateContent).toContain(':disable="!form.receipt_file"')
      expect(templateContent).toContain("<q-tooltip>Open Receipt in New Tab</q-tooltip>")
      expect(templateContent).toContain('@click="viewCurrentReceipt"')

      expect(templateContent).toContain('data-testid="btn-toggle-receipt-preview"')
      expect(templateContent).toContain(":icon=\"showReceiptPreview ? 'visibility_off' : 'visibility'\"")
      expect(templateContent).toContain('@click="toggleReceiptPreview"')
    })

    it("renders inline receipt preview card with PDF/image switching, file label, open-in-tab, and close button", () => {
      expect(templateContent).toContain('data-testid="receipt-preview-container"')
      expect(templateContent).toContain("Receipt Preview: {{ form.receipt_file?.name }}")
      expect(templateContent).toContain('data-testid="btn-preview-open-tab"')
      expect(templateContent).toContain('data-testid="btn-preview-close"')
      expect(templateContent).toContain('data-testid="receipt-preview-pdf"')
      expect(templateContent).toContain('data-testid="receipt-preview-img"')
    })

    it("exposes parsing, focus, and receipt viewing methods in defineExpose contract", () => {
      expect(templateContent).toContain("parseCurrentReceipt")
      expect(templateContent).toContain("isParsingReceipt")
      expect(templateContent).toContain("onReceiptSelected")
      expect(templateContent).toContain("focusDateInput")
      expect(templateContent).toContain("dateInputRef")
      expect(templateContent).toContain("viewCurrentReceipt")
      expect(templateContent).toContain("toggleReceiptPreview")
      expect(templateContent).toContain("showReceiptPreview")
      expect(templateContent).toContain("receiptPreviewUrl")
      expect(templateContent).toContain("isReceiptPdf")
    })

    it("detects PDF files correctly using isPdfFile", () => {
      const pdfByMime = new File(["dummy pdf"], "receipt.tmp", { type: "application/pdf" })
      const pdfByExt = new File(["dummy pdf"], "receipt.PDF", { type: "application/octet-stream" })
      const imageFile = new File(["dummy img"], "receipt.png", { type: "image/png" })

      expect(isPdfFile(pdfByMime)).toBe(true)
      expect(isPdfFile(pdfByExt)).toBe(true)
      expect(isPdfFile(imageFile)).toBe(false)
      expect(isPdfFile(null)).toBe(false)
    })

    it("creates and opens blob URL preview using openBlobPreview", () => {
      const file = new File(["sample content"], "receipt.png", { type: "image/png" })
      const windowOpenMock = vi.fn()
      vi.stubGlobal("window", { open: windowOpenMock })

      const url = openBlobPreview(file)
      expect(url).toMatch(/^blob:/)
      expect(windowOpenMock).toHaveBeenCalledWith(url, "_blank")
    })
  })

  describe("ManualEntryView AI Receipt Auto-Fill & Split Synchronization", () => {
    it("cascades date, description, total_amount and synchronizes single split", () => {
      const form: ManualEntryFormState = createInitialManualEntryState("comp-acme")
      expect(form.splits).toHaveLength(1)
      expect(form.splits[0].amount).toBe("")

      const parsed: ReceiptParseResponse = {
        date: "2026-10-18",
        description: "Staples - Printer ink & pens",
        merchant: "Staples",
        total_amount: 88.5,
      }

      applyParsedReceiptToForm(form, parsed)

      expect(form.date).toBe("2026-10-18")
      expect(form.description).toBe("Staples - Printer ink & pens")
      expect(form.total_amount).toBe("88.5")
      expect(form.splits[0].amount).toBe("88.5")
      expect(form.splits[0].company_id).toBe("comp-acme")
    })

    it("falls back to merchant when parsed description is missing or null", () => {
      const form: ManualEntryFormState = createInitialManualEntryState()

      const parsed: ReceiptParseResponse = {
        date: "2026-10-19",
        description: null,
        merchant: "Home Depot",
        total_amount: 142.15,
      }

      applyParsedReceiptToForm(form, parsed)

      expect(form.date).toBe("2026-10-19")
      expect(form.description).toBe("Home Depot")
      expect(form.total_amount).toBe("142.15")
      expect(form.splits[0].amount).toBe("142.15")
    })

    it("preserves multi-split allocations without overwriting when splits count > 1", () => {
      const form: ManualEntryFormState = {
        date: "",
        description: "",
        total_amount: "",
        receipt_file: null,
        splits: [
          { company_id: "comp-1", amount: "60.00" },
          { company_id: "comp-2", amount: "40.00" },
        ],
      }

      const parsed: ReceiptParseResponse = {
        date: "2026-10-20",
        description: "Shared Server Cost",
        merchant: "AWS",
        total_amount: 100.0,
      }

      applyParsedReceiptToForm(form, parsed)

      expect(form.date).toBe("2026-10-20")
      expect(form.description).toBe("Shared Server Cost")
      expect(form.total_amount).toBe("100")
      // Secondary splits preserved
      expect(form.splits[0].amount).toBe("60.00")
      expect(form.splits[1].amount).toBe("40.00")
    })

    it("handles partial receipt data without wiping existing manual entries", () => {
      const form: ManualEntryFormState = {
        date: "2026-10-15",
        description: "Pre-existing Client Lunch",
        total_amount: "50.00",
        receipt_file: null,
        splits: [{ company_id: "comp-1", amount: "50.00" }],
      }

      const partialParsed: ReceiptParseResponse = {
        date: null,
        description: null,
        merchant: null,
        total_amount: 75.25,
      }

      applyParsedReceiptToForm(form, partialParsed)

      // Total updated
      expect(form.total_amount).toBe("75.25")
      expect(form.splits[0].amount).toBe("75.25")
      // Existing date and description remain intact
      expect(form.date).toBe("2026-10-15")
      expect(form.description).toBe("Pre-existing Client Lunch")
    })
  })

  describe("ManualEntryView Keyboard-First Focus Behavior", () => {
    it("focuses Date input directly when focus() method is present on ref", () => {
      const focusMock = vi.fn()
      const mockRef = { focus: focusMock }

      focusDateInputElement(mockRef)
      expect(focusMock).toHaveBeenCalledTimes(1)
    })

    it("focuses inner native input element when wrapped by Quasar $el", () => {
      const inputFocusMock = vi.fn()
      const mockInput = { focus: inputFocusMock } as unknown as HTMLInputElement
      const mockEl = {
        querySelector: vi.fn((selector: string) => {
          if (selector === "input") return mockInput
          return null
        }),
      } as unknown as HTMLElement

      const mockRef = { $el: mockEl }
      focusDateInputElement(mockRef)

      expect(mockEl.querySelector).toHaveBeenCalledWith("input")
      expect(inputFocusMock).toHaveBeenCalledTimes(1)
    })

    it("handles null or undefined input ref gracefully without throwing", () => {
      expect(() => focusDateInputElement(null)).not.toThrow()
      expect(() => focusDateInputElement(undefined)).not.toThrow()
    })

    it("verifies programmatic initial focus on Date input in template onMounted hook", () => {
      const manualEntryPath = path.resolve(__dirname, "../src/views/ManualEntryView.vue")
      const templateContent = fs.readFileSync(manualEntryPath, "utf-8")

      expect(templateContent).toContain("onMounted(async () => {")
      expect(templateContent).toContain("focusDateInput()")
      expect(templateContent).toContain('ref="dateInputRef"')
      expect(templateContent).toContain('hint="Use Ctrl+; to set today"')
    })
  })

  describe("ImportView Multi-File Receipt Parser & Batch Feedback", () => {
    const importViewPath = path.resolve(__dirname, "../src/views/ImportView.vue")
    const templateContent = fs.readFileSync(importViewPath, "utf-8")

    it("enables :multiple dynamically when selectedImporter is receipt_parser", () => {
      expect(templateContent).toContain(":multiple=\"selectedImporter?.importer_id === 'receipt_parser'\"")
      expect(templateContent).toContain(':use-chips="true"')
      expect(templateContent).toContain("Array.isArray(importerFile) && importerFile.length > 1")
      expect(templateContent).toContain("`${importerFile.length} files selected`")
    })

    it("determines notification type as warning when batch has failed files", () => {
      const resultWithFailures: ImporterRunResponse = {
        importer_id: "receipt_parser",
        total_parsed: 3,
        staged_count: 2,
        skipped_duplicates: 0,
        items: [],
        failed_files: ["corrupt_receipt.png"],
      }

      const notifType = getImportNotificationType(resultWithFailures)
      expect(notifType).toBe("warning")

      const summaryToast = formatImporterSummaryToast(resultWithFailures)
      expect(summaryToast).toContain("Imported 2 new transactions into staging")
      expect(summaryToast).toContain("1 failed: corrupt_receipt.png")
    })

    it("determines notification type as warning when batch has skipped duplicates", () => {
      const resultWithDuplicates: ImporterRunResponse = {
        importer_id: "receipt_parser",
        total_parsed: 3,
        staged_count: 2,
        skipped_duplicates: 1,
        items: [],
        failed_files: [],
      }

      const notifType = getImportNotificationType(resultWithDuplicates)
      expect(notifType).toBe("warning")

      const summaryToast = formatImporterSummaryToast(resultWithDuplicates)
      expect(summaryToast).toContain("Imported 2 new transactions into staging")
      expect(summaryToast).toContain("1 duplicates skipped")
    })

    it("determines notification type as positive when batch completes cleanly without failures or duplicates", () => {
      const cleanResult: ImporterRunResponse = {
        importer_id: "receipt_parser",
        total_parsed: 4,
        staged_count: 4,
        skipped_duplicates: 0,
        items: [],
        failed_files: [],
      }

      const notifType = getImportNotificationType(cleanResult)
      expect(notifType).toBe("positive")

      const summaryToast = formatImporterSummaryToast(cleanResult)
      expect(summaryToast).toContain("Imported 4 new transactions into staging")
      expect(summaryToast).toContain("0 duplicates skipped")
      expect(summaryToast).not.toContain("failed")
    })

    it("verifies onRunImporter dispatches warning toast on partial failures in template logic", () => {
      expect(templateContent).toContain('if (getImportNotificationType(result) === "warning") {')
      expect(templateContent).toContain("notifyWarning(summaryToast)")
      expect(templateContent).toContain("notifySuccess(summaryToast)")
    })
  })
})
