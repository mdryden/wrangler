import { describe, it, expect, beforeEach, vi } from "vitest"
import { setActivePinia, createPinia } from "pinia"
import type { NavigationGuardNext, RouteLocationNormalized, RouteRecordRaw, Router } from "vue-router"
import { routes } from "../src/router/routes"
import { setupNavigationGuards } from "../src/router/guards"
import { useAuthStore } from "../src/stores/auth"

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

function createMockJwt(payload: { sub?: string; exp?: number; [key: string]: unknown }): string {
  const header = btoa(JSON.stringify({ alg: "HS256", typ: "JWT" }))
  const body = btoa(JSON.stringify(payload)).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "")
  return `${header}.${body}.mock_signature`
}

describe("Router Configuration & Navigation Guards", () => {
  describe("routes configuration", () => {
    it("defines login route with guestOnly and without auth requirement", () => {
      const loginRoute = routes.find(r => r.path === "/login")
      expect(loginRoute).toBeDefined()
      expect(loginRoute?.name).toBe("login")
      expect(loginRoute?.meta?.requiresAuth).toBe(false)
      expect(loginRoute?.meta?.guestOnly).toBe(true)
    })

    it("defines protected routes under root layout", () => {
      const rootRoute = routes.find(r => r.path === "/")
      expect(rootRoute).toBeDefined()
      expect(rootRoute?.meta?.requiresAuth).toBe(true)

      const children = (rootRoute?.children || []) as RouteRecordRaw[]
      const childNames = children.map(c => c.name).filter(Boolean)

      expect(childNames).toContain("ledger")
      expect(childNames).toContain("manual-entry")
      expect(childNames).toContain("sync-manager")
      expect(childNames).toContain("settings")

      // Empty path redirects to ledger
      const defaultChild = children.find(c => c.path === "")
      expect(defaultChild?.redirect).toBe("/ledger")
    })

    it("defines catch-all route redirecting to ledger", () => {
      const catchAll = routes.find(r => typeof r.path === "string" && r.path.includes("catchAll"))
      expect(catchAll).toBeDefined()
      expect(catchAll?.redirect).toBe("/ledger")
    })
  })

  describe("navigation guards", () => {
    let guardFn: (to: RouteLocationNormalized, from: RouteLocationNormalized, next: NavigationGuardNext) => void

    beforeEach(() => {
      mockStorage.clear()
      setActivePinia(createPinia())
      vi.restoreAllMocks()

      const mockRouter = {
        beforeEach: (fn: typeof guardFn) => {
          guardFn = fn
        },
      }
      setupNavigationGuards(mockRouter as unknown as Router)
    })

    it("redirects unauthenticated user to login with redirect query", () => {
      const to = {
        fullPath: "/ledger",
        matched: [{ meta: { requiresAuth: true } }],
      } as unknown as RouteLocationNormalized
      const next = vi.fn()

      guardFn(to, {} as RouteLocationNormalized, next)

      expect(next).toHaveBeenCalledWith({
        name: "login",
        query: { redirect: "/ledger" },
      })
    })

    it("allows unauthenticated user to access login route", () => {
      const to = {
        fullPath: "/login",
        matched: [{ meta: { requiresAuth: false, guestOnly: true } }],
      } as unknown as RouteLocationNormalized
      const next = vi.fn()

      guardFn(to, {} as RouteLocationNormalized, next)

      expect(next).toHaveBeenCalledWith()
    })

    it("redirects authenticated user away from login to ledger", () => {
      const futureExp = Math.floor(Date.now() / 1000) + 3600
      const token = createMockJwt({ sub: "admin", exp: futureExp })
      globalThis.localStorage.setItem("token", token)

      const to = {
        fullPath: "/login",
        matched: [{ meta: { requiresAuth: false, guestOnly: true } }],
      } as unknown as RouteLocationNormalized
      const next = vi.fn()

      guardFn(to, {} as RouteLocationNormalized, next)

      expect(next).toHaveBeenCalledWith({ name: "ledger" })
    })

    it("allows authenticated user to access protected routes", () => {
      const futureExp = Math.floor(Date.now() / 1000) + 3600
      const token = createMockJwt({ sub: "admin", exp: futureExp })
      globalThis.localStorage.setItem("token", token)

      const to = {
        fullPath: "/settings",
        matched: [{ meta: { requiresAuth: true } }],
      } as unknown as RouteLocationNormalized
      const next = vi.fn()

      guardFn(to, {} as RouteLocationNormalized, next)

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
      } as unknown as RouteLocationNormalized
      const next = vi.fn()

      guardFn(to, {} as RouteLocationNormalized, next)

      expect(authStore.token).toBeNull()
      expect(next).toHaveBeenCalledWith({
        name: "login",
        query: { redirect: "/ledger" },
      })
    })
  })
})
