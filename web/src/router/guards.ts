import type { Router } from "vue-router"
import { useAuthStore } from "../stores/auth"

export function setupNavigationGuards(router: Router): void {
  router.beforeEach((to, _from, next) => {
    const authStore = useAuthStore()

    // Automatically purge stale or expired tokens
    if (authStore.token && !authStore.isAuthenticated) {
      authStore.logout()
    }

    // Secure-by-default: require authentication unless explicitly set to false
    const requiresAuth = to.matched.some(record => record.meta.requiresAuth !== false)
    const isGuestOnly = to.matched.some(record => record.meta.guestOnly === true)

    if (requiresAuth && !authStore.isAuthenticated) {
      next({
        name: "login",
        query: {
          redirect: to.fullPath !== "/login" ? to.fullPath : undefined,
        },
      })
    } else if (isGuestOnly && authStore.isAuthenticated) {
      next({ name: "ledger" })
    } else {
      next()
    }
  })
}
