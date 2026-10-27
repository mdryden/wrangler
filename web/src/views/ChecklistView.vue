<script setup lang="ts">
import { computed, onMounted, ref, watch } from "vue"
import { useQuasar } from "quasar"
import { useChecklistStore } from "../stores/checklist"
import ChecklistSettingsDialog from "../components/ChecklistSettingsDialog.vue"
import type { RbcCsvSyncResult } from "../types/checklist"

const $q = useQuasar()
const store = useChecklistStore()

const showSettingsDialog = ref<boolean>(false)

// File uploads
const chequingFile = ref<File | null>(null)
const mastercardFile = ref<File | null>(null)
const syncingType = ref<"chequing" | "mastercard" | null>(null)
const chequingSyncResult = ref<RbcCsvSyncResult | null>(null)
const mastercardSyncResult = ref<RbcCsvSyncResult | null>(null)

// Local form state for Step 8 and Step 9
const netCashInput = ref<string>("")
const taxRateInput = ref<string>("12.00")
const priorSoftCapInput = ref<string>("17600.00")
const locReductionInput = ref<string>("400.00")
const taxLiabilityInput = ref<string>("")
const actualLocBalanceInput = ref<string>("")

// Collapsible accordion state for all 9 steps
const stepKeys = [
  "import_chequing",
  "import_mastercard",
  "allocate_loc_transfers",
  "reconcile_bank_accounts",
  "sync_external_data",
  "scan_receipts",
  "merge_and_reimburse",
  "calculate_net_cash_and_tax",
  "execute_dividends",
] as const

type StepKey = (typeof stepKeys)[number]

const expandedSteps = ref<Record<StepKey, boolean>>({
  import_chequing: false,
  import_mastercard: false,
  allocate_loc_transfers: false,
  reconcile_bank_accounts: false,
  sync_external_data: false,
  scan_receipts: false,
  merge_and_reimburse: false,
  calculate_net_cash_and_tax: false,
  execute_dividends: false,
})

const allExpanded = computed(() => Object.values(expandedSteps.value).every(Boolean))

function toggleExpandAll() {
  const target = !allExpanded.value
  for (const k of stepKeys) {
    expandedSteps.value[k] = target
  }
}

function toggleStepExpansion(stepKey: StepKey) {
  expandedSteps.value[stepKey] = !expandedSteps.value[stepKey]
}

onMounted(async () => {
  await store.fetchConfig()
  await store.fetchMonth(store.selectedYearMonth)
})

watch(
  () => store.currentMonth,
  m => {
    if (m) {
      netCashInput.value = m.net_operating_cash !== null ? String(m.net_operating_cash) : ""
      taxRateInput.value = String(m.tax_rate ?? "12.00")
      priorSoftCapInput.value = String(m.prior_soft_cap ?? "17600.00")
      locReductionInput.value = String(m.monthly_loc_reduction ?? "400.00")
      taxLiabilityInput.value = m.tax_liability !== null ? String(m.tax_liability) : ""
      actualLocBalanceInput.value = m.actual_loc_balance !== null ? String(m.actual_loc_balance) : ""

      // Initially collapse all steps except the first non-completed item (if applicable)
      const completed = new Set(m.completed_steps || [])
      let firstIncompleteFound = false
      for (const k of stepKeys) {
        if (!completed.has(k) && !firstIncompleteFound) {
          expandedSteps.value[k] = true
          firstIncompleteFound = true
        } else {
          expandedSteps.value[k] = false
        }
      }
    }
  },
  { immediate: true },
)

const progressRatio = computed(() => store.completedStepsCount / 9)

const waveBalanceSheetUrl = computed(() => {
  const slug = store.config?.wave_web_business_slug || "d2977f10-6793-4504-a139-f0d6872b2628"
  const ym = store.selectedYearMonth
  const parts = ym.split("-")
  const year = parseInt(parts[0], 10)
  const month = parseInt(parts[1], 10)
  const lastDay = new Date(year, month, 0).getDate()
  return `https://next.waveapps.com/${slug}/reports/balance-sheet?end=${ym}-${String(lastDay).padStart(2, "0")}`
})

async function onMonthSelect(val: string | number | null) {
  if (typeof val === "string" && val && val !== store.selectedYearMonth) {
    chequingSyncResult.value = null
    mastercardSyncResult.value = null
    chequingFile.value = null
    mastercardFile.value = null
    await store.fetchMonth(val)
  }
}

