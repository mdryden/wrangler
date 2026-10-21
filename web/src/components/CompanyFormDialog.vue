<script setup lang="ts">
import { computed, ref, watch } from "vue"
import { useQuasar, type QForm } from "quasar"
import { useCompanyStore } from "../stores/companies"
import type { Company } from "../types/company"
import type { WaveAccount, WaveBusiness, WaveCategory } from "../types/wave"

const props = defineProps<{
  modelValue: boolean
  company: Company | null
}>()

const emit = defineEmits<{
  (e: "update:modelValue", val: boolean): void
  (e: "saved", company: Company): void
}>()

const $q = useQuasar()
const companyStore = useCompanyStore()

const formRef = ref<QForm | null>(null)
const name = ref<string>("")
const saving = ref<boolean>(false)
const errorMessage = ref<string>("")

// Wave state
const waveToken = ref<string>("")
const testingToken = ref<boolean>(false)
const businesses = ref<WaveBusiness[]>([])
const selectedBusinessId = ref<string | null>(null)
const fetchingAccounts = ref<boolean>(false)
const anchorAccounts = ref<WaveAccount[]>([])
const selectedAnchorId = ref<string | null>(null)
const cachedCategories = ref<WaveCategory[]>([])
const syncingCategories = ref<boolean>(false)
const disconnectingWave = ref<boolean>(false)

const isOpen = computed({
  get: () => props.modelValue,
  set: (val: boolean) => emit("update:modelValue", val),
})

const isEditMode = computed(() => !!props.company)
const isWaveConnected = computed(() => !!props.company?.is_wave_connected)

const businessOptions = computed(() => businesses.value.map(b => ({ label: b.name, value: b.id })))
const anchorOptions = computed(() => anchorAccounts.value.map(a => ({ label: `${a.name} (${a.type})`, value: a.id })))

// Reset or populate fields whenever dialog opens or company changes
watch(
  () => [props.modelValue, props.company] as const,
  async ([visible, comp]) => {
    if (visible) {
      errorMessage.value = ""
      waveToken.value = ""
      businesses.value = []
      selectedBusinessId.value = null
      anchorAccounts.value = []
      selectedAnchorId.value = null
      cachedCategories.value = []

      if (comp) {
        name.value = comp.name || ""
        selectedAnchorId.value = comp.wave_anchor_account_id ?? null
        if (comp.is_wave_connected) {
          try {
            cachedCategories.value = await companyStore.fetchWaveCategories(comp.id)
          } catch {
            // Silently handle initial category load
          }
        }
      } else {
        name.value = ""
      }
    }
  },
  { immediate: true },
)

async function onTestToken(): Promise<void> {
  if (!waveToken.value.trim()) return
  testingToken.value = true
  errorMessage.value = ""
  try {
    const list = await companyStore.testWaveToken(waveToken.value.trim())
    businesses.value = list
    if (list.length > 0) {
      selectedBusinessId.value = list[0].id
      await onBusinessSelected(list[0].id)
    }
    $q.notify({
      type: "positive",
      message: `Token verified. Found ${list.length} accessible businesses.`,
      position: "top",
      timeout: 2500,
    })
  } catch (err) {
    errorMessage.value = err instanceof Error ? err.message : "Failed to verify Wave token"
  } finally {
    testingToken.value = false
  }
}

async function onBusinessSelected(businessId: string | null): Promise<void> {
  if (!businessId || !waveToken.value.trim()) {
    anchorAccounts.value = []
    selectedAnchorId.value = null
    return
  }
  fetchingAccounts.value = true
  errorMessage.value = ""
  try {
    const accountsData = await companyStore.fetchBusinessAccounts(waveToken.value.trim(), businessId)
    anchorAccounts.value = accountsData.anchor_accounts
    if (accountsData.anchor_accounts.length > 0) {
      selectedAnchorId.value = accountsData.anchor_accounts[0].id
    }
  } catch (err) {
    errorMessage.value = err instanceof Error ? err.message : "Failed to fetch accounts for business"
  } finally {
    fetchingAccounts.value = false
  }
}

