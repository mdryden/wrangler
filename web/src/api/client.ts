import { getActivePinia } from "pinia"
import router from "../router"
import { useAuthStore } from "../stores/auth"

export interface RequestOptions extends Omit<RequestInit, "body"> {
  baseUrl?: string
  params?: Record<string, unknown>
  skipAuth?: boolean
  responseType?: "json" | "text" | "blob" | "raw"
  body?: unknown
}

export interface ApiClientConfig {
  baseUrl?: string
  getToken?: () => string | null
  onUnauthorized?: () => void
  fetch?: typeof fetch
}

export class ApiError extends Error {
  readonly status: number
  readonly statusText: string
  readonly data: unknown
  readonly response: Response

  constructor(status: number, statusText: string, data: unknown, response: Response, message?: string) {
    super(message || statusText || `HTTP ${status}`)
    this.name = "ApiError"
    this.status = status
    this.statusText = statusText
    this.data = data
    this.response = response
  }
}

export function resolveUrl(endpoint: string, baseUrl = "", params?: Record<string, unknown>): string {
  let url: string

  if (/^https?:\/\//i.test(endpoint)) {
    url = endpoint
  } else if (!baseUrl) {
    url = endpoint.startsWith("/") ? endpoint : `/${endpoint}`
  } else {
    const cleanBase = baseUrl.replace(/\/+$/, "")
    const cleanPath = endpoint.replace(/^\/+/, "")
    if (cleanBase.endsWith("/api") && cleanPath.startsWith("api/")) {
      url = `${cleanBase}/${cleanPath.slice(4)}`
    } else {
      url = `${cleanBase}/${cleanPath}`
    }
  }

  if (params && Object.keys(params).length > 0) {
    const searchParams = new URLSearchParams()
    for (const [key, val] of Object.entries(params)) {
      if (val !== undefined && val !== null) {
        searchParams.append(key, String(val))
      }
    }
    const queryString = searchParams.toString()
    if (queryString) {
      const separator = url.includes("?") ? "&" : "?"
      url = `${url}${separator}${queryString}`
    }
  }

  return url
}

export function defaultGetToken(): string | null {
  try {
    if (getActivePinia()) {
      const auth = useAuthStore()
      if (auth.token) return auth.token
    }
  } catch {
    // Pinia not ready
  }

  try {
    if (typeof localStorage !== "undefined") {
      return localStorage.getItem("token")
    }
  } catch {
    // Storage inaccessible
  }

  return null
}

export function defaultOnUnauthorized(): void {
  try {
    if (getActivePinia()) {
      const auth = useAuthStore()
      auth.logout()
    }
  } catch {
    // Pinia not active
  }

  try {
    if (typeof localStorage !== "undefined") {
      localStorage.removeItem("token")
      localStorage.removeItem("user")
    }
  } catch {
    // Storage inaccessible
  }

  try {
    if (router.currentRoute.value?.name !== "login") {
      const redirect = router.currentRoute.value?.fullPath
      router.push({
        name: "login",
        query: redirect && redirect !== "/" ? { redirect } : undefined,
      })
    }
  } catch {
    // Router unavailable
  }
}

function isBinaryOrFormData(value: unknown): boolean {
  if (!value || typeof value !== "object") return false
  if (typeof FormData !== "undefined" && value instanceof FormData) return true
  if (typeof Blob !== "undefined" && value instanceof Blob) return true
  if (typeof ArrayBuffer !== "undefined" && value instanceof ArrayBuffer) return true
  if (typeof URLSearchParams !== "undefined" && value instanceof URLSearchParams) return true
  return false
}

export interface ApiClient {
  <T = unknown>(endpoint: string, options?: RequestOptions): Promise<T>
  get<T = unknown>(endpoint: string, options?: RequestOptions): Promise<T>
  post<T = unknown>(endpoint: string, body?: unknown, options?: RequestOptions): Promise<T>
  put<T = unknown>(endpoint: string, body?: unknown, options?: RequestOptions): Promise<T>
  patch<T = unknown>(endpoint: string, body?: unknown, options?: RequestOptions): Promise<T>
  delete<T = unknown>(endpoint: string, options?: RequestOptions): Promise<T>
}

