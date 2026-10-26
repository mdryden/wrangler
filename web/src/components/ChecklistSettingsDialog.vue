<script setup lang="ts">
import { computed, ref, watch } from "vue"
import { useQuasar } from "quasar"
import { useCompanyStore } from "../stores/companies"
import { useChecklistStore } from "../stores/checklist"

const props = defineProps<{
  modelValue: boolean
}>()

const emit = defineEmits<{
  (e: "update:modelValue", val: boolean): void
  (e: "saved"): void
}>()

const $q = useQuasar()
const companyStore = useCompanyStore()
const checklistStore = useChecklistStore()

const isOpen = computed({
  get: () => props.modelValue,
  set: (val: boolean) => emit("update:modelValue", val),
})

const selectedCompanyId = ref<string | null>(null)
const chequingAccountId = ref<string | null>(null)
const mastercardAccountId = ref<string | null>(null)
const taxExpenseAccountId = ref<string | null>(null)
const taxPayableAccountId = ref<string | null>(null)
const waveWebBusinessSlug = ref<string>("d2977f10-6793-4504-a139-f0d6872b2628")
const lastChequingTxDate = ref<string | null>(null)
const lastMastercardTxDate = ref<string | null>(null)

const saving = ref<boolean>(false)
const loadingAccounts = ref<boolean>(false)

const companyOptions = computed(() =>
  companyStore.companies.map(c => ({
    label: c.name,
    value: c.id,
  })),
)

const bankAndCcOptions = computed(() =>
  (checklistStore.groupedWaveAccounts?.bank_and_cc_accounts || []).map(a => ({
    label: `${a.name} (${a.type})`,
    value: a.id,
  })),
)

const expenseOptions = computed(() =>
  (checklistStore.groupedWaveAccounts?.expense_accounts || []).map(a => ({
    label: a.name,
    value: a.id,
  })),
)

const liabilityOptions = computed(() =>
  (checklistStore.groupedWaveAccounts?.liability_accounts || []).map(a => ({
    label: a.name,
    value: a.id,
  })),
)

async function loadWaveAccounts(companyId: string) {
  loadingAccounts.value = true
  try {
    await checklistStore.fetchWaveAccounts(companyId)
  } catch (err) {
    const msg = err instanceof Error ? err.message : "Failed to load Wave accounts for company"
    $q.notify({
      type: "negative",
      message: msg,
    })
  } finally {
    loadingAccounts.value = false
  }
}

watch(
  () => props.modelValue,
  async visible => {
    if (visible) {
      if (!companyStore.companies.length) {
        await companyStore.fetchCompanies()
      }
      if (!checklistStore.config) {
        await checklistStore.fetchConfig()
      }

      const cfg = checklistStore.config
      selectedCompanyId.value = cfg?.company_id ?? null
      chequingAccountId.value = cfg?.chequing_wave_account_id ?? null
      mastercardAccountId.value = cfg?.mastercard_wave_account_id ?? null
      taxExpenseAccountId.value = cfg?.tax_expense_wave_account_id ?? null
      taxPayableAccountId.value = cfg?.tax_payable_wave_account_id ?? null
      waveWebBusinessSlug.value = cfg?.wave_web_business_slug || "d2977f10-6793-4504-a139-f0d6872b2628"
      lastChequingTxDate.value = cfg?.last_chequing_tx_date ?? null
      lastMastercardTxDate.value = cfg?.last_mastercard_tx_date ?? null

      if (selectedCompanyId.value) {
        await loadWaveAccounts(selectedCompanyId.value)
      }
    }
  },
  { immediate: true },
)

async function onCompanyChanged(newCompanyId: string | null) {
  chequingAccountId.value = null
  mastercardAccountId.value = null
  taxExpenseAccountId.value = null
  taxPayableAccountId.value = null

  if (newCompanyId) {
    await loadWaveAccounts(newCompanyId)
  }
}

