<template>
  <q-chip
    :color="statusInfo.color"
    :text-color="statusInfo.textColor"
    :icon="statusInfo.icon"
    size="sm"
    dense
    class="text-weight-bold"
    :aria-label="`Wave Status: ${statusInfo.label}`"
  >
    {{ statusInfo.label }}
    <q-tooltip anchor="top middle" self="bottom middle">
      <div>{{ statusInfo.description }}</div>
      <div v-if="formattedExpiration" class="text-caption">
        {{ status === "expired" ? "Expired on:" : "Expires:" }} {{ formattedExpiration }}
      </div>
    </q-tooltip>
  </q-chip>
</template>

<script setup lang="ts">
import { computed } from "vue"
import type { Company } from "../types/company"
import { getCompanyTokenStatus, getTokenStatusInfo } from "../types/company"

const props = defineProps<{
  company: Company
}>()

const status = computed(() => getCompanyTokenStatus(props.company))
const statusInfo = computed(() => getTokenStatusInfo(status.value))

const formattedExpiration = computed(() => {
  if (!props.company.wave_token_expires_at) return null
  try {
    const date = new Date(props.company.wave_token_expires_at)
    if (Number.isNaN(date.getTime())) return null
    return date.toLocaleString()
  } catch {
    return null
  }
})
</script>