async function onPrevMonth() {
  chequingSyncResult.value = null
  mastercardSyncResult.value = null
  chequingFile.value = null
  mastercardFile.value = null
  await store.navigateMonth(-1)
}

async function onNextMonth() {
  chequingSyncResult.value = null
  mastercardSyncResult.value = null
  chequingFile.value = null
  mastercardFile.value = null
  await store.navigateMonth(1)
}

async function saveStep8Fields() {
  if (!store.currentMonth) return
  const netCash = netCashInput.value.trim() !== "" ? netCashInput.value : null
  const rate = taxRateInput.value.trim() !== "" ? taxRateInput.value : "12.00"
  await store.updateMonth(store.selectedYearMonth, {
    net_operating_cash: netCash,
    tax_rate: rate,
  })
}

async function saveStep9Fields() {
  if (!store.currentMonth) return
  const priorCap = priorSoftCapInput.value.trim() !== "" ? priorSoftCapInput.value : "17600.00"
  const reduction = locReductionInput.value.trim() !== "" ? locReductionInput.value : "400.00"
  const taxLiab = taxLiabilityInput.value.trim() !== "" ? taxLiabilityInput.value : null
  const locBal = actualLocBalanceInput.value.trim() !== "" ? actualLocBalanceInput.value : null

  await store.updateMonth(store.selectedYearMonth, {
    prior_soft_cap: priorCap,
    monthly_loc_reduction: reduction,
    tax_liability: taxLiab,
    actual_loc_balance: locBal,
  })
}

async function handleSyncChequing() {
  if (!chequingFile.value) return
  syncingType.value = "chequing"
  try {
    const res = await store.syncRbcCsv(store.selectedYearMonth, "chequing", chequingFile.value)
    chequingSyncResult.value = res
    $q.notify({
      type: "positive",
      message: `Synced ${res.synced_count} chequing transactions directly to Wave`,
    })
  } catch (err) {
    const msg = err instanceof Error ? err.message : "Failed to sync chequing CSV"
    $q.notify({ type: "negative", message: msg })
  } finally {
    syncingType.value = null
  }
}

async function handleSyncMastercard() {
  if (!mastercardFile.value) return
  syncingType.value = "mastercard"
  try {
    const res = await store.syncRbcCsv(store.selectedYearMonth, "mastercard", mastercardFile.value)
    mastercardSyncResult.value = res
    $q.notify({
      type: "positive",
      message: `Synced ${res.synced_count} Mastercard transactions directly to Wave`,
    })
  } catch (err) {
    const msg = err instanceof Error ? err.message : "Failed to sync Mastercard CSV"
    $q.notify({ type: "negative", message: msg })
  } finally {
    syncingType.value = null
  }
}

async function handleSyncTaxAccrual() {
  try {
    await saveStep8Fields()
    await store.syncTaxAccrual(store.selectedYearMonth)
    $q.notify({
      type: "positive",
      message: "Corporate tax accrual journal entry successfully posted to Wave",
    })
  } catch (err) {
    const msg = err instanceof Error ? err.message : "Failed to sync tax accrual"
    $q.notify({ type: "negative", message: msg })
  }
}
</script>

