import { afterEach, vi } from "vitest"

// Polyfill window.matchMedia for Quasar responsive layout checks
if (typeof window !== "undefined") {
  Object.defineProperty(window, "matchMedia", {
    writable: true,
    value: vi.fn().mockImplementation((query: string) => ({
      matches: false,
      media: query,
      onchange: null,
      addListener: vi.fn(), // deprecated
      removeListener: vi.fn(), // deprecated
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      dispatchEvent: vi.fn(),
    })),
  })

  // Polyfill ResizeObserver
  global.ResizeObserver = class ResizeObserver {
    observe = vi.fn()
    unobserve = vi.fn()
    disconnect = vi.fn()
  } as unknown as typeof ResizeObserver

  // Polyfill IntersectionObserver
  global.IntersectionObserver = class IntersectionObserver {
    observe = vi.fn()
    unobserve = vi.fn()
    disconnect = vi.fn()
    takeRecords = vi.fn().mockReturnValue([])
  } as unknown as typeof IntersectionObserver
}

// Clean up DOM between test runs to avoid cross-test element leaks
afterEach(() => {
  document.body.innerHTML = ""
})