async function onSyncCategories(): Promise<void> {
  if (!props.company) return
  syncingCategories.value = true
  errorMessage.value = ""
  try {
    const updatedCats = await companyStore.syncWaveCategories(props.company.id)
    cachedCategories.value = updatedCats
    $q.notify({
      type: "positive",
      message: `Synchronized ${updatedCats.length} categories from Wave.`,
      position: "top",
      timeout: 2500,
    })
  } catch (err) {
    errorMessage.value = err instanceof Error ? err.message : "Failed to sync categories"
  } finally {
    syncingCategories.value = false
  }
}

function onConfirmDisconnect(): void {
  if (!props.company) return
  $q.dialog({
    title: "Disconnect Wave",
    message: `Are you sure you want to disconnect Wave from "${props.company.name}"? This will clear credentials and revert the company to CSV export mode.`,
    cancel: true,
    persistent: true,
    ok: {
      label: "Disconnect",
      color: "negative",
      flat: true,
    },
  }).onOk(async () => {
    if (!props.company) return
    disconnectingWave.value = true
    try {
      const updated = await companyStore.disconnectWave(props.company.id)
      cachedCategories.value = []
      emit("saved", updated)
      $q.notify({
        type: "positive",
        message: "Wave disconnected successfully.",
        position: "top",
        timeout: 2500,
      })
    } catch (err) {
      errorMessage.value = err instanceof Error ? err.message : "Failed to disconnect Wave"
    } finally {
      disconnectingWave.value = false
    }
  })
}

async function onSubmit(): Promise<void> {
  errorMessage.value = ""
  saving.value = true

  try {
    let result: Company
    if (isEditMode && props.company) {
      result = await companyStore.updateCompany(props.company.id, {
        name: name.value.trim(),
      })
    } else {
      result = await companyStore.createCompany({
        name: name.value.trim(),
      })
    }

    // Connect Wave credentials if provided
    if (waveToken.value.trim() && selectedBusinessId.value && selectedAnchorId.value) {
      const chosenBiz = businesses.value.find(b => b.id === selectedBusinessId.value)
      result = await companyStore.connectWave(result.id, {
        token: waveToken.value.trim(),
        business_id: selectedBusinessId.value,
        business_name: chosenBiz?.name || "Wave Business",
        anchor_account_id: selectedAnchorId.value,
      })
    }

    $q.notify({
      type: "positive",
      message: `Company "${result.name}" saved successfully`,
      position: "top",
      timeout: 2500,
    })

    emit("saved", result)
    isOpen.value = false
  } catch (err) {
    errorMessage.value = err instanceof Error ? err.message : "Failed to save company"
    $q.notify({
      type: "negative",
      message: errorMessage.value,
      position: "top",
      timeout: 4000,
    })
  } finally {
    saving.value = false
  }
}
</script>

