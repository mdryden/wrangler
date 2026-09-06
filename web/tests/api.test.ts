import { describe, it, expect, beforeEach, vi } from "vitest"
import { setActivePinia, createPinia } from "pinia"
import { createApiClient, resolveUrl, ApiError } from "../src/api/client"

// In-memory mock storage
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

describe("resolveUrl", () => {
  it("resolves endpoint with no baseUrl", () => {
    expect(resolveUrl("/api/companies")).toBe("/api/companies")
    expect(resolveUrl("api/companies")).toBe("/api/companies")
  })

  it("resolves endpoint with baseUrl without duplicating slashes or /api prefix", () => {
    expect(resolveUrl("/companies", "/api")).toBe("/api/companies")
    expect(resolveUrl("companies", "/api/")).toBe("/api/companies")
    expect(resolveUrl("/api/companies", "/api")).toBe("/api/companies")
    expect(resolveUrl("api/companies", "/api")).toBe("/api/companies")
  })

  it("preserves absolute URLs", () => {
    expect(resolveUrl("https://api.external.com/v1", "/api")).toBe("https://api.external.com/v1")
    expect(resolveUrl("http://localhost:8000/api/health", "/api")).toBe("http://localhost:8000/api/health")
  })

  it("appends query parameters ignoring undefined and null", () => {
    const url = resolveUrl("/api/transactions", "", {
      page: 1,
      page_size: 20,
      filter: "pending",
      ignored: undefined,
      nullish: null,
    })
    expect(url).toBe("/api/transactions?page=1&page_size=20&filter=pending")
  })

  it("appends query parameters when url already contains a query string", () => {
    const url = resolveUrl("/api/transactions?sort=desc", "", {
      page: 2,
    })
    expect(url).toBe("/api/transactions?sort=desc&page=2")
  })
})

