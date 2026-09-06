<template>
  <q-layout view="hHh lpR fFf">
    <q-header elevated class="bg-primary text-white">
      <q-toolbar>
        <q-toolbar-title class="row items-center">
          <q-icon name="account_balance_wallet" size="sm" class="q-mr-sm" />
          Wrangler
        </q-toolbar-title>

        <div class="row items-center q-gutter-sm">
          <span class="text-caption text-weight-medium">
            {{ authStore.username || "User" }}
          </span>
          <q-btn flat dense round icon="logout" aria-label="Logout" title="Logout" @click="onLogout" />
        </div>
      </q-toolbar>
    </q-header>

    <q-page-container>
      <router-view />
    </q-page-container>
  </q-layout>
</template>

<script setup lang="ts">
import { useRouter } from "vue-router"
import { useAuthStore } from "../stores/auth"

const router = useRouter()
const authStore = useAuthStore()

function onLogout(): void {
  authStore.logout()
  router.push({ name: "login" })
}
</script>
