<template>
  <q-layout view="hHh Lpr fFf">
    <q-header elevated class="bg-primary text-white">
      <q-toolbar>
        <q-btn flat dense round icon="menu" aria-label="Menu" title="Toggle navigation drawer" @click="toggleLeftDrawer" />

        <q-toolbar-title class="row items-center cursor-pointer" @click="router.push({ name: 'ledger' })">
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

    <q-drawer v-model="leftDrawerOpen" show-if-above bordered side="left" class="bg-grey-1" :width="240">
      <q-scroll-area class="fit">
        <q-list padding class="text-grey-8">
          <q-item-label header class="text-uppercase text-weight-bold text-grey-6" style="font-size: 0.72rem; letter-spacing: 0.08em">
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
          >
            <q-item-section avatar>
              <q-icon :name="item.icon" />
            </q-item-section>
            <q-item-section>
              <q-item-label>{{ item.label }}</q-item-label>
            </q-item-section>
          </q-item>
        </q-list>
      </q-scroll-area>
    </q-drawer>

    <q-page-container>
      <router-view />
    </q-page-container>
  </q-layout>
</template>

<script setup lang="ts">
import { ref } from "vue"
import { useRouter } from "vue-router"
import { useAuthStore } from "../stores/auth"
import { navItems } from "./nav"

const router = useRouter()
const authStore = useAuthStore()

const leftDrawerOpen = ref<boolean>(true)

function toggleLeftDrawer(): void {
  leftDrawerOpen.value = !leftDrawerOpen.value
}

function onLogout(): void {
  authStore.logout()
  router.push({ name: "login" })
}
</script>