describe("apiClient", () => {
  let mockFetch: ReturnType<typeof vi.fn>

  beforeEach(() => {
    mockStorage.clear()
    setActivePinia(createPinia())
    vi.restoreAllMocks()
    mockFetch = vi.fn()
  })

  describe("Authentication Header", () => {
    it("automatically attaches Bearer token when token is present in storage", async () => {
      mockStorage.set("token", "my-jwt-token")
      mockFetch.mockResolvedValueOnce({
        ok: true,
        status: 200,
        headers: new Headers({ "content-type": "application/json" }),
        json: async () => ({ success: true }),
      })

      const client = createApiClient({ fetch: mockFetch as unknown as typeof fetch })
      const result = await client("/api/companies")

      expect(mockFetch).toHaveBeenCalledTimes(1)
      const [, init] = mockFetch.mock.calls[0]
      const headers = init.headers as Headers
      expect(headers.get("Authorization")).toBe("Bearer my-jwt-token")
      expect(result).toEqual({ success: true })
    })

    it("does not attach Authorization header when no token exists", async () => {
      mockFetch.mockResolvedValueOnce({
        ok: true,
        status: 200,
        headers: new Headers({ "content-type": "application/json" }),
        json: async () => ({ success: true }),
      })

      const client = createApiClient({ fetch: mockFetch as unknown as typeof fetch })
      await client("/api/health")

      const [, init] = mockFetch.mock.calls[0]
      const headers = init.headers as Headers
      expect(headers.get("Authorization")).toBeNull()
    })

    it("skips Authorization header when skipAuth is true", async () => {
      mockStorage.set("token", "my-jwt-token")
      mockFetch.mockResolvedValueOnce({
        ok: true,
        status: 200,
        headers: new Headers({ "content-type": "application/json" }),
        json: async () => ({ success: true }),
      })

      const client = createApiClient({ fetch: mockFetch as unknown as typeof fetch })
      await client("/api/login", { skipAuth: true })

      const [, init] = mockFetch.mock.calls[0]
      const headers = init.headers as Headers
      expect(headers.get("Authorization")).toBeNull()
    })

    it("preserves explicit custom Authorization header", async () => {
      mockStorage.set("token", "storage-token")
      mockFetch.mockResolvedValueOnce({
        ok: true,
        status: 200,
        headers: new Headers({ "content-type": "application/json" }),
        json: async () => ({ ok: true }),
      })

      const client = createApiClient({ fetch: mockFetch as unknown as typeof fetch })
      await client("/api/test", {
        headers: { Authorization: "Custom custom-token" },
      })

      const [, init] = mockFetch.mock.calls[0]
      const headers = init.headers as Headers
      expect(headers.get("Authorization")).toBe("Custom custom-token")
    })
  })

  describe("Request Body & Content-Type", () => {
    it("serializes object bodies to JSON and sets Content-Type header", async () => {
      mockFetch.mockResolvedValueOnce({
        ok: true,
        status: 201,
        headers: new Headers({ "content-type": "application/json" }),
        json: async () => ({ id: 1, name: "Acme" }),
      })

      const client = createApiClient({ fetch: mockFetch as unknown as typeof fetch })
      const result = await client.post("/api/companies", { name: "Acme" })

      const [, init] = mockFetch.mock.calls[0]
      const headers = init.headers as Headers
      expect(headers.get("Content-Type")).toBe("application/json")
      expect(init.body).toBe(JSON.stringify({ name: "Acme" }))
      expect(result).toEqual({ id: 1, name: "Acme" })
    })

    it("preserves custom Content-Type when provided with an object", async () => {
      mockFetch.mockResolvedValueOnce({
        ok: true,
        status: 200,
        headers: new Headers({ "content-type": "application/json" }),
        json: async () => ({ ok: true }),
      })

      const client = createApiClient({ fetch: mockFetch as unknown as typeof fetch })
      await client.post("/api/custom", { data: 123 }, { headers: { "Content-Type": "application/vnd.api+json" } })

      const [, init] = mockFetch.mock.calls[0]
      const headers = init.headers as Headers
      expect(headers.get("Content-Type")).toBe("application/vnd.api+json")
    })

    it("passes string bodies without JSON stringifying", async () => {
      mockFetch.mockResolvedValueOnce({
        ok: true,
        status: 200,
        headers: new Headers({ "content-type": "application/json" }),
        json: async () => ({ ok: true }),
      })

      const client = createApiClient({ fetch: mockFetch as unknown as typeof fetch })
      await client.post("/api/raw", "raw text payload", {
        headers: { "Content-Type": "text/plain" },
      })

      const [, init] = mockFetch.mock.calls[0]
      expect(init.body).toBe("raw text payload")
    })
  })

  describe("Response Parsing", () => {
    it("returns undefined for 204 No Content", async () => {
      mockFetch.mockResolvedValueOnce({
        ok: true,
        status: 204,
        headers: new Headers(),
      })

      const client = createApiClient({ fetch: mockFetch as unknown as typeof fetch })
      const result = await client.delete("/api/companies/1")
      expect(result).toBeUndefined()
    })

    it("returns blob when responseType is blob", async () => {
      const mockBlob = new Blob(["test receipt"], { type: "application/pdf" })
      mockFetch.mockResolvedValueOnce({
        ok: true,
        status: 200,
        headers: new Headers({ "content-type": "application/pdf" }),
        blob: async () => mockBlob,
      })

      const client = createApiClient({ fetch: mockFetch as unknown as typeof fetch })
      const result = await client.get("/api/receipts/doc.pdf", { responseType: "blob" })
      expect(result).toBe(mockBlob)
    })

    it("returns text when responseType is text", async () => {
      mockFetch.mockResolvedValueOnce({
        ok: true,
        status: 200,
        headers: new Headers({ "content-type": "text/plain" }),
        text: async () => "plain text response",
      })

      const client = createApiClient({ fetch: mockFetch as unknown as typeof fetch })
      const result = await client.get("/api/health", { responseType: "text" })
      expect(result).toBe("plain text response")
    })
  })

  describe("Error Handling & 401 Redirect", () => {
    it("calls onUnauthorized and throws ApiError on 401", async () => {
      const onUnauthorized = vi.fn()
      mockFetch.mockResolvedValueOnce({
        ok: false,
        status: 401,
        statusText: "Unauthorized",
        headers: new Headers({ "content-type": "application/json" }),
        json: async () => ({ detail: "Token has expired" }),
      })

      const client = createApiClient({
        fetch: mockFetch as unknown as typeof fetch,
        onUnauthorized,
      })

      let thrownError: unknown
      try {
        await client.get("/api/companies")
      } catch (err) {
        thrownError = err
      }

      expect(onUnauthorized).toHaveBeenCalledTimes(1)
      expect(thrownError).toBeInstanceOf(ApiError)
      const apiErr = thrownError as ApiError
      expect(apiErr.status).toBe(401)
      expect(apiErr.message).toBe("Token has expired")
      expect(apiErr.data).toEqual({ detail: "Token has expired" })
    })

    it("formats array of validation errors from detail field", async () => {
      mockFetch.mockResolvedValueOnce({
        ok: false,
        status: 422,
        statusText: "Unprocessable Entity",
        headers: new Headers({ "content-type": "application/json" }),
        json: async () => ({
          detail: [{ msg: "Field required" }, { msg: "Must be positive integer" }],
        }),
      })

      const client = createApiClient({ fetch: mockFetch as unknown as typeof fetch })

      await expect(client.post("/api/transactions", {})).rejects.toThrow("Field required, Must be positive integer")
    })

    it("handles non-json error responses gracefully", async () => {
      mockFetch.mockResolvedValueOnce({
        ok: false,
        status: 502,
        statusText: "Bad Gateway",
        headers: new Headers({ "content-type": "text/html" }),
        text: async () => "Bad Gateway Server Error",
      })

      const client = createApiClient({ fetch: mockFetch as unknown as typeof fetch })

      await expect(client.get("/api/companies")).rejects.toThrow("Bad Gateway Server Error")
    })
  })

  describe("HTTP Method Helpers", () => {
    it("executes get, post, put, patch, delete with correct methods", async () => {
      const client = createApiClient({ fetch: mockFetch as unknown as typeof fetch })

      mockFetch.mockResolvedValue({
        ok: true,
        status: 200,
        headers: new Headers({ "content-type": "application/json" }),
        json: async () => ({ ok: true }),
      })

      await client.get("/api/get-test")
      expect(mockFetch.mock.calls[0][1].method).toBe("GET")

      await client.post("/api/post-test", { a: 1 })
      expect(mockFetch.mock.calls[1][1].method).toBe("POST")

      await client.put("/api/put-test", { b: 2 })
      expect(mockFetch.mock.calls[2][1].method).toBe("PUT")

      await client.patch("/api/patch-test", { c: 3 })
      expect(mockFetch.mock.calls[3][1].method).toBe("PATCH")

      await client.delete("/api/delete-test")
      expect(mockFetch.mock.calls[4][1].method).toBe("DELETE")
    })
  })
})
