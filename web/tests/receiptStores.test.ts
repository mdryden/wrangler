import { describe, it, expect, beforeEach, vi } from "vitest"
import { setActivePinia, createPinia } from "pinia"
import { canRunImporter, formatImporterSummaryToast, useStagingStore } from "../src/stores/staging"
import { useTransactionStore } from "../src/stores/transactions"
import type { ImporterMetadata, ImporterRunResponse } from "../src/types/staging"
import type { ReceiptParseResponse } from "../src/types/transaction"

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

describe("Receipt Stores & Helpers (Phase 3)", () => {
  let mockFetch: ReturnType<typeof vi.fn>

  beforeEach(() => {
    setActivePinia(createPinia())
    mockStorage.clear()
    mockStorage.set("auth_token", "fake-token")

    mockFetch = vi.fn()
    globalThis.fetch = mockFetch as unknown as typeof fetch
  })

  describe("canRunImporter helper", () => {
    const fileImporter: ImporterMetadata = {
      importer_id: "receipt_parser",
      source_name: "receipt_parser",
      display_name: "Receipt Scanner",
      description: "Scans receipts",
      input_type: "file",
      accepted_file_types: [".png", ".jpg", ".pdf"],
      supports_mark_imported: false,
    }

    const noneImporter: ImporterMetadata = {
      importer_id: "google_groups",
      source_name: "google_groups",
      display_name: "Google Groups",
      description: "Direct sync",
      input_type: "none",
      accepted_file_types: [],
      supports_mark_imported: true,
    }

    it("returns false if importer is null", () => {
      expect(canRunImporter(null, null)).toBe(false)
      const file = new File(["dummy"], "receipt.png", { type: "image/png" })
      expect(canRunImporter(null, file)).toBe(false)
    })

    it("returns true for input_type none regardless of file", () => {
      expect(canRunImporter(noneImporter, null)).toBe(true)
      const file = new File(["dummy"], "receipt.png", { type: "image/png" })
      expect(canRunImporter(noneImporter, file)).toBe(true)
    })

    it("handles single File for file importer", () => {
      expect(canRunImporter(fileImporter, null)).toBe(false)
      const file = new File(["dummy"], "receipt.png", { type: "image/png" })
      expect(canRunImporter(fileImporter, file)).toBe(true)
    })

    it("handles empty array and populated array for file importer", () => {
      expect(canRunImporter(fileImporter, [])).toBe(false)
      const file1 = new File(["f1"], "r1.png", { type: "image/png" })
      const file2 = new File(["f2"], "r2.png", { type: "image/png" })
      expect(canRunImporter(fileImporter, [file1, file2])).toBe(true)
    })
  })

  describe("formatImporterSummaryToast helper", () => {
    it("formats clean success message", () => {
      const res: ImporterRunResponse = {
        importer_id: "receipt_parser",
        total_parsed: 5,
        staged_count: 5,
        skipped_duplicates: 0,
        items: [],
      }
      expect(formatImporterSummaryToast(res)).toBe("Imported 5 new transactions into staging (0 duplicates skipped)")
    })

    it("formats message with skipped duplicates", () => {
      const res: ImporterRunResponse = {
        importer_id: "receipt_parser",
        total_parsed: 3,
        staged_count: 2,
        skipped_duplicates: 1,
        items: [],
      }
      expect(formatImporterSummaryToast(res)).toBe("Imported 2 new transactions into staging (1 duplicates skipped)")
    })

    it("appends failure summary when failed_files are present", () => {
      const res: ImporterRunResponse = {
        importer_id: "receipt_parser",
        total_parsed: 2,
        staged_count: 1,
        skipped_duplicates: 0,
        items: [],
        failed_files: ["bad_doc.pdf: corrupt document", "blurry.jpg: unreadable"],
      }
      const toast = formatImporterSummaryToast(res)
      expect(toast).toContain("Imported 1 new transactions into staging (0 duplicates skipped)")
      expect(toast).toContain("2 failed: bad_doc.pdf: corrupt document, blurry.jpg: unreadable")
    })
  })

  describe("stagingStore.runImporter with multi-file upload", () => {
    it("constructs FormData appending all files under files key", async () => {
      const store = useStagingStore()
      const mockResult: ImporterRunResponse = {
        importer_id: "receipt_parser",
        total_parsed: 2,
        staged_count: 2,
        skipped_duplicates: 0,
        items: [],
        failed_files: [],
      }

      mockFetch.mockResolvedValueOnce({
        ok: true,
        status: 200,
        headers: new Headers({ "content-type": "application/json" }),
        json: async () => mockResult,
      })

      const file1 = new File(["content1"], "receipt1.png", { type: "image/png" })
      const file2 = new File(["content2"], "receipt2.png", { type: "image/png" })

      const result = await store.runImporter("receipt_parser", [file1, file2])

      expect(mockFetch).toHaveBeenCalledTimes(1)
      const [url, options] = mockFetch.mock.calls[0]
      expect(url).toBe("/api/importers/receipt_parser/run")
      expect(options.method).toBe("POST")

      const body = options.body as FormData
      expect(body instanceof FormData).toBe(true)
      const appendedFiles = body.getAll("files")
      expect(appendedFiles.length).toBe(2)
      expect(result).toEqual(mockResult)
    })

    it("constructs FormData for single File under files key", async () => {
      const store = useStagingStore()
      const mockResult: ImporterRunResponse = {
        importer_id: "receipt_parser",
        total_parsed: 1,
        staged_count: 1,
        skipped_duplicates: 0,
        items: [],
      }

      mockFetch.mockResolvedValueOnce({
        ok: true,
        status: 200,
        headers: new Headers({ "content-type": "application/json" }),
        json: async () => mockResult,
      })

      const file = new File(["content"], "receipt.png", { type: "image/png" })
      const result = await store.runImporter("receipt_parser", file)

      expect(mockFetch).toHaveBeenCalledTimes(1)
      const [, options] = mockFetch.mock.calls[0]
      const body = options.body as FormData
      const appendedFiles = body.getAll("files")
      expect(appendedFiles.length).toBe(1)
      expect(result).toEqual(mockResult)
    })
  })

  describe("transactionStore.parseReceipt", () => {
    it("sends multipart POST to /api/receipts/parse and returns parsed response", async () => {
      const store = useTransactionStore()
      const mockParseResult: ReceiptParseResponse = {
        merchant: "Costco Wholesale",
        date: "2026-10-18",
        total_amount: 125.75,
        description: "Costco - Groceries and household",
      }

      mockFetch.mockResolvedValueOnce({
        ok: true,
        status: 200,
        headers: new Headers({ "content-type": "application/json" }),
        json: async () => mockParseResult,
      })

      const testFile = new File(["image-bytes"], "costco_receipt.jpg", { type: "image/jpeg" })
      const response = await store.parseReceipt(testFile)

      expect(mockFetch).toHaveBeenCalledTimes(1)
      const [url, options] = mockFetch.mock.calls[0]
      expect(url).toBe("/api/receipts/parse")
      expect(options.method).toBe("POST")

      const body = options.body as FormData
      expect(body instanceof FormData).toBe(true)
      expect(body.get("file")).toBe(testFile)

      expect(response).toEqual(mockParseResult)
    })

    it("propagates error and updates store error state on failure", async () => {
      const store = useTransactionStore()
      mockFetch.mockResolvedValueOnce({
        ok: false,
        status: 503,
        statusText: "Service Unavailable",
        headers: new Headers({ "content-type": "application/json" }),
        json: async () => ({ detail: "AI provider service unavailable" }),
      })

      const testFile = new File(["image-bytes"], "error_receipt.jpg", { type: "image/jpeg" })
      await expect(store.parseReceipt(testFile)).rejects.toThrow("AI provider service unavailable")
      expect(store.error).toBe("AI provider service unavailable")
    })
  })
})
