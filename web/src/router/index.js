import { createRouter, createWebHistory, createMemoryHistory } from "vue-router"
import { routes } from "./routes.js"
import { setupNavigationGuards } from "./guards.js"

const history = typeof window !== "undefined" ? createWebHistory(import.meta.env?.BASE_URL) : createMemoryHistory()

const router = createRouter({
  history,
  routes,
})

setupNavigationGuards(router)

export { routes, setupNavigationGuards }
export default router
