import { describe, it, expect } from "vitest"
import { parseJwt, isTokenValid, type JwtPayload } from "../src/utils/jwt"

// Helper to create mock unsigned JWT
function createMockJwt(payload: JwtPayload): string {
  const header = btoa(JSON.stringify({ alg: "HS256", typ: "JWT" }))
  const body = btoa(JSON.stringify(payload)).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "")
  const signature = "mock_signature"
  return `${header}.${body}.${signature}`
}

describe("JWT Utilities", () => {
  describe("parseJwt", () => {
    it("returns null for invalid inputs", () => {
      expect(parseJwt(null)).toBeNull()
      expect(parseJwt(undefined)).toBeNull()
      expect(parseJwt("")).toBeNull()
      expect(parseJwt(123 as unknown as string)).toBeNull()
      expect(parseJwt("not.a.valid.jwt.token")).toBeNull()
      expect(parseJwt("part1.part2")).toBeNull()
      expect(parseJwt("part1.bad_base64!@#.part3")).toBeNull()
    })

    it("correctly parses valid JWT payload", () => {
      const token = createMockJwt({ sub: "admin", exp: 1700000000 })
      const parsed = parseJwt(token)
      expect(parsed).toEqual({ sub: "admin", exp: 1700000000 })
    })
  })

  describe("isTokenValid", () => {
    it("returns false for null, invalid, or malformed tokens", () => {
      expect(isTokenValid(null)).toBe(false)
      expect(isTokenValid("")).toBe(false)
      expect(isTokenValid("invalid.token")).toBe(false)
    })

    it("returns true for non-expired tokens", () => {
      const futureExp = Math.floor(Date.now() / 1000) + 3600
      const token = createMockJwt({ sub: "admin", exp: futureExp })
      expect(isTokenValid(token)).toBe(true)
    })

    it("returns false for expired tokens", () => {
      const pastExp = Math.floor(Date.now() / 1000) - 3600
      const token = createMockJwt({ sub: "admin", exp: pastExp })
      expect(isTokenValid(token)).toBe(false)
    })

    it("returns true for tokens without exp claim", () => {
      const token = createMockJwt({ sub: "admin" })
      expect(isTokenValid(token)).toBe(true)
    })
  })
})
