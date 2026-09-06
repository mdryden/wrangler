<template>
  <q-layout view="hHh lpR fFf">
    <q-header elevated class="bg-primary text-white">
      <q-toolbar>
        <q-toolbar-title>
          {{ appStore.appName }}
        </q-toolbar-title>
        <q-badge color="secondary" label="Vue 3 + Quasar + Pinia" class="q-mr-sm" />
      </q-toolbar>
    </q-header>

    <q-page-container>
      <q-page class="flex flex-center q-pa-md">
        <q-card class="q-pa-lg text-center" style="max-width: 480px; width: 100%">
          <div class="text-h5 q-mb-md">{{ appStore.appName }} Foundation</div>
          <div class="text-body1 text-grey-7 q-mb-lg">Frontend initialized with Vue 3.5, Quasar 2.30, and Pinia 3.</div>
          <q-btn color="primary" icon="check_circle" label="Ready" unelevated />
        </q-card>
      </q-page>
    </q-page-container>
  </q-layout>
</template>

<script setup>
import { useAppStore } from "./stores/app.js"

const appStore = useAppStore()
</script>
