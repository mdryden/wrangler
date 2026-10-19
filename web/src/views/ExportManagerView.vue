<script setup lang="ts">
import { computed, onMounted, ref } from "vue"
import { Notify, useQuasar, type QTableColumn } from "quasar"
import { useCompanyStore } from "../stores/companies"
import { useTransactionStore } from "../stores/transactions"
import type { Company } from "../types/company"
import {
  buildCompanyExportOptions,
  canExportCompany,
  createInitialExportControlsState,
  DEFAULT_EXPORT_PAGE_SIZE,
  extractCompanyAllocationRows,
  formatCurrency,
  getCompanyExportSummary,
  getLedgerTransactionUrl,
  openTransactionInLedgerNewTab,
  resetExportControlsState,
  type ExportAllocationRow,
} from "./exportManager"

const companyStore = useCompanyStore()
const transactionStore = useTransactionStore()

const controls = ref(createInitialExportControlsState())
const exporting = ref<boolean>(false)

const pagination = ref({
  sortBy: "date",
  descending: false,
  page: 1,
  rowsPerPage: DEFAULT_EXPORT_PAGE_SIZE,
  rowsNumber: 0,
})

function notifySuccess(message: string): void {
  try {
    const q = useQuasar()
    if (q?.notify) {
      q.notify({ type: "positive", message, position: "top", timeout: 2500 })
      return
    }
  } catch {
    // fallback
  }
  Notify.create({ type: "positive", message, position: "top", timeout: 2500 })
}

function notifyError(message: string): void {
  try {
    const q = useQuasar()
    if (q?.notify) {
      q.notify({ type: "negative", message, position: "top", timeout: 4000 })
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

const columns: QTableColumn[] = [
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
]

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
  onRequest({ pagination: pagination.value })
}

function resetControls(): void {
  resetExportControlsState(controls.value)
  transactionStore.transactions = []
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
  selectedCompany,
  selectedCompanySummary,
  allocationRows,
  previewTotalAmountFormatted,
  loadCompanies,
  onRequest,
  applyFilters,
  resetControls,
  refresh,
  onExportCsv,
  openReceipt,
  getLedgerTransactionUrl,
  openTransactionInLedgerNewTab,
  canExportCompany,
  getCompanyExportSummary,
  formatCurrency,
})
</script>

<template>
  <q-page class="q-pa-md">
    <!-- Page Header -->
    <div class="row items-center justify-between q-mb-md">
      <div>
        <div class="text-h5 text-weight-bold text-grey-9">Export Manager</div>
        <div class="text-caption text-grey-7">
          Select a company to review its business allocations and generate a Wave-compatible CSV export.
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
          <!-- Company Dropdown (Starts Empty) -->
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

    <!-- Export Action Bar (Under Filter Bar, Above Allocations Table) -->
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
            <q-badge color="green-1" text-color="positive" class="q-px-sm q-py-xs text-weight-bold" data-testid="summary-unlocked-badge">
              {{ selectedCompanySummary.unlockedCount }} Unlocked ({{ selectedCompanySummary.unlockedTotalFormatted }})
            </q-badge>
            <q-badge color="amber-2" text-color="amber-10" class="q-px-sm q-py-xs text-weight-bold" data-testid="summary-locked-badge">
              <q-icon name="lock" size="12px" class="q-mr-xs" />
              {{ selectedCompanySummary.lockedCount }} Locked
            </q-badge>
          </template>
          <div v-else class="text-body2 text-grey-7" data-testid="export-no-company-prompt">
            Select a company in the filter bar above to preview allocations and export a Wave CSV file.
          </div>
        </div>

        <div class="row items-center q-gutter-sm">
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

      <!-- Lock Status Column -->
      <template #body-cell-is_locked="props">
        <q-td :props="props" align="center">
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

      <!-- Parent Transaction (Open in Ledger New Tab) Column -->
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
          <span v-if="!controls.company_id">Select a company above to review allocations for export.</span>
          <span v-else>No matching allocations found for the selected company and filters.</span>
        </div>
      </template>
    </q-table>
  </q-page>
</template>
