/**
 * Decodes a base64url or base64 string handling UTF-8 properly.
 */
function base64UrlDecode(str: string): string {
  const base64 = str.replace(/-/g, "+").replace(/_/g, "/")
  const padded = base64.padEnd(base64.length + ((4 - (base64.length % 4)) % 4), "=")
  const binary = atob(padded)
  const bytes = new Uint8Array(binary.length)
  for (let i = 0; i < binary.length; i++) {
    bytes[i] = binary.charCodeAt(i)
  }
  return new TextDecoder().decode(bytes)
}

export interface JwtPayload {
  sub?: string
  exp?: number
  [key: string]: unknown
}

/**
 * Parses and returns the decoded JSON payload from a JWT token.
 * Returns null if the token is invalid or malformed.
 */
export function parseJwt(token: string | null | undefined): JwtPayload | null {
  if (!token || typeof token !== "string") {
    return null
  }
  try {
    const parts = token.split(".")
    if (parts.length !== 3) {
      return null
    }
    const decoded = base64UrlDecode(parts[1])
    return JSON.parse(decoded) as JwtPayload
  } catch {
    return null
  }
}

/**
 * Validates whether a JWT token is structurally valid and not expired.
 * Checks the standard `exp` claim against current time (in seconds).
 */
export function isTokenValid(token: string | null | undefined): boolean {
  const payload = parseJwt(token)
  if (!payload) {
    return false
  }
  if (typeof payload.exp === "number") {
    // exp is in seconds, Date.now() is in milliseconds
    return payload.exp * 1000 > Date.now()
  }
  return true
}
