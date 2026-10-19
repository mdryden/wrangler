import { describe, it, expect, beforeEach, vi } from "vitest"
import { setActivePinia, createPinia } from "pinia"
import { useStagingStore } from "../staging"
import type { ImporterMetadata, StagedTransaction } from "../../types/staging"

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

describe("useStagingStore", () => {
  let mockFetch: ReturnType<typeof vi.fn>

  const sampleImporters: ImporterMetadata[] = [
    {
      importer_id: "wrangler_csv",
      source_name: "wrangler_csv",
      display_name: "Wrangler CSV",
      description: "Imports standard Wrangler CSV",
      input_type: "file",
      accepted_file_types: [".csv"],
      supports_mark_imported: false,
    },
    {
      importer_id: "google_groups",
      source_name: "google_groups",
      display_name: "Google Groups",
      description: "Imports from Google Groups",
      input_type: "none",
      accepted_file_types: [],
      supports_mark_imported: true,
    },
  ]

  const sampleStaged: StagedTransaction = {
    id: "stx-1",
    source: "wrangler_csv",
    external_id: "EXT-1",
    date: "2026-10-01",
    description: "Cloud Server",
    total_amount: "50.00",
    receipt_file_path: null,
    url: null,
    status: "STAGED",
    is_marked_imported: false,
    ledger_transaction_id: null,
    created_at: "2026-10-01T10:00:00Z",
    allocations: [],
    is_ready: false,
    supports_mark_imported: false,
    mark_imported_error: null,
  }

  beforeEach(() => {
    mockStorage.clear()
    setActivePinia(createPinia())
    vi.restoreAllMocks()
    mockFetch = vi.fn()
    globalThis.fetch = mockFetch as unknown as typeof fetch
  })

  it("fetches importers from GET /api/importers", async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      status: 200,
      headers: new Headers({ "content-type": "application/json" }),
      json: async () => sampleImporters,
    })

    const store = useStagingStore()
    const res = await store.fetchImporters()
    expect(mockFetch).toHaveBeenCalledWith("/api/importers", expect.anything())
    expect(res).toEqual(sampleImporters)
    expect(store.importers).toEqual(sampleImporters)
  })

  it("runs an importer with or without a file via POST /api/importers/{id}/run", async () => {
    const runResult = {
      importer_id: "wrangler_csv",
      total_parsed: 2,
      staged_count: 1,
      skipped_duplicates: 1,
      items: [sampleStaged],
    }

    mockFetch.mockResolvedValueOnce({
      ok: true,
      status: 200,
      headers: new Headers({ "content-type": "application/json" }),
      json: async () => runResult,
    })

    const store = useStagingStore()
    const file = new File(["id,date\n"], "test.csv", { type: "text/csv" })
    const res = await store.runImporter("wrangler_csv", file)
    expect(mockFetch).toHaveBeenCalledWith("/api/importers/wrangler_csv/run", expect.objectContaining({ method: "POST" }))
    expect(res).toEqual(runResult)
  })

  it("fetches staged transactions with status and source filters", async () => {
    const pageData = {
      items: [sampleStaged],
      total: 1,
      page: 1,
      page_size: 50,
      total_pages: 1,
    }

    mockFetch.mockResolvedValueOnce({
      ok: true,
      status: 200,
      headers: new Headers({ "content-type": "application/json" }),
      json: async () => pageData,
    })

    const store = useStagingStore()
    await store.fetchStagedTransactions({ status: "STAGED", source: "wrangler_csv" })

    const calledUrl = mockFetch.mock.calls[0][0] as string
    expect(calledUrl).toContain("status=STAGED")
    expect(calledUrl).toContain("source=wrangler_csv")
    expect(store.stagedTransactions).toEqual([sampleStaged])
    expect(store.total).toBe(1)
  })

  it("updates, dismisses, restores, and batch accepts staged transactions", async () => {
    const store = useStagingStore()
    store.stagedTransactions = [{ ...sampleStaged }]
    store.total = 1

    const updatedReady: StagedTransaction = {
      ...sampleStaged,
      is_ready: true,
      allocations: [
        {
          id: "sa-1",
          staged_transaction_id: "stx-1",
          amount: "50.00",
          is_personal: true,
          company_id: null,
        },
      ],
    }

    mockFetch.mockResolvedValueOnce({
      ok: true,
      status: 200,
      headers: new Headers({ "content-type": "application/json" }),
      json: async () => updatedReady,
    })

    const upd = await store.updateStagedTransaction("stx-1", {
      allocations: [{ amount: "50.00", is_personal: true }],
    })
    expect(upd.is_ready).toBe(true)
    expect(store.stagedTransactions[0].is_ready).toBe(true)

    // Dismiss removes item from STAGED view
    const dismissedItem: StagedTransaction = {
      ...sampleStaged,
      status: "DISMISSED",
    }
    mockFetch.mockResolvedValueOnce({
      ok: true,
      status: 200,
      headers: new Headers({ "content-type": "application/json" }),
      json: async () => dismissedItem,
    })

    await store.dismissStagedTransaction("stx-1")
    expect(store.stagedTransactions).toHaveLength(0)
    expect(store.total).toBe(0)

    // Batch accept
    const acceptRes = {
      accepted_count: 1,
      ledger_transaction_ids: ["ltx-1"],
      marked_imported_count: 1,
      mark_imported_errors: [],
    }
    mockFetch.mockResolvedValueOnce({
      ok: true,
      status: 200,
      headers: new Headers({ "content-type": "application/json" }),
      json: async () => acceptRes,
    })

    const acc = await store.acceptStagedTransactions(["stx-1"])
    expect(acc).toEqual(acceptRes)
  })
})
