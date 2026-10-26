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
              outline
              color="primary"
              icon="settings"
              label="Configure Accounts"
              class="q-ml-md"
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
      <q-card flat bordered :class="{ 'bg-grey-1': store.isStepCompleted('import_chequing') }" data-testid="step-card-import_chequing">
        <q-card-section>
          <div class="row items-start justify-between">
            <div class="row items-center q-gutter-x-sm">
              <q-checkbox
                :model-value="store.isStepCompleted('import_chequing')"
                @update:model-value="val => store.toggleStep('import_chequing', val)"
                data-testid="checkbox-import_chequing"
              />
              <div>
                <div class="text-subtitle1 text-weight-bold">Step 1: Import Chequing Feed</div>
                <div class="text-caption text-grey-7">Pull RBC Chequing transactions into Wave.</div>
              </div>
            </div>

            <q-chip
              outline
              size="sm"
              color="primary"
              icon="event"
              :label="`Last Chequing Tx: ${store.config?.last_chequing_tx_date || 'Not yet synced'}`"
            />
          </div>

          <!-- Step 1 Action Panel -->
          <div class="q-mt-md q-ml-xl bg-white q-pa-sm rounded-borders border-grey">
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
          </div>
        </q-card-section>
      </q-card>

      <!-- Step 2: Import Mastercard Feed -->
      <q-card flat bordered :class="{ 'bg-grey-1': store.isStepCompleted('import_mastercard') }" data-testid="step-card-import_mastercard">
        <q-card-section>
          <div class="row items-start justify-between">
            <div class="row items-center q-gutter-x-sm">
              <q-checkbox
                :model-value="store.isStepCompleted('import_mastercard')"
                @update:model-value="val => store.toggleStep('import_mastercard', val)"
                data-testid="checkbox-import_mastercard"
              />
              <div>
                <div class="text-subtitle1 text-weight-bold">Step 2: Import Mastercard Feed</div>
                <div class="text-caption text-grey-7">Pull RBC Mastercard transactions into Wave.</div>
              </div>
            </div>

            <q-chip
              outline
              size="sm"
              color="primary"
              icon="event"
              :label="`Last Mastercard Tx: ${store.config?.last_mastercard_tx_date || 'Not yet synced'}`"
            />
          </div>

          <!-- Step 2 Action Panel -->
          <div class="q-mt-md q-ml-xl bg-white q-pa-sm rounded-borders border-grey">
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
          </div>
        </q-card-section>
      </q-card>

      <!-- Step 3: Allocate LOC Transfers -->
      <q-card
        flat
        bordered
        :class="{ 'bg-grey-1': store.isStepCompleted('allocate_loc_transfers') }"
        data-testid="step-card-allocate_loc_transfers"
      >
        <q-card-section>
          <div class="row items-center q-gutter-x-sm">
            <q-checkbox
              :model-value="store.isStepCompleted('allocate_loc_transfers')"
              @update:model-value="val => store.toggleStep('allocate_loc_transfers', val)"
              data-testid="checkbox-allocate_loc_transfers"
            />
            <div>
              <div class="text-subtitle1 text-weight-bold">Step 3: Allocate LOC Transfers</div>
              <div class="text-caption text-grey-7">
                Code Chequing transactions (<span class="text-weight-bold">LOAN PAYMENT</span> and
                <span class="text-weight-bold">LOAN CREDIT</span>) that moved to or from the LOC to establish the corresponding LOC ledger
                entries.
              </div>
            </div>
          </div>
        </q-card-section>
      </q-card>

      <!-- Step 4: Reconcile Bank Accounts -->
      <q-card
        flat
        bordered
        :class="{ 'bg-grey-1': store.isStepCompleted('reconcile_bank_accounts') }"
        data-testid="step-card-reconcile_bank_accounts"
      >
        <q-card-section>
          <div class="row items-center q-gutter-x-sm">
            <q-checkbox
              :model-value="store.isStepCompleted('reconcile_bank_accounts')"
              @update:model-value="val => store.toggleStep('reconcile_bank_accounts', val)"
              data-testid="checkbox-reconcile_bank_accounts"
            />
            <div>
              <div class="text-subtitle1 text-weight-bold">Step 4: Reconcile Bank Accounts</div>
              <div class="text-caption text-grey-7">
                Perform the official month-end reconciliation against the PDF bank statements and mark the imported transactions as
                reviewed.
              </div>
            </div>
          </div>
        </q-card-section>
      </q-card>

      <!-- Step 5: Sync External Data -->
      <q-card
        flat
        bordered
        :class="{ 'bg-grey-1': store.isStepCompleted('sync_external_data') }"
        data-testid="step-card-sync_external_data"
      >
        <q-card-section>
          <div class="row items-start justify-between">
            <div class="row items-center q-gutter-x-sm">
              <q-checkbox
                :model-value="store.isStepCompleted('sync_external_data')"
                @update:model-value="val => store.toggleStep('sync_external_data', val)"
                data-testid="checkbox-sync_external_data"
              />
              <div>
                <div class="text-subtitle1 text-weight-bold">Step 5: Sync External Data</div>
                <div class="text-caption text-grey-7">
                  Use the Amazon Order History Reporter extension to export transactions for the past 2 months (since Wrangler detects
                  duplicates and Amazon does weird things with transactions, going back further ensures nothing is missed), then import into
                  Wrangler and sync business allocations to Wave.
                </div>
              </div>
            </div>
          </div>

          <div class="q-mt-sm q-ml-xl row items-center q-gutter-sm">
            <q-btn
              outline
              size="sm"
              color="primary"
              icon="open_in_new"
              label="Open Amazon Order History"
              href="https://www.amazon.ca/gp/css/order-history?ref_=nav_orders_first"
              target="_blank"
            />
            <q-btn outline size="sm" color="primary" icon="cloud_upload" label="Go to Wrangler Import" to="/import" />
            <q-btn outline size="sm" color="primary" icon="sync" label="Go to Export Manager" to="/export-manager" />
          </div>
        </q-card-section>
      </q-card>

      <!-- Step 6: Scan Receipts -->
      <q-card flat bordered :class="{ 'bg-grey-1': store.isStepCompleted('scan_receipts') }" data-testid="step-card-scan_receipts">
        <q-card-section>
          <div class="row items-center q-gutter-x-sm">
            <q-checkbox
              :model-value="store.isStepCompleted('scan_receipts')"
              @update:model-value="val => store.toggleStep('scan_receipts', val)"
              data-testid="checkbox-scan_receipts"
            />
            <div>
              <div class="text-subtitle1 text-weight-bold">Step 6: Scan Receipts</div>
              <div class="text-caption text-grey-7">
                Scan physical receipts directly into Wave, which will generate new, unreviewed transactions in your ledger.
              </div>
            </div>
          </div>
        </q-card-section>
      </q-card>

      <!-- Step 7: Merge and Reimburse -->
      <q-card
        flat
        bordered
        :class="{ 'bg-grey-1': store.isStepCompleted('merge_and_reimburse') }"
        data-testid="step-card-merge_and_reimburse"
      >
        <q-card-section>
          <div class="row items-center q-gutter-x-sm">
            <q-checkbox
              :model-value="store.isStepCompleted('merge_and_reimburse')"
              @update:model-value="val => store.toggleStep('merge_and_reimburse', val)"
              data-testid="checkbox-merge_and_reimburse"
            />
            <div>
              <div class="text-subtitle1 text-weight-bold">Step 7: Merge and Reimburse</div>
              <div class="text-caption text-grey-7">
                Review the newly generated receipt transactions. Merge matches into the existing, reviewed bank transactions. For unmatched
                receipts, categorize the expense and assign the transaction to the Reimbursement account to log the personal card outlay.
              </div>
            </div>
          </div>
        </q-card-section>
      </q-card>

      <!-- Step 8: Calculate Net Cash & Accrue Corporate Tax -->
      <q-card
        flat
        bordered
        :class="{ 'bg-grey-1': store.isStepCompleted('calculate_net_cash_and_tax') }"
        data-testid="step-card-calculate_net_cash_and_tax"
      >
        <q-card-section>
          <div class="row items-start justify-between">
            <div class="row items-center q-gutter-x-sm">
              <q-checkbox
                :model-value="store.isStepCompleted('calculate_net_cash_and_tax')"
                @update:model-value="val => store.toggleStep('calculate_net_cash_and_tax', val)"
                data-testid="checkbox-calculate_net_cash_and_tax"
              />
              <div>
                <div class="text-subtitle1 text-weight-bold">Step 8: Calculate Net Cash & Accrue Corporate Tax</div>
                <div class="text-caption text-grey-7">
                  Run the Wave Cash Flow report for the completed month to determine your final Net Cash from Operating Activities, then
                  post a Journal Entry dated the last day of the month for the calculated Tax Reserve (Debit: Taxes - Corporate Tax; Credit:
                  Taxes Payable).
                </div>
              </div>
            </div>

            <q-btn
              outline
              size="sm"
              color="primary"
              icon="open_in_new"
              :label="`Open Wave Cash Flow Report (${store.selectedYearMonth})`"
              :href="store.currentMonth?.wave_cash_flow_url"
              target="_blank"
              data-testid="btn-wave-cash-flow"
            />
          </div>

          <!-- Step 8 Calculator & Sync Panel -->
          <div class="q-mt-md q-ml-xl bg-white q-pa-md rounded-borders border-grey">
            <div class="row items-center q-col-gutter-md">
              <div class="col-4">
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

              <div class="col-2">
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

              <div class="col-3">
                <div class="text-caption text-grey-7">Calculated Tax Reserve</div>
                <div class="text-subtitle1 text-weight-bold text-primary" data-testid="tax-reserve-amount">
                  ${{ store.currentMonth?.tax_reserve_amount || "0.00" }}
                </div>
              </div>

              <div class="col-3 row items-center justify-end q-gutter-x-sm">
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
          </div>
        </q-card-section>
      </q-card>

      <!-- Step 9: Calculate Safe Draw & Execute Dividends -->
      <q-card flat bordered :class="{ 'bg-grey-1': store.isStepCompleted('execute_dividends') }" data-testid="step-card-execute_dividends">
        <q-card-section>
          <div class="row items-start justify-between">
            <div class="row items-center q-gutter-x-sm">
              <q-checkbox
                :model-value="store.isStepCompleted('execute_dividends')"
                @update:model-value="val => store.toggleStep('execute_dividends', val)"
                data-testid="checkbox-execute_dividends"
              />
              <div>
                <div class="text-subtitle1 text-weight-bold">Step 9: Calculate Safe Draw & Execute Dividends</div>
                <div class="text-caption text-grey-7">
                  Calculate the Maximum Safe Draw (Soft Cap - Tax Liability - Actual LOC Balance), execute the physical cash transfer to
                  your personal account, and record it in Wave as a shareholder draw.
                </div>
              </div>
            </div>

            <q-btn
              outline
              size="sm"
              color="primary"
              icon="open_in_new"
              :label="`Open Wave Balance Sheet (${store.selectedYearMonth})`"
              :href="waveBalanceSheetUrl"
              target="_blank"
              data-testid="btn-wave-balance-sheet"
            />
          </div>

          <!-- Step 9 Calculator Panel -->
          <div class="q-mt-md q-ml-xl bg-white q-pa-md rounded-borders border-grey">
            <div class="row items-center q-col-gutter-md q-mb-md">
              <div class="col-3">
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
              <div class="col-3">
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
              <div class="col-3">
                <div class="text-caption text-grey-7">Current Soft Cap</div>
                <div class="text-subtitle1 text-weight-bold" data-testid="current-soft-cap">
                  ${{ store.currentMonth?.current_soft_cap || "0.00" }}
                </div>
              </div>
            </div>

            <div class="row items-center q-col-gutter-md">
              <div class="col-3">
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
              <div class="col-3">
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
              <div class="col-6">
                <q-banner
                  rounded
                  :class="Number(store.currentMonth?.maximum_safe_draw || 0) > 0 ? 'bg-green-1 text-green-9' : 'bg-red-1 text-red-9'"
                >
                  <div class="text-caption text-weight-medium">Maximum Safe Draw</div>
                  <div class="text-h6 text-weight-bolder" data-testid="maximum-safe-draw">
                    ${{ store.currentMonth?.maximum_safe_draw !== null ? store.currentMonth?.maximum_safe_draw : "—" }}
                  </div>
                </q-banner>
              </div>
            </div>
          </div>
        </q-card-section>
      </q-card>
    </div>

    <!-- Checklist Settings Dialog -->
    <ChecklistSettingsDialog v-model="showSettingsDialog" />
  </q-page>
</template>

<style scoped>
.border-grey {
  border: 1px solid #e0e0e0;
}
</style>
