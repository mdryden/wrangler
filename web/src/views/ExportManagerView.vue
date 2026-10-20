<script setup lang="ts">
import { computed, onMounted, ref, watch } from "vue"
import { Notify, useQuasar, type QTableColumn } from "quasar"
import { useCompanyStore } from "../stores/companies"
import { useTransactionStore } from "../stores/transactions"
import type { Company } from "../types/company"
import type { WaveCategory, WaveSyncResponse } from "../types/wave"
import {
  buildCompanyExportOptions,
  canExportCompany,
  canSyncRowToWave,
  createInitialExportControlsState,
  DEFAULT_EXPORT_PAGE_SIZE,
  extractCompanyAllocationRows,
  formatCurrency,
  getCompanyExportSummary,
  getLedgerTransactionUrl,
  isWaveAlreadySynced,
  openTransactionInLedgerNewTab,
  resetExportControlsState,
  type ExportAllocationRow,
} from "./exportManager"

const $q = useQuasar()
const companyStore = useCompanyStore()
const transactionStore = useTransactionStore()

const controls = ref(createInitialExportControlsState())
const exporting = ref<boolean>(false)
const syncingToWave = ref<boolean>(false)
const syncingCategories = ref<boolean>(false)

const cachedCategories = ref<WaveCategory[]>([])
const selectedRows = ref<ExportAllocationRow[]>([])

// Sync result dialog
const showSyncSummary = ref<boolean>(false)
const syncSummaryData = ref<WaveSyncResponse | null>(null)

const pagination = ref({
  sortBy: "date",
  descending: false,
  page: 1,
  rowsPerPage: DEFAULT_EXPORT_PAGE_SIZE,
  rowsNumber: 0,
})

function notifySuccess(message: string): void {
  try {
    if ($q?.notify) {
      $q.notify({ type: "positive", message, position: "top", timeout: 2500 })
      return
    }
  } catch {
    // fallback
  }
  Notify.create({ type: "positive", message, position: "top", timeout: 2500 })
}

function notifyError(message: string): void {
  try {
    if ($q?.notify) {
      $q.notify({ type: "negative", message, position: "top", timeout: 4000 })
      return
    }
  } catch {
    // fallback
  }
  Notify.create({ type: "negative", message, position: "top", timeout: 4000 })
}

const companyOptions = computed(() =>
  companyStore.companies.map(c => ({
    label: c.name,
    value: c.id,
  })),
)

const selectedCompany = computed<Company | null>(() => companyStore.companies.find(c => c.id === controls.value.company_id) ?? null)

const isWaveMode = computed<boolean>(() => Boolean(selectedCompany.value?.is_wave_connected))

const selectedCompanySummary = computed(() => (selectedCompany.value ? getCompanyExportSummary(selectedCompany.value) : null))

const allocationRows = computed<ExportAllocationRow[]>(() => {
  if (!controls.value.company_id) {
    return []
  }
  return extractCompanyAllocationRows(transactionStore.transactions, controls.value.company_id, controls.value.include_locked)
})

const previewTotalAmountFormatted = computed(() => {
  const total = allocationRows.value.reduce((acc, row) => {
    const num = typeof row.amount === "string" ? parseFloat(row.amount) : row.amount
    return acc + (Number.isNaN(num) ? 0 : num)
  }, 0)
  return formatCurrency(total)
})

const categoryOptions = computed(() =>
  cachedCategories.value.map(cat => ({
    label: cat.name,
    value: cat.id,
    is_uncategorized: cat.is_uncategorized,
  })),
)

// Select all toggle logic
const eligibleRows = computed(() => allocationRows.value.filter(r => !r.is_locked && !isWaveAlreadySynced(r)))

const isAllSelected = computed(() => eligibleRows.value.length > 0 && selectedRows.value.length === eligibleRows.value.length)

function toggleSelectAll(): void {
  if (isAllSelected.value) {
    selectedRows.value = []
  } else {
    selectedRows.value = [...eligibleRows.value]
  }
}

function isRowSelected(row: ExportAllocationRow): boolean {
  return selectedRows.value.some(r => r.id === row.id)
}

