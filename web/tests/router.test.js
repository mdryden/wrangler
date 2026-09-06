import { describe, it, expect, beforeEach, vi } from "vitest"
import { setActivePinia, createPinia } from "pinia"
import { routes } from "../src/router/routes.js"
import { setupNavigationGuards } from "../src/router/guards.js"
import { useAuthStore } from "../src/stores/auth.js"

// In-memory mock storage
const mockStorage = new Map()
globalThis.localStorage = {
  getItem: key => mockStorage.get(key) || null,
  setItem: (key, val) => mockStorage.set(key, String(val)),
  removeItem: key => mockStorage.delete(key),
  clear: () => mockStorage.clear(),
}

function createMockJwt(payload) {
  const header = btoa(JSON.stringify({ alg: "HS256", typ: "JWT" }))
  const body = btoa(JSON.stringify(payload)).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "")
  return `${header}.${body}.mock_signature`
}

describe("Router Configuration & Navigation Guards", () => {
  describe("routes configuration", () => {
    it("defines login route with guestOnly and without auth requirement", () => {
      const loginRoute = routes.find(r => r.path === "/login")
      expect(loginRoute).toBeDefined()
      expect(loginRoute.name).toBe("login")
      expect(loginRoute.meta.requiresAuth).toBe(false)
      expect(loginRoute.meta.guestOnly).toBe(true)
    })

    it("defines protected routes under root layout", () => {
      const rootRoute = routes.find(r => r.path === "/")
      expect(rootRoute).toBeDefined()
      expect(rootRoute.meta.requiresAuth).toBe(true)

      const children = rootRoute.children
      const childNames = children.map(c => c.name).filter(Boolean)

      expect(childNames).toContain("ledger")
      expect(childNames).toContain("manual-entry")
      expect(childNames).toContain("sync-manager")
      expect(childNames).toContain("settings")

      // Empty path redirects to ledger
      const defaultChild = children.find(c => c.path === "")
      expect(defaultChild.redirect).toBe("/ledger")
    })

    it("defines catch-all route redirecting to ledger", () => {
      const catchAll = routes.find(r => r.path.includes("catchAll"))
      expect(catchAll).toBeDefined()
      expect(catchAll.redirect).toBe("/ledger")
    })
  })

  describe("navigation guards", () => {
    let guardFn

    beforeEach(() => {
      mockStorage.clear()
      setActivePinia(createPinia())
      vi.restoreAllMocks()

      const mockRouter = {
        beforeEach: fn => {
          guardFn = fn
        },
      }
      setupNavigationGuards(mockRouter)
    })

    it("redirects unauthenticated user to login with redirect query", () => {
      const to = {
        fullPath: "/ledger",
        matched: [{ meta: { requiresAuth: true } }],
      }
      const next = vi.fn()

      guardFn(to, {}, next)

      expect(next).toHaveBeenCalledWith({
        name: "login",
        query: { redirect: "/ledger" },
      })
    })

    it("allows unauthenticated user to access login route", () => {
      const to = {
        fullPath: "/login",
        matched: [{ meta: { requiresAuth: false, guestOnly: true } }],
      }
      const next = vi.fn()

      guardFn(to, {}, next)

      expect(next).toHaveBeenCalledWith()
    })

    it("redirects authenticated user away from login to ledger", () => {
      const futureExp = Math.floor(Date.now() / 1000) + 3600
      const token = createMockJwt({ sub: "admin", exp: futureExp })
      globalThis.localStorage.setItem("token", token)

      const to = {
        fullPath: "/login",
        matched: [{ meta: { requiresAuth: false, guestOnly: true } }],
      }
      const next = vi.fn()

      guardFn(to, {}, next)

      expect(next).toHaveBeenCalledWith({ name: "ledger" })
    })

    it("allows authenticated user to access protected routes", () => {
      const futureExp = Math.floor(Date.now() / 1000) + 3600
      const token = createMockJwt({ sub: "admin", exp: futureExp })
      globalThis.localStorage.setItem("token", token)

      const to = {
        fullPath: "/settings",
        matched: [{ meta: { requiresAuth: true } }],
      }
      const next = vi.fn()

      guardFn(to, {}, next)

      expect(next).toHaveBeenCalledWith()
    })

    it("clears expired token and redirects to login", () => {
      const pastExp = Math.floor(Date.now() / 1000) - 3600
      const token = createMockJwt({ sub: "admin", exp: pastExp })
      globalThis.localStorage.setItem("token", token)

      const authStore = useAuthStore()
      expect(authStore.token).toBe(token)

      const to = {
        fullPath: "/ledger",
        matched: [{ meta: { requiresAuth: true } }],
      }
      const next = vi.fn()

      guardFn(to, {}, next)

      expect(authStore.token).toBeNull()
      expect(next).toHaveBeenCalledWith({
        name: "login",
        query: { redirect: "/ledger" },
      })
    })
  })
})