export function createApiClient(config: ApiClientConfig = {}): ApiClient {
  const fetchFn = config.fetch || globalThis.fetch
  const defaultBaseUrl = config.baseUrl ?? ""
  const getToken = config.getToken ?? defaultGetToken
  const onUnauthorized = config.onUnauthorized ?? defaultOnUnauthorized

  const request = async function <T = unknown>(endpoint: string, options: RequestOptions = {}): Promise<T> {
    const baseUrl = options.baseUrl !== undefined ? options.baseUrl : defaultBaseUrl
    const url = resolveUrl(endpoint, baseUrl, options.params)

    const headers = new Headers(options.headers || {})

    if (!options.skipAuth && !headers.has("Authorization")) {
      const token = getToken()
      if (token) {
        headers.set("Authorization", `Bearer ${token}`)
      }
    }

    let body = options.body
    if (body !== undefined && body !== null) {
      if (!isBinaryOrFormData(body) && typeof body === "object") {
        if (!headers.has("Content-Type")) {
          headers.set("Content-Type", "application/json")
        }
        body = JSON.stringify(body)
      }
    }

    if (!headers.has("Accept") && options.responseType !== "blob" && options.responseType !== "raw") {
      headers.set("Accept", "application/json, text/plain, */*")
    }

    const { baseUrl: _baseUrl, params: _params, skipAuth: _skipAuth, responseType, ...fetchOptions } = options

    const response = await fetchFn(url, {
      ...fetchOptions,
      headers,
      body: body as BodyInit | null | undefined,
    })

    if (!response.ok) {
      if (response.status === 401) {
        onUnauthorized()
      }

      let errorData: unknown = null
      let errorMessage = response.statusText || `Request failed with status ${response.status}`

      try {
        const contentType = response.headers.get("content-type") || ""
        if (contentType.includes("application/json")) {
          errorData = await response.json()
          if (errorData && typeof errorData === "object") {
            const detail = (errorData as Record<string, unknown>).detail
            if (typeof detail === "string") {
              errorMessage = detail
            } else if (Array.isArray(detail)) {
              errorMessage = detail.map((e: { msg?: string }) => e.msg || JSON.stringify(e)).join(", ")
            } else if (typeof (errorData as Record<string, unknown>).message === "string") {
              errorMessage = (errorData as Record<string, unknown>).message as string
            }
          }
        } else {
          const text = await response.text()
          if (text) {
            errorMessage = text
            errorData = text
          }
        }
      } catch {
        // Body reading failed, retain status message
      }

      throw new ApiError(response.status, response.statusText, errorData, response, errorMessage)
    }

    if (responseType === "raw") {
      return response as unknown as T
    }

    if (responseType === "blob") {
      return (await response.blob()) as unknown as T
    }

    if (responseType === "text") {
      return (await response.text()) as unknown as T
    }

    if (response.status === 204 || response.headers.get("content-length") === "0") {
      return undefined as unknown as T
    }

    const contentType = response.headers.get("content-type") || ""
    if (contentType.includes("application/json")) {
      return (await response.json()) as T
    }

    const text = await response.text()
    if (!text) {
      return undefined as unknown as T
    }

    try {
      return JSON.parse(text) as T
    } catch {
      return text as unknown as T
    }
  }

  request.get = <T = unknown>(endpoint: string, options: RequestOptions = {}) => request<T>(endpoint, { ...options, method: "GET" })

  request.post = <T = unknown>(endpoint: string, body?: unknown, options: RequestOptions = {}) =>
    request<T>(endpoint, { ...options, method: "POST", body })

  request.put = <T = unknown>(endpoint: string, body?: unknown, options: RequestOptions = {}) =>
    request<T>(endpoint, { ...options, method: "PUT", body })

  request.patch = <T = unknown>(endpoint: string, body?: unknown, options: RequestOptions = {}) =>
    request<T>(endpoint, { ...options, method: "PATCH", body })

  request.delete = <T = unknown>(endpoint: string, options: RequestOptions = {}) => request<T>(endpoint, { ...options, method: "DELETE" })

  return request as ApiClient
}

export const apiClient: ApiClient = createApiClient()