<template>
  <q-page class="q-pa-lg" data-testid="checklist-view">
    <!-- Header Card -->
    <q-card flat bordered class="q-mb-md">
      <q-card-section>
        <div class="row items-center justify-between q-col-gutter-sm">
          <div>
            <div class="text-h5 text-weight-bold">Monthly Bookkeeping Checklist — Michelle Dryden LTD</div>
            <div class="text-caption text-grey-7">
              Repeatable end-to-end month-end workflow, RBC bank feed direct-to-Wave sync, corporate tax accrual, and safe draw calculator.
            </div>
          </div>

          <div class="row items-center q-gutter-x-sm">
            <q-btn flat round dense icon="chevron_left" @click="onPrevMonth" data-testid="month-selector-prev" />
            <q-input
              :model-value="store.selectedYearMonth"
              outlined
              dense
              mask="####-##"
              style="width: 130px"
              input-class="text-center text-weight-bold"
              @update:model-value="onMonthSelect"
              data-testid="month-selector-input"
            />
            <q-btn flat round dense icon="chevron_right" @click="onNextMonth" data-testid="month-selector-next" />

            <q-btn
              flat
              dense
              color="primary"
              :icon="allExpanded ? 'unfold_less' : 'unfold_more'"
              :label="allExpanded ? 'Collapse All' : 'Expand All'"
              class="q-ml-sm"
              @click="toggleExpandAll"
              data-testid="btn-toggle-expand-all"
            />

            <q-btn
              outline
              color="primary"
              icon="settings"
              label="Configure Accounts"
              class="q-ml-xs"
              @click="showSettingsDialog = true"
              data-testid="btn-configure-accounts"
            />
          </div>
        </div>

        <!-- Progress Bar -->
        <div class="q-mt-md">
          <div class="row items-center justify-between q-mb-xs">
            <span class="text-weight-medium text-caption text-grey-8">Monthly Completion Progress</span>
            <q-badge color="primary" :label="`${store.completedStepsCount} / 9 Completed`" />
          </div>
          <q-linear-progress :value="progressRatio" color="primary" rounded size="8px" />
        </div>
      </q-card-section>
    </q-card>

    <div v-if="store.isLoading" class="row justify-center q-my-xl">
      <q-spinner size="48px" color="primary" />
    </div>

    <!-- Steps Stack -->
    <div v-else class="q-gutter-y-md">
      <!-- Step 1: Import Chequing Feed -->
      <q-card flat bordered data-testid="step-card-import_chequing" class="overflow-hidden">
        <div
          class="q-pa-md cursor-pointer row items-center no-wrap justify-between step-header-hover select-none bg-grey-1"
          :class="{ 'bg-grey-2': store.isStepCompleted('import_chequing') }"
          @click="toggleStepExpansion('import_chequing')"
        >
          <div class="row items-center no-wrap q-gutter-x-sm col-grow">
            <div @click.stop>
              <q-checkbox
                :model-value="store.isStepCompleted('import_chequing')"
                @update:model-value="val => store.toggleStep('import_chequing', val)"
                data-testid="checkbox-import_chequing"
              />
            </div>
            <div class="text-subtitle1 text-weight-bold" :class="{ 'text-grey-7': store.isStepCompleted('import_chequing') }">
              Step 1: Import Chequing Feed
            </div>
          </div>

          <div class="col-auto">
            <q-btn
              flat
              round
              dense
              size="sm"
              color="grey-7"
              :icon="expandedSteps.import_chequing ? 'expand_less' : 'expand_more'"
              aria-label="Toggle step details"
            />
          </div>
        </div>

        <q-slide-transition>
          <div v-show="expandedSteps.import_chequing" class="bg-white">
            <q-separator />
            <q-card-section class="q-pt-md q-px-md q-pb-md">
              <div class="row items-center justify-between q-col-gutter-sm q-mb-md">
                <div class="text-caption text-grey-7 col">Pull RBC Chequing transactions into Wave.</div>
                <div class="col-auto">
                  <q-chip
                    outline
                    size="sm"
                    color="primary"
                    icon="event"
                    :label="`Last Chequing Tx: ${store.config?.last_chequing_tx_date || 'Not yet synced'}`"
                  />
                </div>
              </div>

              <div class="row items-center q-col-gutter-md">
                <div class="col-grow">
                  <q-file
                    v-model="chequingFile"
                    outlined
                    dense
                    label="Upload RBC Chequing CSV (shellco-chq.csv)"
                    accept=".csv"
                    data-testid="file-chequing"
                  >
                    <template #prepend>
                      <q-icon name="attach_file" />
                    </template>
                  </q-file>
                </div>
                <div class="col-auto">
                  <q-btn
                    unelevated
                    color="primary"
                    icon="cloud_upload"
                    label="Sync to Wave"
                    :disable="!chequingFile || !store.isChequingConfigured || store.isSyncingCsv"
                    :loading="store.isSyncingCsv && syncingType === 'chequing'"
                    @click="handleSyncChequing"
                    data-testid="btn-sync-chequing"
                  />
                </div>
              </div>

              <q-banner v-if="chequingSyncResult" dense rounded class="bg-green-1 text-green-9 q-mt-sm">
                Synced {{ chequingSyncResult.synced_count }} transactions directly to Wave ({{
                  chequingSyncResult.auto_categorized_count
                }}
                auto-categorized, {{ chequingSyncResult.uncategorized_count }} uncategorized).
              </q-banner>
            </q-card-section>
          </div>
        </q-slide-transition>
      </q-card>

      <!-- Step 2: Import Mastercard Feed -->
      <q-card flat bordered data-testid="step-card-import_mastercard" class="overflow-hidden">
        <div
          class="q-pa-md cursor-pointer row items-center no-wrap justify-between step-header-hover select-none bg-grey-1"
          :class="{ 'bg-grey-2': store.isStepCompleted('import_mastercard') }"
          @click="toggleStepExpansion('import_mastercard')"
        >
          <div class="row items-center no-wrap q-gutter-x-sm col-grow">
            <div @click.stop>
              <q-checkbox
                :model-value="store.isStepCompleted('import_mastercard')"
                @update:model-value="val => store.toggleStep('import_mastercard', val)"
                data-testid="checkbox-import_mastercard"
              />
            </div>
            <div class="text-subtitle1 text-weight-bold" :class="{ 'text-grey-7': store.isStepCompleted('import_mastercard') }">
              Step 2: Import Mastercard Feed
            </div>
          </div>

          <div class="col-auto">
            <q-btn
              flat
              round
              dense
              size="sm"
              color="grey-7"
              :icon="expandedSteps.import_mastercard ? 'expand_less' : 'expand_more'"
              aria-label="Toggle step details"
            />
          </div>
        </div>

        <q-slide-transition>
          <div v-show="expandedSteps.import_mastercard" class="bg-white">
            <q-separator />
            <q-card-section class="q-pt-md q-px-md q-pb-md">
              <div class="row items-center justify-between q-col-gutter-sm q-mb-md">
                <div class="text-caption text-grey-7 col">Pull RBC Mastercard transactions into Wave.</div>
                <div class="col-auto">
                  <q-chip
                    outline
                    size="sm"
                    color="primary"
                    icon="event"
                    :label="`Last Mastercard Tx: ${store.config?.last_mastercard_tx_date || 'Not yet synced'}`"
                  />
                </div>
              </div>

              <div class="row items-center q-col-gutter-md">
                <div class="col-grow">
                  <q-file
                    v-model="mastercardFile"
                    outlined
                    dense
                    label="Upload RBC Mastercard CSV (shellco-mc.csv)"
                    accept=".csv"
                    data-testid="file-mastercard"
                  >
                    <template #prepend>
                      <q-icon name="attach_file" />
                    </template>
                  </q-file>
                </div>
                <div class="col-auto">
                  <q-btn
                    unelevated
                    color="primary"
                    icon="cloud_upload"
                    label="Sync to Wave"
                    :disable="!mastercardFile || !store.isMastercardConfigured || store.isSyncingCsv"
                    :loading="store.isSyncingCsv && syncingType === 'mastercard'"
                    @click="handleSyncMastercard"
                    data-testid="btn-sync-mastercard"
                  />
                </div>
              </div>

              <q-banner v-if="mastercardSyncResult" dense rounded class="bg-green-1 text-green-9 q-mt-sm">
                Synced {{ mastercardSyncResult.synced_count }} transactions directly to Wave ({{
                  mastercardSyncResult.auto_categorized_count
                }}
                auto-categorized, {{ mastercardSyncResult.uncategorized_count }} uncategorized).
              </q-banner>
            </q-card-section>
          </div>
        </q-slide-transition>
      </q-card>

      <!-- Step 3: Allocate LOC Transfers -->
      <q-card flat bordered data-testid="step-card-allocate_loc_transfers" class="overflow-hidden">
        <div
          class="q-pa-md cursor-pointer row items-center no-wrap justify-between step-header-hover select-none bg-grey-1"
          :class="{ 'bg-grey-2': store.isStepCompleted('allocate_loc_transfers') }"
          @click="toggleStepExpansion('allocate_loc_transfers')"
        >
          <div class="row items-center no-wrap q-gutter-x-sm col-grow">
            <div @click.stop>
              <q-checkbox
                :model-value="store.isStepCompleted('allocate_loc_transfers')"
                @update:model-value="val => store.toggleStep('allocate_loc_transfers', val)"
                data-testid="checkbox-allocate_loc_transfers"
              />
            </div>
            <div class="text-subtitle1 text-weight-bold" :class="{ 'text-grey-7': store.isStepCompleted('allocate_loc_transfers') }">
              Step 3: Allocate LOC Transfers
            </div>
          </div>

          <div class="col-auto">
            <q-btn
              flat
              round
              dense
              size="sm"
              color="grey-7"
              :icon="expandedSteps.allocate_loc_transfers ? 'expand_less' : 'expand_more'"
              aria-label="Toggle step details"
            />
          </div>
        </div>

        <q-slide-transition>
          <div v-show="expandedSteps.allocate_loc_transfers" class="bg-white">
            <q-separator />
            <q-card-section class="q-pt-md q-px-md q-pb-md">
              <div class="text-caption text-grey-7">
                Code Chequing transactions (<span class="text-weight-bold">LOAN PAYMENT</span> and
                <span class="text-weight-bold">LOAN CREDIT</span>) that moved to or from the LOC to establish the corresponding LOC ledger
                entries.
              </div>
            </q-card-section>
          </div>
        </q-slide-transition>
      </q-card>

      <!-- Step 4: Reconcile Bank Accounts -->
      <q-card flat bordered data-testid="step-card-reconcile_bank_accounts" class="overflow-hidden">
        <div
          class="q-pa-md cursor-pointer row items-center no-wrap justify-between step-header-hover select-none bg-grey-1"
          :class="{ 'bg-grey-2': store.isStepCompleted('reconcile_bank_accounts') }"
          @click="toggleStepExpansion('reconcile_bank_accounts')"
        >
          <div class="row items-center no-wrap q-gutter-x-sm col-grow">
            <div @click.stop>
              <q-checkbox
                :model-value="store.isStepCompleted('reconcile_bank_accounts')"
                @update:model-value="val => store.toggleStep('reconcile_bank_accounts', val)"
                data-testid="checkbox-reconcile_bank_accounts"
              />
            </div>
            <div class="text-subtitle1 text-weight-bold" :class="{ 'text-grey-7': store.isStepCompleted('reconcile_bank_accounts') }">
              Step 4: Reconcile Bank Accounts
            </div>
          </div>

          <div class="col-auto">
            <q-btn
              flat
              round
              dense
              size="sm"
              color="grey-7"
              :icon="expandedSteps.reconcile_bank_accounts ? 'expand_less' : 'expand_more'"
              aria-label="Toggle step details"
            />
          </div>
        </div>

        <q-slide-transition>
          <div v-show="expandedSteps.reconcile_bank_accounts" class="bg-white">
            <q-separator />
            <q-card-section class="q-pt-md q-px-md q-pb-md">
              <div class="text-caption text-grey-7">
                Perform the official month-end reconciliation against the PDF bank statements and mark the imported transactions as
                reviewed.
              </div>
            </q-card-section>
          </div>
        </q-slide-transition>
      </q-card>

      <!-- Step 5: Sync External Data -->
      <q-card flat bordered data-testid="step-card-sync_external_data" class="overflow-hidden">
        <div
          class="q-pa-md cursor-pointer row items-center no-wrap justify-between step-header-hover select-none bg-grey-1"
          :class="{ 'bg-grey-2': store.isStepCompleted('sync_external_data') }"
          @click="toggleStepExpansion('sync_external_data')"
        >
          <div class="row items-center no-wrap q-gutter-x-sm col-grow">
            <div @click.stop>
              <q-checkbox
                :model-value="store.isStepCompleted('sync_external_data')"
                @update:model-value="val => store.toggleStep('sync_external_data', val)"
                data-testid="checkbox-sync_external_data"
              />
            </div>
            <div class="text-subtitle1 text-weight-bold" :class="{ 'text-grey-7': store.isStepCompleted('sync_external_data') }">
              Step 5: Sync External Data
            </div>
          </div>

          <div class="col-auto">
            <q-btn
              flat
              round
              dense
              size="sm"
              color="grey-7"
              :icon="expandedSteps.sync_external_data ? 'expand_less' : 'expand_more'"
              aria-label="Toggle step details"
            />
          </div>
        </div>

        <q-slide-transition>
          <div v-show="expandedSteps.sync_external_data" class="bg-white">
            <q-separator />
            <q-card-section class="q-pt-md q-px-md q-pb-md">
              <div class="text-caption text-grey-7">
                Use the Amazon Order History Reporter extension to export transactions for the past 2 months (since Wrangler detects
                duplicates and Amazon does weird things with transactions, going back further ensures nothing is missed), then import into
                Wrangler and sync business allocations to Wave.
              </div>

              <div class="row items-center q-gutter-sm q-mt-sm">
                <q-btn
                  outline
                  size="sm"
                  color="primary"
                  icon="open_in_new"
                  label="Open Amazon Order History"
                  href="https://www.amazon.ca/gp/css/order-history?ref_=nav_orders_first"
                  target="_blank"
                />
                <q-btn outline size="sm" color="primary" icon="cloud_upload" label="Go to Wrangler Import" href="/import" target="_blank" />
                <q-btn outline size="sm" color="primary" icon="sync" label="Go to Export Manager" href="/export-manager" target="_blank" />
              </div>
            </q-card-section>
          </div>
        </q-slide-transition>
      </q-card>

      <!-- Step 6: Scan Receipts -->
      <q-card flat bordered data-testid="step-card-scan_receipts" class="overflow-hidden">
        <div
          class="q-pa-md cursor-pointer row items-center no-wrap justify-between step-header-hover select-none bg-grey-1"
          :class="{ 'bg-grey-2': store.isStepCompleted('scan_receipts') }"
          @click="toggleStepExpansion('scan_receipts')"
        >
          <div class="row items-center no-wrap q-gutter-x-sm col-grow">
            <div @click.stop>
              <q-checkbox
                :model-value="store.isStepCompleted('scan_receipts')"
                @update:model-value="val => store.toggleStep('scan_receipts', val)"
                data-testid="checkbox-scan_receipts"
              />
            </div>
            <div class="text-subtitle1 text-weight-bold" :class="{ 'text-grey-7': store.isStepCompleted('scan_receipts') }">
              Step 6: Scan Receipts
            </div>
          </div>

          <div class="col-auto">
            <q-btn
              flat
              round
              dense
              size="sm"
              color="grey-7"
              :icon="expandedSteps.scan_receipts ? 'expand_less' : 'expand_more'"
              aria-label="Toggle step details"
            />
          </div>
        </div>

        <q-slide-transition>
          <div v-show="expandedSteps.scan_receipts" class="bg-white">
            <q-separator />
            <q-card-section class="q-pt-md q-px-md q-pb-md">
              <div class="text-caption text-grey-7">
                Scan physical receipts directly into Wave, which will generate new, unreviewed transactions in your ledger.
              </div>
            </q-card-section>
          </div>
        </q-slide-transition>
      </q-card>

      <!-- Step 7: Merge and Reimburse -->
      <q-card flat bordered data-testid="step-card-merge_and_reimburse" class="overflow-hidden">
        <div
          class="q-pa-md cursor-pointer row items-center no-wrap justify-between step-header-hover select-none bg-grey-1"
          :class="{ 'bg-grey-2': store.isStepCompleted('merge_and_reimburse') }"
          @click="toggleStepExpansion('merge_and_reimburse')"
        >
          <div class="row items-center no-wrap q-gutter-x-sm col-grow">
            <div @click.stop>
              <q-checkbox
                :model-value="store.isStepCompleted('merge_and_reimburse')"
                @update:model-value="val => store.toggleStep('merge_and_reimburse', val)"
                data-testid="checkbox-merge_and_reimburse"
              />
            </div>
            <div class="text-subtitle1 text-weight-bold" :class="{ 'text-grey-7': store.isStepCompleted('merge_and_reimburse') }">
              Step 7: Merge and Reimburse
            </div>
          </div>

          <div class="col-auto">
            <q-btn
              flat
              round
              dense
              size="sm"
              color="grey-7"
              :icon="expandedSteps.merge_and_reimburse ? 'expand_less' : 'expand_more'"
              aria-label="Toggle step details"
            />
          </div>
        </div>

        <q-slide-transition>
          <div v-show="expandedSteps.merge_and_reimburse" class="bg-white">
            <q-separator />
            <q-card-section class="q-pt-md q-px-md q-pb-md">
              <div class="text-caption text-grey-7">
                Review the newly generated receipt transactions. Merge matches into the existing, reviewed bank transactions. For unmatched
                receipts, categorize the expense and assign the transaction to the Reimbursement account to log the personal card outlay.
              </div>
            </q-card-section>
          </div>
        </q-slide-transition>
      </q-card>

      <!-- Step 8: Calculate Net Cash & Accrue Corporate Tax -->
      <q-card flat bordered data-testid="step-card-calculate_net_cash_and_tax" class="overflow-hidden">
        <div
          class="q-pa-md cursor-pointer row items-center no-wrap justify-between step-header-hover select-none bg-grey-1"
          :class="{ 'bg-grey-2': store.isStepCompleted('calculate_net_cash_and_tax') }"
          @click="toggleStepExpansion('calculate_net_cash_and_tax')"
        >
          <div class="row items-center no-wrap q-gutter-x-sm col-grow">
            <div @click.stop>
              <q-checkbox
                :model-value="store.isStepCompleted('calculate_net_cash_and_tax')"
                @update:model-value="val => store.toggleStep('calculate_net_cash_and_tax', val)"
                data-testid="checkbox-calculate_net_cash_and_tax"
              />
            </div>
            <div class="text-subtitle1 text-weight-bold" :class="{ 'text-grey-7': store.isStepCompleted('calculate_net_cash_and_tax') }">
              Step 8: Calculate Net Cash & Accrue Corporate Tax
            </div>
          </div>

          <div class="col-auto">
            <q-btn
              flat
              round
              dense
              size="sm"
              color="grey-7"
              :icon="expandedSteps.calculate_net_cash_and_tax ? 'expand_less' : 'expand_more'"
              aria-label="Toggle step details"
            />
          </div>
        </div>

        <q-slide-transition>
          <div v-show="expandedSteps.calculate_net_cash_and_tax" class="bg-white">
            <q-separator />
            <q-card-section class="q-pt-md q-px-md q-pb-md">
              <div class="row items-center justify-between q-col-gutter-sm q-mb-md">
                <div class="text-caption text-grey-7 col">
                  Run the Wave Cash Flow report for the completed month to determine your final Net Cash from Operating Activities, then
                  post a Journal Entry dated the last day of the month for the calculated Tax Reserve (Debit: Taxes - Corporate Tax; Credit:
                  Taxes Payable).
                </div>
                <div class="col-auto">
                  <q-btn
                    outline
                    size="sm"
                    color="primary"
                    icon="open_in_new"
                    :label="`Wave Cash Flow (${store.selectedYearMonth})`"
                    :href="store.currentMonth?.wave_cash_flow_url"
                    target="_blank"
                    data-testid="btn-wave-cash-flow"
                  />
                </div>
              </div>

              <!-- Calculator inputs row directly on white card surface -->
              <div class="row items-center q-col-gutter-md">
                <div class="col-12 col-sm-4">
                  <q-input
                    v-model="netCashInput"
                    outlined
                    dense
                    prefix="$"
                    label="Net Cash from Operations"
                    data-testid="input-net-operating-cash"
                    @blur="saveStep8Fields"
                  />
                </div>

                <div class="col-12 col-sm-2">
                  <q-input
                    v-model="taxRateInput"
                    outlined
                    dense
                    suffix="%"
                    label="Tax Rate"
                    data-testid="input-tax-rate"
                    @blur="saveStep8Fields"
                  />
                </div>

                <div class="col-12 col-sm-3">
                  <div class="text-caption text-grey-7">Calculated Tax Reserve</div>
                  <div class="text-subtitle1 text-weight-bolder text-primary" data-testid="tax-reserve-amount">
                    ${{ store.currentMonth?.tax_reserve_amount || "0.00" }}
                  </div>
                </div>

                <div class="col-12 col-sm-3 row items-center justify-end q-gutter-x-sm">
                  <q-badge v-if="store.currentMonth?.tax_accrual_wave_tx_id" color="positive" label="Synced to Wave" />
                  <q-btn
                    unelevated
                    color="primary"
                    label="Sync Tax Accrual"
                    :disable="!store.canSyncTaxAccrual || Boolean(store.currentMonth?.tax_accrual_wave_tx_id) || store.isSyncingTax"
                    :loading="store.isSyncingTax"
                    @click="handleSyncTaxAccrual"
                    data-testid="btn-sync-tax-accrual"
                  />
                </div>
              </div>
            </q-card-section>
          </div>
        </q-slide-transition>
      </q-card>

      <!-- Step 9: Calculate Safe Draw & Execute Dividends -->
      <q-card flat bordered data-testid="step-card-execute_dividends" class="overflow-hidden">
        <div
          class="q-pa-md cursor-pointer row items-center no-wrap justify-between step-header-hover select-none bg-grey-1"
          :class="{ 'bg-grey-2': store.isStepCompleted('execute_dividends') }"
          @click="toggleStepExpansion('execute_dividends')"
        >
          <div class="row items-center no-wrap q-gutter-x-sm col-grow">
            <div @click.stop>
              <q-checkbox
                :model-value="store.isStepCompleted('execute_dividends')"
                @update:model-value="val => store.toggleStep('execute_dividends', val)"
                data-testid="checkbox-execute_dividends"
              />
            </div>
            <div class="text-subtitle1 text-weight-bold" :class="{ 'text-grey-7': store.isStepCompleted('execute_dividends') }">
              Step 9: Calculate Safe Draw & Execute Dividends
            </div>
          </div>

          <div class="col-auto">
            <q-btn
              flat
              round
              dense
              size="sm"
              color="grey-7"
              :icon="expandedSteps.execute_dividends ? 'expand_less' : 'expand_more'"
              aria-label="Toggle step details"
            />
          </div>
        </div>

        <q-slide-transition>
          <div v-show="expandedSteps.execute_dividends" class="bg-white">
            <q-separator />
            <q-card-section class="q-pt-md q-px-md q-pb-md">
              <div class="row items-center justify-between q-col-gutter-sm q-mb-md">
                <div class="text-caption text-grey-7 col">
                  Calculate the Maximum Safe Draw (Soft Cap - Tax Liability - Actual LOC Balance), execute the physical cash transfer to
                  your personal account, and record it in Wave as a shareholder draw.
                </div>
                <div class="col-auto">
                  <q-btn
                    outline
                    size="sm"
                    color="primary"
                    icon="open_in_new"
                    :label="`Wave Balance Sheet (${store.selectedYearMonth})`"
                    :href="waveBalanceSheetUrl"
                    target="_blank"
                    data-testid="btn-wave-balance-sheet"
                  />
                </div>
              </div>

              <!-- Calculator inputs & KPI display directly on white card surface -->
              <div class="row q-col-gutter-lg items-center">
                <div class="col-12 col-md-8">
                  <div class="row q-col-gutter-md q-mb-sm items-center">
                    <div class="col-12 col-sm-4">
                      <q-input
                        v-model="priorSoftCapInput"
                        outlined
                        dense
                        prefix="$"
                        label="Prior Soft Cap"
                        data-testid="input-prior-soft-cap"
                        @blur="saveStep9Fields"
                      />
                    </div>
                    <div class="col-12 col-sm-4">
                      <q-input
                        v-model="locReductionInput"
                        outlined
                        dense
                        prefix="$"
                        label="Monthly LOC Reduction"
                        data-testid="input-monthly-loc-reduction"
                        @blur="saveStep9Fields"
                      />
                    </div>
                    <div class="col-12 col-sm-4">
                      <div class="text-caption text-grey-7">Current Soft Cap</div>
                      <div class="text-subtitle1 text-weight-bold" data-testid="current-soft-cap">
                        ${{ store.currentMonth?.current_soft_cap || "0.00" }}
                      </div>
                    </div>
                  </div>

                  <div class="row q-col-gutter-md items-center">
                    <div class="col-12 col-sm-6">
                      <q-input
                        v-model="taxLiabilityInput"
                        outlined
                        dense
                        prefix="$"
                        label="Tax Liability (from Balance Sheet)"
                        data-testid="input-tax-liability"
                        @blur="saveStep9Fields"
                      />
                    </div>
                    <div class="col-12 col-sm-6">
                      <q-input
                        v-model="actualLocBalanceInput"
                        outlined
                        dense
                        prefix="$"
                        label="Actual LOC Balance"
                        data-testid="input-actual-loc-balance"
                        @blur="saveStep9Fields"
                      />
                    </div>
                  </div>
                </div>

                <div class="col-12 col-md-4">
                  <div
                    class="q-pa-md rounded-borders"
                    :class="Number(store.currentMonth?.maximum_safe_draw || 0) > 0 ? 'bg-green-1 text-green-10' : 'bg-red-1 text-red-9'"
                  >
                    <div class="row items-center q-gutter-x-xs q-mb-xs">
                      <q-icon
                        name="account_balance_wallet"
                        size="18px"
                        :color="Number(store.currentMonth?.maximum_safe_draw || 0) > 0 ? 'green-8' : 'red-8'"
                      />
                      <span class="text-caption text-weight-bold">Maximum Safe Draw</span>
                    </div>
                    <div class="text-h5 text-weight-bolder" data-testid="maximum-safe-draw">
                      ${{ store.currentMonth?.maximum_safe_draw !== null ? store.currentMonth?.maximum_safe_draw : "—" }}
                    </div>
                  </div>
                </div>
              </div>
            </q-card-section>
          </div>
        </q-slide-transition>
      </q-card>
    </div>

    <!-- Checklist Settings Dialog -->
    <ChecklistSettingsDialog v-model="showSettingsDialog" />
  </q-page>
</template>

<style scoped>
.step-header-hover:hover {
  background-color: #f0f0f0;
}
</style>
