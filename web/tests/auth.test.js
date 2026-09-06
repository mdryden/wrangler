import { describe, it, expect, beforeEach, vi } from "vitest"
import { setActivePinia, createPinia } from "pinia"
import { useAuthStore } from "../src/stores/auth.js"

// In-memory mock storage
const mockStorage = new Map()
globalThis.localStorage = {
  getItem: key => mockStorage.get(key) || null,
  setItem: (key, val) => mockStorage.set(key, String(val)),
  removeItem: key => mockStorage.delete(key),
  clear: () => mockStorage.clear(),
}

// Helper to create mock JWT
function createMockJwt(payload) {
  const header = btoa(JSON.stringify({ alg: "HS256", typ: "JWT" }))
  const body = btoa(JSON.stringify(payload)).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "")
  return `${header}.${body}.mock_signature`
}

describe("useAuthStore", () => {
  beforeEach(() => {
    mockStorage.clear()
    setActivePinia(createPinia())
    vi.restoreAllMocks()
  })

  it("has unauthenticated initial state when storage is empty", () => {
    const auth = useAuthStore()
    expect(auth.token).toBeNull()
    expect(auth.user).toBeNull()
    expect(auth.isAuthenticated).toBe(false)
    expect(auth.username).toBe("")
  })

  it("recognizes valid token from localStorage on initialization", () => {
    const futureExp = Math.floor(Date.now() / 1000) + 3600
    const token = createMockJwt({ sub: "admin_user", exp: futureExp })
    globalThis.localStorage.setItem("token", token)
    globalThis.localStorage.setItem("user", "admin_user")

    const auth = useAuthStore()
    expect(auth.token).toBe(token)
    expect(auth.user).toBe("admin_user")
    expect(auth.isAuthenticated).toBe(true)
    expect(auth.username).toBe("admin_user")
  })

  it("recognizes expired token as not authenticated", () => {
    const pastExp = Math.floor(Date.now() / 1000) - 3600
    const token = createMockJwt({ sub: "admin_user", exp: pastExp })
    globalThis.localStorage.setItem("token", token)

    const auth = useAuthStore()
    expect(auth.isAuthenticated).toBe(false)
  })

  it("login successfully sets token, user, and persists to localStorage", async () => {
    const futureExp = Math.floor(Date.now() / 1000) + 3600
    const mockToken = createMockJwt({ sub: "admin", exp: futureExp })

    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        access_token: mockToken,
        token_type: "bearer",
      }),
    })

    const auth = useAuthStore()
    const result = await auth.login({ username: "admin", password: "secret" })

    expect(globalThis.fetch).toHaveBeenCalledWith("/api/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ username: "admin", password: "secret" }),
    })
    expect(result.access_token).toBe(mockToken)
    expect(auth.token).toBe(mockToken)
    expect(auth.user).toBe("admin")
    expect(auth.isAuthenticated).toBe(true)
    expect(auth.username).toBe("admin")
    expect(globalThis.localStorage.getItem("token")).toBe(mockToken)
    expect(globalThis.localStorage.getItem("user")).toBe("admin")
  })

  it("login failure throws error with server detail message", async () => {
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: false,
      status: 401,
      json: async () => ({
        detail: "Invalid username or password",
      }),
    })

    const auth = useAuthStore()
    await expect(auth.login({ username: "wrong", password: "bad" })).rejects.toThrow("Invalid username or password")

    expect(auth.token).toBeNull()
    expect(auth.isAuthenticated).toBe(false)
    expect(globalThis.localStorage.getItem("token")).toBeNull()
  })

  it("logout clears token, user, and localStorage", () => {
    const futureExp = Math.floor(Date.now() / 1000) + 3600
    const token = createMockJwt({ sub: "admin", exp: futureExp })
    globalThis.localStorage.setItem("token", token)
    globalThis.localStorage.setItem("user", "admin")

    const auth = useAuthStore()
    expect(auth.isAuthenticated).toBe(true)

    auth.logout()

    expect(auth.token).toBeNull()
    expect(auth.user).toBeNull()
    expect(auth.isAuthenticated).toBe(false)
    expect(auth.username).toBe("")
    expect(globalThis.localStorage.getItem("token")).toBeNull()
    expect(globalThis.localStorage.getItem("user")).toBeNull()
  })
})
