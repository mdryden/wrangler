import { defineStore } from "pinia"
import { ref, computed } from "vue"
import { parseJwt, isTokenValid } from "../utils/jwt"

export interface LoginCredentials {
  username: string
  password: string
}

export interface LoginResponse {
  access_token: string
  token_type: string
  [key: string]: unknown
}

interface StorageAdapter {
  getItem(key: string): string | null
  setItem(key: string, value: string): void
  removeItem(key: string): void
}

const storage: StorageAdapter = {
  getItem(key: string): string | null {
    try {
      return typeof localStorage !== "undefined" ? localStorage.getItem(key) : null
    } catch {
      return null
    }
  },
  setItem(key: string, value: string): void {
    try {
      if (typeof localStorage !== "undefined") {
        localStorage.setItem(key, value)
      }
    } catch {
      // Ignore write errors (quota exceeded, private mode)
    }
  },
  removeItem(key: string): void {
    try {
      if (typeof localStorage !== "undefined") {
        localStorage.removeItem(key)
      }
    } catch {
      // Ignore errors
    }
  },
}

export const useAuthStore = defineStore("auth", () => {
  const token = ref<string | null>(storage.getItem("token") || null)
  const user = ref<string | null>(storage.getItem("user") || null)

  const isAuthenticated = computed<boolean>(() => {
    return isTokenValid(token.value)
  })

  const username = computed<string>(() => {
    if (user.value) return user.value
    const payload = parseJwt(token.value)
    return payload?.sub || ""
  })

  async function login(credentials: LoginCredentials): Promise<LoginResponse> {
    const response = await fetch("/api/login", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify(credentials),
    })

    if (!response.ok) {
      let errorMessage = "Invalid username or password"
      try {
        const errorData = await response.json()
        if (errorData.detail) {
          errorMessage = Array.isArray(errorData.detail)
            ? errorData.detail.map((e: { msg: string }) => e.msg).join(", ")
            : String(errorData.detail)
        }
      } catch {
        // Fallback to default message
      }
      throw new Error(errorMessage)
    }

    const data = (await response.json()) as LoginResponse
    token.value = data.access_token
    storage.setItem("token", data.access_token)

    const payload = parseJwt(data.access_token)
    const subject = payload?.sub || credentials.username
    user.value = subject
    storage.setItem("user", subject)

    return data
  }

  function logout(): void {
    token.value = null
    user.value = null
    storage.removeItem("token")
    storage.removeItem("user")
  }

  return {
    token,
    user,
    username,
    isAuthenticated,
    login,
    logout,
  }
})