function toggleRowSelect(row: ExportAllocationRow): void {
  const idx = selectedRows.value.findIndex(r => r.id === row.id)
  if (idx !== -1) {
    selectedRows.value.splice(idx, 1)
  } else {
    selectedRows.value.push(row)
  }
}

const canSyncSelectedToWave = computed(() => {
  if (!isWaveMode.value || selectedRows.value.length === 0) return false
  return selectedRows.value.every(r => r.wave_category_id)
})

const selectedRowsTotalFormatted = computed(() => {
  const sum = selectedRows.value.reduce((acc, r) => {
    const val = typeof r.amount === "string" ? parseFloat(r.amount) : r.amount
    return acc + (Number.isNaN(val) ? 0 : val)
  }, 0)
  return formatCurrency(sum)
})

const columns = computed<QTableColumn[]>(() => {
  const cols: QTableColumn[] = []

  if (isWaveMode.value) {
    cols.push({
      name: "selection",
      required: true,
      label: "",
      align: "center",
      field: () => "",
      sortable: false,
    })
  }

  cols.push(
    {
      name: "date",
      required: true,
      label: "Date",
      align: "left",
      field: (row: ExportAllocationRow) => row.date,
      sortable: true,
    },
    {
      name: "description",
      required: true,
      label: "Description",
      align: "left",
      field: (row: ExportAllocationRow) => row.description,
      sortable: true,
    },
    {
      name: "amount",
      required: true,
      label: "Amount",
      align: "right",
      field: (row: ExportAllocationRow) => Number(row.amount),
      sortable: true,
    },
  )

  if (isWaveMode.value) {
    cols.push({
      name: "category",
      required: true,
      label: "Category",
      align: "left",
      field: (row: ExportAllocationRow) => row.wave_category_id ?? "",
      sortable: false,
    })
  }

  cols.push(
    {
      name: "is_locked",
      label: "Status",
      align: "center",
      field: (row: ExportAllocationRow) => (row.is_locked ? "Locked" : "Unlocked"),
      sortable: false,
    },
    {
      name: "receipt",
      label: "Receipt",
      align: "center",
      field: (row: ExportAllocationRow) => (row.receipt_file_path ? "Yes" : "No"),
      sortable: false,
    },
    {
      name: "ledger",
      label: "Parent Transaction",
      align: "right",
      field: (row: ExportAllocationRow) => row.transaction_id,
      sortable: false,
    },
  )

  return cols
})

// Load categories on company selection if Wave connected
watch(
  () => controls.value.company_id,
  async newCompId => {
    selectedRows.value = []
    cachedCategories.value = []
    if (newCompId && selectedCompany.value?.is_wave_connected) {
      try {
        cachedCategories.value = await companyStore.fetchWaveCategories(newCompId)
      } catch {
        // Handled silently
      }
    }
  },
)

async function onQuickSyncCategories(): Promise<void> {
  const compId = controls.value.company_id
  if (!compId) return
  syncingCategories.value = true
  try {
    const refreshed = await companyStore.syncWaveCategories(compId)
    cachedCategories.value = refreshed
    notifySuccess(`Refreshed ${refreshed.length} categories from Wave`)
  } catch (err) {
    notifyError(err instanceof Error ? err.message : "Failed to sync categories")
  } finally {
    syncingCategories.value = false
  }
}

async function onCategoryChange(row: ExportAllocationRow, newCategoryId: string | null): Promise<void> {
  try {
    await transactionStore.updateAllocationCategory(row.id, newCategoryId)
    row.wave_category_id = newCategoryId
    notifySuccess("Category updated")
  } catch (err) {
    notifyError(err instanceof Error ? err.message : "Failed to update category")
  }
}

async function loadCompanies(): Promise<void> {
  try {
    await companyStore.fetchCompanies()
  } catch {
    // Error displayed in banner
  }
}

