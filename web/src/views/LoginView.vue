<template>
  <q-layout view="hHh lpR fFf">
    <q-page-container>
      <q-page class="flex flex-center bg-grey-2 q-pa-md">
        <q-card class="q-pa-lg shadow-4 login-card" style="width: 100%; max-width: 420px; border-radius: 8px">
          <div class="text-center q-mb-lg">
            <q-avatar size="64px" font-size="36px" color="primary" text-color="white" icon="account_balance_wallet" class="q-mb-sm" />
            <div class="text-h5 text-weight-bold text-primary">Wrangler</div>
            <div class="text-body2 text-grey-7">Sign in to your account</div>
          </div>

          <q-banner v-if="errorMessage" rounded dense inline-actions class="bg-negative text-white q-mb-md">
            <template #avatar>
              <q-icon name="error" color="white" />
            </template>
            {{ errorMessage }}
            <template #action>
              <q-btn flat round dense icon="close" size="sm" @click="errorMessage = ''" />
            </template>
          </q-banner>

          <q-form class="q-gutter-y-md" @submit.prevent="onSubmit">
            <q-input
              v-model="username"
              label="Username"
              outlined
              dense
              autocomplete="username"
              :rules="[val => (!!val && val.trim().length > 0) || 'Username is required']"
              :disable="loading"
            >
              <template #prepend>
                <q-icon name="person" />
              </template>
            </q-input>

            <q-input
              v-model="password"
              :type="showPassword ? 'text' : 'password'"
              label="Password"
              outlined
              dense
              autocomplete="current-password"
              :rules="[val => (!!val && val.length > 0) || 'Password is required']"
              :disable="loading"
            >
              <template #prepend>
                <q-icon name="lock" />
              </template>
              <template #append>
                <q-icon
                  :name="showPassword ? 'visibility_off' : 'visibility'"
                  class="cursor-pointer"
                  @click="showPassword = !showPassword"
                />
              </template>
            </q-input>

            <q-btn type="submit" label="Sign In" color="primary" class="full-width q-mt-md" unelevated :loading="loading" />
          </q-form>
        </q-card>
      </q-page>
    </q-page-container>
  </q-layout>
</template>

<script setup>
import { ref } from "vue"
import { useRoute, useRouter } from "vue-router"
import { useQuasar } from "quasar"
import { useAuthStore } from "../stores/auth.js"

const route = useRoute()
const router = useRouter()
const $q = useQuasar()
const authStore = useAuthStore()

const username = ref("")
const password = ref("")
const showPassword = ref(false)
const loading = ref(false)
const errorMessage = ref("")

async function onSubmit() {
  errorMessage.value = ""
  loading.value = true

  try {
    await authStore.login({
      username: username.value.trim(),
      password: password.value,
    })

    $q.notify({
      type: "positive",
      message: "Signed in successfully",
      position: "top",
      timeout: 2000,
    })

    const redirectPath = route.query.redirect || { name: "ledger" }
    await router.push(redirectPath)
  } catch (err) {
    errorMessage.value = err.message || "Failed to sign in"
    $q.notify({
      type: "negative",
      message: errorMessage.value,
      position: "top",
      timeout: 4000,
    })
  } finally {
    loading.value = false
  }
}
</script>
