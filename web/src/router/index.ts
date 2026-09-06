import { createRouter, createWebHistory, createMemoryHistory, type Router } from "vue-router"
import { routes } from "./routes"
import { setupNavigationGuards } from "./guards"

const history = typeof window !== "undefined" ? createWebHistory(import.meta.env?.BASE_URL) : createMemoryHistory()

const router: Router = createRouter({
  history,
  routes,
})

setupNavigationGuards(router)

export { routes, setupNavigationGuards }
export default router