async function onRequest(props: {
  pagination: {
    sortBy?: string | null
    descending?: boolean
    page: number
    rowsPerPage: number
    rowsNumber?: number
  }
}): Promise<void> {
  if (!controls.value.company_id) {
    transactionStore.transactions = []
    pagination.value.page = 1
    pagination.value.rowsNumber = 0
    return
  }

  const { page, rowsPerPage, sortBy, descending } = props.pagination
  try {
    await transactionStore.fetchTransactions({
      page,
      rowsPerPage,
      sortBy: sortBy || "date",
      descending: descending ?? false,
      company_id: controls.value.company_id,
      include_locked: controls.value.include_locked,
      start_date: controls.value.start_date.trim() || undefined,
      end_date: controls.value.end_date.trim() || undefined,
    })

    pagination.value.page = transactionStore.page
    pagination.value.rowsPerPage = transactionStore.pageSize
    pagination.value.rowsNumber = transactionStore.total
    pagination.value.sortBy = sortBy ?? "date"
    pagination.value.descending = descending ?? false
  } catch {
    // Handled in store error banner
  }
}

function applyFilters(): void {
  pagination.value.page = 1
  selectedRows.value = []
  onRequest({ pagination: pagination.value })
}

function resetControls(): void {
  resetExportControlsState(controls.value)
  transactionStore.transactions = []
  selectedRows.value = []
  cachedCategories.value = []
  pagination.value.page = 1
  pagination.value.rowsPerPage = DEFAULT_EXPORT_PAGE_SIZE
  pagination.value.rowsNumber = 0
}

function refresh(): void {
  loadCompanies()
  if (controls.value.company_id) {
    onRequest({ pagination: pagination.value })
  }
}

async function onExportCsv(): Promise<void> {
  const companyId = controls.value.company_id
  if (!companyId) return

  exporting.value = true
  try {
    const companyName = selectedCompany.value?.name ?? "Company"
    const options = buildCompanyExportOptions(controls.value)
    await companyStore.exportTransactionsCsv(companyId, options)
    notifySuccess(`Exported CSV for "${companyName}"`)
    await onRequest({ pagination: pagination.value })
  } catch (err) {
    const msg = err instanceof Error ? err.message : "Failed to export CSV"
    notifyError(msg)
  } finally {
    exporting.value = false
  }
}

function onSyncToWave(): void {
  const comp = selectedCompany.value
  if (!comp || selectedRows.value.length === 0) return

  $q.dialog({
    title: "Sync to Wave",
    message: `Push ${selectedRows.value.length} transactions totaling ${selectedRowsTotalFormatted.value} to Wave?`,
    cancel: true,
    persistent: true,
    ok: {
      label: "Sync",
      color: "primary",
      unelevated: true,
    },
  }).onOk(async () => {
    syncingToWave.value = true
    try {
      const allocationIds = selectedRows.value.map(r => r.id)
      const result = await companyStore.syncCompanyToWave(comp.id, allocationIds)
      syncSummaryData.value = result
      showSyncSummary.value = true
      selectedRows.value = []
      await companyStore.fetchCompanies()
      await onRequest({ pagination: pagination.value })
    } catch (err) {
      notifyError(err instanceof Error ? err.message : "Wave synchronization failed")
    } finally {
      syncingToWave.value = false
    }
  })
}

async function openReceipt(receiptPath: string | null): Promise<void> {
  if (!receiptPath) return
  try {
    await transactionStore.openReceiptInNewTab(receiptPath)
  } catch (err) {
    const msg = err instanceof Error ? err.message : "Failed to open receipt"
    notifyError(msg)
  }
}

onMounted(() => {
  transactionStore.transactions = []
  loadCompanies()
})

defineExpose({
  controls,
  pagination,
  columns,
  exporting,
  syncingToWave,
  selectedCompany,
  selectedCompanySummary,
  allocationRows,
  selectedRows,
  cachedCategories,
  previewTotalAmountFormatted,
  isWaveMode,
  loadCompanies,
  onRequest,
  applyFilters,
  resetControls,
  refresh,
  onExportCsv,
  onSyncToWave,
  onCategoryChange,
  onQuickSyncCategories,
  openReceipt,
  getLedgerTransactionUrl,
  openTransactionInLedgerNewTab,
  canExportCompany,
  getCompanyExportSummary,
  formatCurrency,
  isWaveAlreadySynced,
  canSyncRowToWave,
})
</script>