async function handleSave() {
  saving.value = true
  try {
    const bankList = checklistStore.groupedWaveAccounts?.bank_and_cc_accounts || []
    const expList = checklistStore.groupedWaveAccounts?.expense_accounts || []
    const liabList = checklistStore.groupedWaveAccounts?.liability_accounts || []

    const chequingObj = bankList.find(a => a.id === chequingAccountId.value)
    const mcObj = bankList.find(a => a.id === mastercardAccountId.value)
    const taxExpObj = expList.find(a => a.id === taxExpenseAccountId.value)
    const taxPayObj = liabList.find(a => a.id === taxPayableAccountId.value)

    await checklistStore.updateConfig({
      company_id: selectedCompanyId.value,
      chequing_wave_account_id: chequingAccountId.value,
      chequing_wave_account_name: chequingObj?.name ?? null,
      mastercard_wave_account_id: mastercardAccountId.value,
      mastercard_wave_account_name: mcObj?.name ?? null,
      tax_expense_wave_account_id: taxExpenseAccountId.value,
      tax_expense_wave_account_name: taxExpObj?.name ?? null,
      tax_payable_wave_account_id: taxPayableAccountId.value,
      tax_payable_wave_account_name: taxPayObj?.name ?? null,
      wave_web_business_slug: waveWebBusinessSlug.value || "d2977f10-6793-4504-a139-f0d6872b2628",
      last_chequing_tx_date: lastChequingTxDate.value || null,
      last_mastercard_tx_date: lastMastercardTxDate.value || null,
    })

    $q.notify({
      type: "positive",
      message: "Checklist configuration saved successfully",
    })
    emit("saved")
    isOpen.value = false
  } catch (err) {
    const msg = err instanceof Error ? err.message : "Failed to save checklist configuration"
    $q.notify({
      type: "negative",
      message: msg,
    })
  } finally {
    saving.value = false
  }
}
</script>

<template>
  <q-dialog v-model="isOpen" persistent>
    <q-card style="min-width: 540px; max-width: 650px">
      <q-card-section class="row items-center q-pb-none">
        <div class="text-h6 text-weight-bold">Configure Checklist Accounts</div>
        <q-space />
        <q-btn icon="close" flat round dense v-close-popup />
      </q-card-section>

      <q-card-section class="q-pt-md">
        <q-form @submit.prevent="handleSave" class="q-gutter-y-md">
          <!-- Target Company -->
          <q-select
            v-model="selectedCompanyId"
            :options="companyOptions"
            emit-value
            map-options
            outlined
            dense
            label="Target Business Entity *"
            data-testid="select-target-company"
            @update:model-value="onCompanyChanged"
          />

          <div v-if="loadingAccounts" class="row items-center q-gutter-x-sm text-grey-7 q-py-xs">
            <q-spinner size="18px" color="primary" />
            <span>Loading accounts from Wave...</span>
          </div>

          <!-- Wave Chequing Account -->
          <q-select
            v-model="chequingAccountId"
            :options="bankAndCcOptions"
            emit-value
            map-options
            outlined
            dense
            clearable
            label="RBC Chequing Wave Account (Step 1)"
            data-testid="select-wave-chequing"
            :disable="!selectedCompanyId || loadingAccounts"
          />

          <!-- Wave Mastercard Account -->
          <q-select
            v-model="mastercardAccountId"
            :options="bankAndCcOptions"
            emit-value
            map-options
            outlined
            dense
            clearable
            label="RBC Mastercard Wave Account (Step 2)"
            data-testid="select-wave-mastercard"
            :disable="!selectedCompanyId || loadingAccounts"
          />

          <!-- Corporate Tax Expense Account -->
          <q-select
            v-model="taxExpenseAccountId"
            :options="expenseOptions"
            emit-value
            map-options
            outlined
            dense
            clearable
            label="Corporate Tax Expense Account (Step 8)"
            data-testid="select-tax-expense"
            :disable="!selectedCompanyId || loadingAccounts"
          />

          <!-- Taxes Payable Account -->
          <q-select
            v-model="taxPayableAccountId"
            :options="liabilityOptions"
            emit-value
            map-options
            outlined
            dense
            clearable
            label="Taxes Payable Liability Account (Step 8)"
            data-testid="select-tax-payable"
            :disable="!selectedCompanyId || loadingAccounts"
          />

          <!-- Wave Web Business Slug -->
          <q-input
            v-model="waveWebBusinessSlug"
            outlined
            dense
            label="Wave Web Business Slug (URL Deep-Links)"
            hint="Used to construct deep links to the Wave Cash Flow report"
            data-testid="input-wave-slug"
          />

          <q-separator class="q-my-sm" />
          <div class="text-subtitle2 text-grey-8">Manual Cutoff Date Overrides</div>

          <div class="row q-col-gutter-md">
            <div class="col-6">
              <q-input
                v-model="lastChequingTxDate"
                type="date"
                outlined
                dense
                stack-label
                label="Last Chequing Tx Date"
                data-testid="input-last-chequing-date"
              />
            </div>
            <div class="col-6">
              <q-input
                v-model="lastMastercardTxDate"
                type="date"
                outlined
                dense
                stack-label
                label="Last Mastercard Tx Date"
                data-testid="input-last-mastercard-date"
              />
            </div>
          </div>

          <q-card-actions align="right" class="q-px-none q-pt-md">
            <q-btn flat label="Cancel" color="grey-7" v-close-popup :disable="saving" />
            <q-btn unelevated label="Save Settings" color="primary" type="submit" :loading="saving" data-testid="btn-save-settings" />
          </q-card-actions>
        </q-form>
      </q-card-section>
    </q-card>
  </q-dialog>
</template>