<template>
  <q-dialog v-model="isOpen" persistent>
    <q-card style="min-width: 480px; max-width: 600px; width: 100%">
      <q-card-section class="row items-center q-pb-none">
        <div class="text-h6 text-weight-bold">
          {{ isEditMode ? "Edit Company" : "Add Company" }}
        </div>
        <q-space />
        <q-btn icon="close" flat round dense v-close-popup :disable="saving" />
      </q-card-section>

      <q-card-section class="q-pt-sm">
        <div class="text-caption text-grey-7">
          {{
            isEditMode ? "Update company details and Wave integration settings." : "Configure a new company entity for expense allocation."
          }}
        </div>

        <q-banner v-if="errorMessage" rounded dense inline-actions class="bg-negative text-white q-mt-sm">
          <template #avatar>
            <q-icon name="error" color="white" />
          </template>
          {{ errorMessage }}
          <template #action>
            <q-btn flat round dense icon="close" size="sm" @click="errorMessage = ''" />
          </template>
        </q-banner>

        <q-form ref="formRef" class="q-gutter-y-md q-mt-sm" @submit.prevent="onSubmit">
          <q-input
            v-model="name"
            label="Company Name *"
            placeholder="e.g. Acme Corp or Consulting LLC"
            outlined
            dense
            :rules="[val => (!!val && val.trim().length > 0) || 'Company name is required']"
            :disable="saving"
            autofocus
          >
            <template #prepend>
              <q-icon name="business" />
            </template>
          </q-input>

          <!-- Wave Integration Card -->
          <q-card flat bordered class="q-pa-sm bg-grey-1 rounded-borders">
            <div class="row items-center justify-between q-mb-sm">
              <div class="row items-center q-gutter-x-sm">
                <q-icon name="sync_alt" size="sm" color="primary" />
                <span class="text-subtitle2 text-weight-bold">Wave Integration</span>
              </div>
              <q-chip
                :color="isWaveConnected ? 'positive' : 'grey-6'"
                text-color="white"
                dense
                :icon="isWaveConnected ? 'cloud_done' : 'description'"
                data-testid="wave-status-chip"
              >
                {{ isWaveConnected ? "Connected to Wave" : "CSV Export Only" }}
              </q-chip>
            </div>

            <!-- Connected View -->
            <div v-if="isWaveConnected" class="q-gutter-y-sm">
              <div class="text-caption text-grey-8">
                Linked Business: <strong>{{ props.company?.wave_business_name || props.company?.wave_business_id }}</strong>
              </div>
              <div class="text-caption text-grey-7">
                Cached Expense Categories: <strong>{{ cachedCategories.length }}</strong>
              </div>

              <div class="row items-center q-gutter-x-sm q-mt-xs">
                <q-btn
                  outline
                  dense
                  size="sm"
                  color="primary"
                  icon="refresh"
                  label="Sync Categories"
                  :loading="syncingCategories"
                  data-testid="btn-sync-categories"
                  @click="onSyncCategories"
                />
                <q-btn
                  flat
                  dense
                  size="sm"
                  color="negative"
                  icon="link_off"
                  label="Disconnect Wave"
                  :loading="disconnectingWave"
                  data-testid="btn-disconnect-wave"
                  @click="onConfirmDisconnect"
                />
              </div>
            </div>

            <!-- Setup / Connect View -->
            <div v-else class="q-gutter-y-sm">
              <div class="text-caption text-grey-7">
                Connect your Wave account using a Full Access Bearer Token to enable direct synchronization.
              </div>

              <div class="row q-col-gutter-sm items-center">
                <div class="col-grow">
                  <q-input
                    v-model="waveToken"
                    type="password"
                    label="Wave Full Access Token"
                    placeholder="Enter token from Wave Developer Portal"
                    outlined
                    dense
                    data-testid="input-wave-token"
                    :disable="testingToken || saving"
                  />
                </div>
                <div class="col-auto">
                  <q-btn
                    color="primary"
                    unelevated
                    dense
                    label="Test & Fetch Businesses"
                    :loading="testingToken"
                    :disable="!waveToken.trim()"
                    data-testid="btn-test-token"
                    @click="onTestToken"
                  />
                </div>
              </div>

              <!-- Business selection dropdown -->
              <div v-if="businesses.length > 0" class="q-gutter-y-sm q-mt-xs">
                <q-select
                  v-model="selectedBusinessId"
                  :options="businessOptions"
                  emit-value
                  map-options
                  label="Select Wave Business *"
                  outlined
                  dense
                  data-testid="select-wave-business"
                  @update:model-value="onBusinessSelected"
                />

                <q-select
                  v-if="anchorAccounts.length > 0"
                  v-model="selectedAnchorId"
                  :options="anchorOptions"
                  emit-value
                  map-options
                  label="Select Anchor Account (Reimbursement / Bank) *"
                  outlined
                  dense
                  :loading="fetchingAccounts"
                  data-testid="select-wave-anchor"
                />
              </div>
            </div>
          </q-card>

          <q-card-actions align="right" class="q-pt-md q-px-none">
            <q-btn flat label="Cancel" color="grey-7" v-close-popup :disable="saving" />
            <q-btn type="submit" :label="isEditMode ? 'Update Company' : 'Create Company'" color="primary" unelevated :loading="saving" />
          </q-card-actions>
        </q-form>
      </q-card-section>
    </q-card>
  </q-dialog>
</template>