<template>
  <q-page class="q-pa-md">
    <!-- Page Header -->
    <div class="row items-center justify-between q-mb-md">
      <div>
        <div class="text-h5 text-weight-bold text-grey-9">Export & Sync Manager</div>
        <div class="text-caption text-grey-7">
          Select a company to review business allocations and sync directly to Wave or export a CSV.
        </div>
      </div>
      <div class="row items-center q-gutter-sm">
        <q-btn
          flat
          dense
          round
          icon="refresh"
          color="grey-7"
          aria-label="Refresh Export Manager"
          data-testid="btn-refresh-exports"
          :loading="companyStore.loading || transactionStore.loading"
          @click="refresh"
        >
          <q-tooltip>Refresh export data</q-tooltip>
        </q-btn>
      </div>
    </div>

    <!-- Error Banner -->
    <q-banner v-if="companyStore.error || transactionStore.error" rounded dense inline-actions class="bg-negative text-white q-mb-md">
      <template #avatar>
        <q-icon name="error" color="white" />
      </template>
      {{ companyStore.error || transactionStore.error }}
      <template #action>
        <q-btn flat label="Retry" color="white" @click="refresh" />
      </template>
    </q-banner>

    <!-- Filter Bar -->
    <q-card flat bordered class="q-mb-md bg-grey-1">
      <q-card-section class="q-py-sm">
        <div class="row q-col-gutter-sm items-center">
          <!-- Company Dropdown -->
          <div class="col-12 col-sm-6 col-md-3">
            <q-select
              v-model="controls.company_id"
              dense
              outlined
              clearable
              emit-value
              map-options
              bg-color="white"
              label="Company"
              placeholder="Select a company..."
              :options="companyOptions"
              data-testid="export-filter-company"
              @update:model-value="applyFilters"
            >
              <template #prepend>
                <q-icon name="business" />
              </template>
              <template v-if="isWaveMode" #after>
                <q-btn
                  flat
                  round
                  dense
                  icon="sync"
                  color="primary"
                  :loading="syncingCategories"
                  data-testid="btn-quick-sync-categories"
                  @click.stop="onQuickSyncCategories"
                >
                  <q-tooltip>Refresh Wave categories</q-tooltip>
                </q-btn>
              </template>
            </q-select>
          </div>

          <!-- Start Date Filter -->
          <div class="col-12 col-sm-6 col-md-2">
            <q-input
              v-model="controls.start_date"
              type="date"
              dense
              outlined
              clearable
              stack-label
              bg-color="white"
              label="Start Date"
              data-testid="export-start-date"
              @update:model-value="applyFilters"
              @keyup.enter="applyFilters"
            />
          </div>

          <!-- End Date Filter -->
          <div class="col-12 col-sm-6 col-md-2">
            <q-input
              v-model="controls.end_date"
              type="date"
              dense
              outlined
              clearable
              stack-label
              bg-color="white"
              label="End Date"
              data-testid="export-end-date"
              @update:model-value="applyFilters"
              @keyup.enter="applyFilters"
            />
          </div>

          <!-- Include Locked Transactions Toggle -->
          <div class="col-12 col-sm-6 col-md-3">
            <q-toggle
              v-model="controls.include_locked"
              color="primary"
              label="Include locked transactions"
              data-testid="toggle-include-locked"
              @update:model-value="applyFilters"
            />
          </div>

          <!-- Filter / Reset Buttons -->
          <div class="col-12 col-md-2 row items-center justify-end q-gutter-xs">
            <q-btn
              color="primary"
              unelevated
              icon="filter_list"
              label="Filter"
              data-testid="btn-apply-export-filters"
              @click="applyFilters"
            />
            <q-btn flat color="grey-7" icon="clear" label="Reset" data-testid="btn-reset-export-controls" @click="resetControls" />
          </div>
        </div>
      </q-card-section>
    </q-card>

    <!-- Action Bar -->
    <q-card flat bordered class="q-mb-md bg-white" data-testid="export-action-bar">
      <q-card-section class="q-py-sm row items-center justify-between q-col-gutter-sm">
        <div class="row items-center q-gutter-md">
          <template v-if="selectedCompany && selectedCompanySummary">
            <div class="row items-center no-wrap">
              <q-avatar size="28px" color="blue-1" text-color="primary" icon="business" class="q-mr-sm" />
              <span class="text-subtitle1 text-weight-bold" data-testid="selected-company-name">
                {{ selectedCompany.name }}
              </span>
            </div>
            <q-badge
              :color="isWaveMode ? 'green-1' : 'green-1'"
              :text-color="isWaveMode ? 'positive' : 'positive'"
              class="q-px-sm q-py-xs text-weight-bold"
              data-testid="summary-unlocked-badge"
            >
              {{ selectedCompanySummary.unlockedCount }} Unlocked ({{ selectedCompanySummary.unlockedTotalFormatted }})
            </q-badge>
            <q-badge color="amber-2" text-color="amber-10" class="q-px-sm q-py-xs text-weight-bold" data-testid="summary-locked-badge">
              <q-icon name="lock" size="12px" class="q-mr-xs" />
              {{ selectedCompanySummary.lockedCount }} Locked
            </q-badge>
            <q-chip v-if="isWaveMode" dense color="positive" text-color="white" icon="cloud_done" class="text-weight-bold">
              Wave Connected
            </q-chip>
          </template>
          <div v-else class="text-body2 text-grey-7" data-testid="export-no-company-prompt">
            Select a company in the filter bar above to preview allocations and synchronize or export.
          </div>
        </div>

        <!-- Action Buttons -->
        <div class="row items-center q-gutter-sm">
          <!-- Wave Connected Mode -->
          <template v-if="isWaveMode">
            <q-btn
              unelevated
              color="primary"
              icon="cloud_upload"
              label="Sync to Wave"
              :loading="syncingToWave"
              :disable="!canSyncSelectedToWave || syncingToWave"
              data-testid="btn-sync-to-wave"
              @click="onSyncToWave"
            >
              <q-tooltip v-if="selectedRows.length === 0">Select one or more categorized rows to sync to Wave</q-tooltip>
              <q-tooltip v-else-if="!canSyncSelectedToWave">All selected rows must have a category assigned</q-tooltip>
              <q-tooltip v-else>Push {{ selectedRows.length }} categorized transactions directly to Wave</q-tooltip>
            </q-btn>

            <q-btn
              flat
              color="grey-8"
              icon="download"
              label="Export CSV"
              :loading="exporting"
              :disable="!controls.company_id || exporting"
              data-testid="btn-export-csv"
              @click="onExportCsv"
            >
              <q-tooltip>Download Wave CSV backup</q-tooltip>
            </q-btn>
          </template>

          <!-- Standard Unlinked Mode -->
          <template v-else>
            <q-btn
              unelevated
              color="primary"
              icon="download"
              label="Export CSV"
              :loading="exporting"
              :disable="!controls.company_id || exporting"
              data-testid="btn-export-csv"
              @click="onExportCsv"
            >
              <q-tooltip v-if="!controls.company_id">Select a company first to export CSV</q-tooltip>
              <q-tooltip v-else>Download Wave CSV and automatically lock exported allocations</q-tooltip>
            </q-btn>
          </template>
        </div>
      </q-card-section>
    </q-card>

    <!-- Allocations Preview Table -->
    <q-table
      :rows="allocationRows"
      :columns="columns"
      row-key="id"
      :loading="transactionStore.loading"
      v-model:pagination="pagination"
      :rows-per-page-options="[20, 50, 100]"
      flat
      bordered
      class="shadow-1 export-allocations-table"
      data-testid="table-export-allocations"
      @request="onRequest"
    >
      <!-- Header Selection Slot (Wave Mode) -->
      <template #header-cell-selection="props">
        <q-th :props="props" auto-width>
          <q-checkbox
            :model-value="isAllSelected"
            :disable="eligibleRows.length === 0"
            dense
            data-testid="checkbox-select-all"
            @update:model-value="toggleSelectAll"
          />
        </q-th>
      </template>

      <!-- Row Selection Checkbox (Wave Mode) -->
      <template #body-cell-selection="props">
        <q-td :props="props" auto-width>
          <q-checkbox
            :model-value="isRowSelected(props.row)"
            :disable="props.row.is_locked || isWaveAlreadySynced(props.row)"
            dense
            :data-testid="`checkbox-row-${props.row.id}`"
            @update:model-value="() => toggleRowSelect(props.row)"
          />
        </q-td>
      </template>

      <!-- Date Column -->
      <template #body-cell-date="props">
        <q-td :props="props">
          <span class="text-weight-medium">{{ props.row.date }}</span>
        </q-td>
      </template>

      <!-- Description Column -->
      <template #body-cell-description="props">
        <q-td :props="props">
          <div class="text-weight-medium">{{ props.row.description }}</div>
        </q-td>
      </template>

      <!-- Amount Column -->
      <template #body-cell-amount="props">
        <q-td :props="props" align="right">
          <span :class="Number(props.row.amount) < 0 ? 'text-negative text-weight-bold' : 'text-weight-bold'">
            {{ formatCurrency(props.row.amount) }}
          </span>
        </q-td>
      </template>

      <!-- Category Column (Wave Mode) -->
      <template #body-cell-category="props">
        <q-td :props="props">
          <div style="min-width: 200px">
            <q-select
              :model-value="props.row.wave_category_id"
              :options="categoryOptions"
              emit-value
              map-options
              dense
              outlined
              clearable
              :disable="props.row.is_locked"
              placeholder="Select Category..."
              :data-testid="`select-row-category-${props.row.id}`"
              @update:model-value="(val: string | null) => onCategoryChange(props.row, val)"
            >
              <template #selected-item="scope">
                <span :class="scope.opt.is_uncategorized ? 'text-grey-7 italic' : ''">
                  {{ scope.opt.label }}
                </span>
              </template>
              <template #option="scope">
                <q-item v-bind="scope.itemProps">
                  <q-item-section>
                    <q-item-label :class="scope.opt.is_uncategorized ? 'text-primary text-weight-medium' : ''">
                      {{ scope.opt.label }}
                    </q-item-label>
                    <q-item-label v-if="scope.opt.is_uncategorized" caption class="text-grey-6"> Wave System Default </q-item-label>
                  </q-item-section>
                </q-item>
              </template>
            </q-select>
            <div v-if="!props.row.wave_category_id" class="q-mt-xs">
              <q-chip dense color="warning" text-color="white" size="xs" data-testid="chip-category-required"> Category Required </q-chip>
            </div>
          </div>
        </q-td>
      </template>

      <!-- Lock / Sync Status Column -->
      <template #body-cell-is_locked="props">
        <q-td :props="props" align="center">
          <!-- Wave Connected Mode Status Badges -->
          <template v-if="isWaveMode">
            <!-- Synced to Wave -->
            <q-badge
              v-if="props.row.is_locked && props.row.wave_transaction_id"
              color="positive"
              text-color="white"
              class="q-px-sm q-py-xs text-weight-bold"
              data-testid="badge-synced-to-wave"
            >
              <q-icon name="check_circle" size="12px" class="q-mr-xs" />
              Synced to Wave
            </q-badge>

            <!-- Already in Wave (Unlocked after sync) -->
            <q-badge
              v-else-if="!props.row.is_locked && props.row.wave_transaction_id"
              color="warning"
              text-color="white"
              class="q-px-sm q-py-xs text-weight-bold cursor-pointer"
              data-testid="badge-already-in-wave"
            >
              <q-icon name="warning" size="12px" class="q-mr-xs" />
              Already in Wave
              <q-tooltip>Previously pushed to Wave. Wave does not allow updates via API; adjust in Wave directly.</q-tooltip>
            </q-badge>

            <!-- Locked (CSV export locked) -->
            <q-badge
              v-else-if="props.row.is_locked"
              color="amber-2"
              text-color="amber-10"
              class="q-px-sm q-py-xs text-weight-bold"
              data-testid="badge-allocation-locked"
            >
              <q-icon name="lock" size="12px" class="q-mr-xs" />
              Locked
            </q-badge>

            <!-- Unlocked -->
            <q-badge
              v-else
              color="green-1"
              text-color="positive"
              class="q-px-sm q-py-xs text-weight-bold"
              data-testid="badge-allocation-unlocked"
            >
              <q-icon name="lock_open" size="12px" class="q-mr-xs" />
              Unlocked
            </q-badge>
          </template>

          <!-- Standard Unlinked Company Mode Status Badges -->
          <template v-else>
            <q-badge
              v-if="props.row.is_locked"
              color="amber-2"
              text-color="amber-10"
              class="q-px-sm q-py-xs text-weight-bold"
              data-testid="badge-allocation-locked"
            >
              <q-icon name="lock" size="12px" class="q-mr-xs" />
              Locked
            </q-badge>
            <q-badge
              v-else
              color="green-1"
              text-color="positive"
              class="q-px-sm q-py-xs text-weight-bold"
              data-testid="badge-allocation-unlocked"
            >
              <q-icon name="lock_open" size="12px" class="q-mr-xs" />
              Unlocked
            </q-badge>
          </template>
        </q-td>
      </template>

      <!-- Receipt Column -->
      <template #body-cell-receipt="props">
        <q-td :props="props" align="center">
          <q-btn
            v-if="props.row.receipt_file_path"
            flat
            round
            dense
            size="sm"
            icon="receipt"
            color="primary"
            aria-label="View Receipt"
            data-testid="btn-view-receipt"
            @click="openReceipt(props.row.receipt_file_path)"
          >
            <q-tooltip>View receipt in new tab</q-tooltip>
          </q-btn>
          <span v-else class="text-grey-5">—</span>
        </q-td>
      </template>

      <!-- Parent Transaction Column -->
      <template #body-cell-ledger="props">
        <q-td :props="props" align="right">
          <q-btn
            flat
            dense
            no-wrap
            size="sm"
            color="primary"
            icon-right="open_in_new"
            label="View in Ledger"
            :href="getLedgerTransactionUrl(props.row.transaction_id)"
            target="_blank"
            rel="noopener noreferrer"
            data-testid="link-open-in-ledger"
          >
            <q-tooltip>Open parent transaction in Ledger (new tab)</q-tooltip>
          </q-btn>
        </q-td>
      </template>

      <!-- Empty State -->
      <template #no-data>
        <div class="full-width row flex-center text-grey-7 q-gutter-sm q-pa-lg">
          <q-icon size="2em" :name="controls.company_id ? 'receipt_long' : 'business'" />
          <span v-if="!controls.company_id">Select a company above to review allocations.</span>
          <span v-else>No matching allocations found for the selected company and filters.</span>
        </div>
      </template>
    </q-table>

    <!-- Wave Sync Summary Dialog -->
    <q-dialog v-model="showSyncSummary" persistent>
      <q-card style="min-width: 440px; max-width: 560px; width: 100%" data-testid="dialog-sync-summary">
        <q-card-section class="row items-center q-pb-none">
          <div class="text-h6 text-weight-bold">Wave Synchronization Complete</div>
          <q-space />
          <q-btn icon="close" flat round dense v-close-popup />
        </q-card-section>

        <q-card-section class="q-pt-sm">
          <div v-if="syncSummaryData" class="q-gutter-y-sm">
            <q-banner rounded dense class="bg-positive text-white">
              <template #avatar>
                <q-icon name="check_circle" color="white" />
              </template>
              <strong>{{ syncSummaryData.synced_count }}</strong> of <strong>{{ syncSummaryData.total_processed }}</strong> transactions
              successfully synced to Wave.
            </q-banner>

            <div v-if="syncSummaryData.failed_count > 0" class="q-mt-sm">
              <div class="text-subtitle2 text-negative text-weight-bold q-mb-xs">
                {{ syncSummaryData.failed_count }} Failed Transactions:
              </div>
              <q-list bordered separator class="rounded-borders">
                <q-item v-for="(err, idx) in syncSummaryData.errors" :key="idx">
                  <q-item-section>
                    <q-item-label class="text-weight-medium">{{ err.description }}</q-item-label>
                    <q-item-label caption class="text-negative">{{ err.error }}</q-item-label>
                  </q-item-section>
                </q-item>
              </q-list>
            </div>
          </div>
        </q-card-section>

        <q-card-actions align="right">
          <q-btn flat label="Close" color="primary" v-close-popup />
        </q-card-actions>
      </q-card>
    </q-dialog>
  </q-page>
</template>
