import { defineStore } from "pinia"
import { ref, computed } from "vue"
import { parseJwt, isTokenValid } from "../utils/jwt.js"

const storage = {
  getItem(key) {
    try {
      return typeof localStorage !== "undefined" ? localStorage.getItem(key) : null
    } catch {
      return null
    }
  },
  setItem(key, value) {
    try {
      if (typeof localStorage !== "undefined") {
        localStorage.setItem(key, value)
      }
    } catch {
      // Ignore write errors (quota exceeded, private mode)
    }
  },
  removeItem(key) {
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
  const token = ref(storage.getItem("token") || null)
  const user = ref(storage.getItem("user") || null)

  const isAuthenticated = computed(() => {
    return isTokenValid(token.value)
  })

  const username = computed(() => {
    if (user.value) return user.value
    const payload = parseJwt(token.value)
    return payload?.sub || ""
  })

  async function login(credentials) {
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
          errorMessage = Array.isArray(errorData.detail) ? errorData.detail.map(e => e.msg).join(", ") : errorData.detail
        }
      } catch {
        // Fallback to default message
      }
      throw new Error(errorMessage)
    }

    const data = await response.json()
    token.value = data.access_token
    storage.setItem("token", data.access_token)

    const payload = parseJwt(data.access_token)
    const subject = payload?.sub || credentials.username
    user.value = subject
    storage.setItem("user", subject)

    return data
  }

  function logout() {
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
