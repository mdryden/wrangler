<script setup lang="ts">
import { ref, onMounted, onUnmounted } from "vue"
import { useRouter } from "vue-router"
import { useAuthStore } from "../stores/auth"
import { useAppStore } from "../stores/app"
import { navItems, handleSidebarKeydown } from "./nav"

const router = useRouter()
const authStore = useAuthStore()
const appStore = useAppStore()

// Keep drawer visible; collapsing is handled by appStore.sidebarCollapsed and :mini
const drawerOpen = ref<boolean>(true)

function handleKeydown(event: KeyboardEvent): void {
  handleSidebarKeydown(event, () => appStore.toggleSidebar())
}

onMounted(() => {
  window.addEventListener("keydown", handleKeydown)
})

onUnmounted(() => {
  window.removeEventListener("keydown", handleKeydown)
})

function onLogout(): void {
  authStore.logout()
  router.push({ name: "login" })
}

defineExpose({
  drawerOpen,
  handleKeydown,
  onLogout,
})
</script>

<template>
  <q-layout view="lHh Lpr lFf">
    <!-- Top Header Toolbar (starts to the right of the full-height drawer) -->
    <q-header elevated class="bg-primary text-white">
      <q-toolbar>
        <!-- Dedicated external sidebar trigger button, positioned flush outside the sidebar border -->
        <q-btn
          flat
          dense
          round
          class="q-mr-sm"
          aria-label="Toggle sidebar"
          :title="appStore.sidebarCollapsed ? 'Expand sidebar (Ctrl+B)' : 'Collapse sidebar (Ctrl+B)'"
          @click="appStore.toggleSidebar"
        >
          <!-- Lucide panel-left SVG icon -->
          <svg
            xmlns="http://www.w3.org/2000/svg"
            width="20"
            height="20"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            stroke-width="2"
            stroke-linecap="round"
            stroke-linejoin="round"
          >
            <rect width="18" height="18" x="3" y="3" rx="2" />
            <path d="M9 3v18" />
          </svg>
          <q-tooltip anchor="bottom right" self="top left" :offset="[8, 8]">
            {{ appStore.sidebarCollapsed ? "Expand sidebar (Ctrl+B)" : "Collapse sidebar (Ctrl+B)" }}
          </q-tooltip>
        </q-btn>

        <q-toolbar-title class="row items-center text-weight-medium text-body1">
          <!-- Optional page breadcrumb or title context -->
        </q-toolbar-title>

        <div class="row items-center q-gutter-sm">
          <span class="text-caption text-weight-medium">
            {{ authStore.username || "User" }}
          </span>
          <q-btn flat dense round icon="logout" aria-label="Logout" title="Logout" @click="onLogout" />
        </div>
      </q-toolbar>
    </q-header>

    <!-- Full-height Drawer -->
    <q-drawer
      v-model="drawerOpen"
      show-if-above
      bordered
      side="left"
      class="bg-grey-1 text-grey-8"
      :mini="appStore.sidebarCollapsed"
      :mini-width="60"
      :width="240"
      :breakpoint="0"
    >
      <q-scroll-area class="fit">
        <!-- Top branding inside drawer -->
        <div
          class="row items-center q-px-md q-py-md cursor-pointer no-wrap"
          :class="appStore.sidebarCollapsed ? 'justify-center' : 'justify-start'"
          @click="router.push({ name: 'ledger' })"
        >
          <q-icon name="account_balance_wallet" size="sm" color="primary" />
          <span v-show="!appStore.sidebarCollapsed" class="text-subtitle1 text-weight-bold text-grey-9 q-ml-sm"> Wrangler </span>
        </div>

        <q-separator />

        <!-- Navigation Section -->
        <q-list padding class="text-grey-8">
          <q-item-label
            v-show="!appStore.sidebarCollapsed"
            header
            class="text-uppercase text-weight-bold text-grey-6"
            style="font-size: 0.72rem; letter-spacing: 0.08em"
          >
            Navigation
          </q-item-label>

          <q-item
            v-for="item in navItems"
            :key="item.name"
            clickable
            v-ripple
            :to="{ name: item.name }"
            exact
            active-class="text-primary bg-blue-1 text-weight-bold"
            class="rounded-borders q-mx-xs q-mb-xs"
            :class="{ 'sidebar-mini-item': appStore.sidebarCollapsed }"
          >
            <q-item-section
              avatar
              :class="{ 'sidebar-mini-avatar': appStore.sidebarCollapsed }"
              :style="appStore.sidebarCollapsed ? 'min-width: 0; padding: 0;' : 'min-width: 40px'"
            >
              <q-icon :name="item.icon" size="sm" />
            </q-item-section>

            <q-item-section v-if="!appStore.sidebarCollapsed">
              <q-item-label>{{ item.label }}</q-item-label>
            </q-item-section>

            <!-- Contextual Tooltip for Mini Rail Mode -->
            <q-tooltip
              v-if="appStore.sidebarCollapsed"
              anchor="center right"
              self="center left"
              :offset="[14, 14]"
              class="bg-grey-9 text-white shadow-3 text-caption text-weight-medium"
            >
              {{ item.label }}
            </q-tooltip>
          </q-item>
        </q-list>
      </q-scroll-area>
    </q-drawer>

    <!-- Main Page Container -->
    <q-page-container>
      <router-view />
    </q-page-container>
  </q-layout>
</template>

<style scoped>
.sidebar-mini-item {
  justify-content: center;
  padding-left: 0 !important;
  padding-right: 0 !important;
}

.sidebar-mini-avatar {
  min-width: 0 !important;
  padding: 0 !important;
  align-items: center !important;
  justify-content: center !important;
}
</style>
