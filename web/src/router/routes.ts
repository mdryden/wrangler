import type { RouteRecordRaw } from "vue-router"

export const routes: RouteRecordRaw[] = [
  {
    path: "/login",
    name: "login",
    component: () => import("../views/LoginView.vue"),
    meta: {
      requiresAuth: false,
      guestOnly: true,
    },
  },
  {
    path: "/",
    component: () => import("../layouts/MainLayout.vue"),
    meta: {
      requiresAuth: true,
    },
    children: [
      {
        path: "",
        redirect: "/ledger",
      },
      {
        path: "ledger",
        name: "ledger",
        component: () => import("../views/LedgerView.vue"),
        meta: {
          requiresAuth: true,
        },
      },
      {
        path: "manual-entry",
        name: "manual-entry",
        component: () => import("../views/ManualEntryView.vue"),
        meta: {
          requiresAuth: true,
        },
      },
      {
        path: "sync-manager",
        name: "sync-manager",
        component: () => import("../views/SyncManagerView.vue"),
        meta: {
          requiresAuth: true,
        },
      },
      {
        path: "settings",
        name: "settings",
        component: () => import("../views/SettingsView.vue"),
        meta: {
          requiresAuth: true,
        },
      },
    ],
  },
  {
    path: "/:catchAll(.*)*",
    redirect: "/ledger",
  },
]
