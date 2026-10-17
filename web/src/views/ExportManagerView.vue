<script setup lang="ts">
import { onMounted, ref } from "vue"
import { Notify, useQuasar, type QTableColumn } from "quasar"
import { useCompanyStore } from "../stores/companies"
import type { Company } from "../types/company"
import {
  buildCompanyExportOptions,
  canExportCompany,
  createInitialExportControlsState,
  formatCurrency,
  getCompanyExportSummary,
  resetExportControlsState,
} from "./exportManager"

const companyStore = useCompanyStore()

const controls = ref(createInitialExportControlsState())
const exportingCompanyId = ref<string | null>(null)

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

const columns: QTableColumn[] = [
  {
    name: "name",
    required: true,
    label: "Company Name",
    align: "left",
    field: (row: Company) => row.name,
    sortable: true,
  },
  {
    name: "unlocked_allocation_count",
    label: "Unlocked Allocations",
    align: "center",
    field: (row: Company) => row.unlocked_allocation_count ?? 0,
    sortable: true,
  },
  {
    name: "unlocked_amount_total",
    label: "Unlocked Amount",
    align: "right",
    field: (row: Company) => Number(row.unlocked_amount_total ?? 0),
    sortable: true,
  },
  {
    name: "locked_allocation_count",
    label: "Locked Allocations",
    align: "center",
    field: (row: Company) => row.locked_allocation_count ?? 0,
    sortable: true,
  },
  {
    name: "actions",
    label: "Actions",
    align: "right",
    field: () => "",
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

function resetControls(): void {
  resetExportControlsState(controls.value)
}

async function onExportCompany(company: Company): Promise<void> {
  exportingCompanyId.value = company.id
  try {
    const options = buildCompanyExportOptions(controls.value)
    await companyStore.exportTransactionsCsv(company.id, options)
    notifySuccess(`Exported CSV for "${company.name}"`)
  } catch (err) {
    const msg = err instanceof Error ? err.message : "Failed to export CSV"
    notifyError(msg)
  } finally {
    exportingCompanyId.value = null
  }
}

onMounted(() => {
  loadCompanies()
})

defineExpose({
  controls,
  columns,
  exportingCompanyId,
  loadCompanies,
  resetControls,
  onExportCompany,
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
          Generate Wave-compatible CSV exports per company. Exported business allocations are automatically locked.
        </div>
      </div>
      <div class="row items-center q-gutter-sm">
        <q-btn
          flat
          dense
          round
          icon="refresh"
          color="grey-7"
          aria-label="Refresh Export Summary"
          data-testid="btn-refresh-exports"
          :loading="companyStore.loading"
          @click="loadCompanies"
        >
          <q-tooltip>Refresh export summary</q-tooltip>
        </q-btn>
      </div>
    </div>

    <!-- Error Banner -->
    <q-banner v-if="companyStore.error" rounded dense inline-actions class="bg-negative text-white q-mb-md">
      <template #avatar>
        <q-icon name="error" color="white" />
      </template>
      {{ companyStore.error }}
      <template #action>
        <q-btn flat label="Retry" color="white" @click="loadCompanies" />
      </template>
    </q-banner>

    <!-- Export Options & Controls -->
    <q-card flat bordered class="q-mb-md bg-grey-1">
      <q-card-section class="q-py-sm">
        <div class="row q-col-gutter-md items-center">
          <!-- Include Locked Transactions Toggle -->
          <div class="col-12 col-md-4">
            <q-toggle
              v-model="controls.include_locked"
              color="primary"
              label="Include locked transactions"
              data-testid="toggle-include-locked"
            />
          </div>

          <!-- Start Date Filter -->
          <div class="col-12 col-sm-6 col-md-3">
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
            />
          </div>

          <!-- End Date Filter -->
          <div class="col-12 col-sm-6 col-md-3">
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
            />
          </div>

          <!-- Reset Button -->
          <div class="col-12 col-md-2 row items-center justify-end">
            <q-btn flat color="grey-7" icon="clear" label="Reset" data-testid="btn-reset-export-controls" @click="resetControls" />
          </div>
        </div>
      </q-card-section>
    </q-card>

    <!-- Empty State -->
    <q-card v-if="!companyStore.loading && companyStore.companies.length === 0" flat bordered class="text-center q-pa-xl bg-grey-1">
      <q-icon name="domain_disabled" size="64px" color="grey-5" class="q-mb-sm" />
      <div class="text-h6 text-grey-8 text-weight-medium">No Companies Configured</div>
      <div class="text-body2 text-grey-6">Add a company in Settings and allocate business transactions to export Wave CSV files.</div>
    </q-card>

    <!-- Company Export Summary Table -->
    <q-table
      v-else
      :rows="companyStore.companies"
      :columns="columns"
      row-key="id"
      :loading="companyStore.loading"
      flat
      bordered
      :pagination="{ rowsPerPage: 10 }"
      class="shadow-1 export-summary-table"
      data-testid="table-company-exports"
    >
      <!-- Company Name -->
      <template #body-cell-name="props">
        <q-td :props="props">
          <div class="row items-center no-wrap">
            <q-avatar size="32px" color="blue-1" text-color="primary" icon="business" class="q-mr-sm" />
            <div class="text-weight-bold text-body2" data-testid="company-export-name">{{ props.row.name }}</div>
          </div>
        </q-td>
      </template>

      <!-- Unlocked Allocations Count -->
      <template #body-cell-unlocked_allocation_count="props">
        <q-td :props="props" align="center">
          <q-badge
            :color="(props.row.unlocked_allocation_count ?? 0) > 0 ? 'green-1' : 'grey-2'"
            :text-color="(props.row.unlocked_allocation_count ?? 0) > 0 ? 'positive' : 'grey-7'"
            class="text-weight-bold q-px-sm q-py-xs"
            data-testid="company-unlocked-count"
          >
            {{ props.row.unlocked_allocation_count ?? 0 }}
          </q-badge>
        </q-td>
      </template>

      <!-- Unlocked Amount Total -->
      <template #body-cell-unlocked_amount_total="props">
        <q-td :props="props" align="right">
          <span
            :class="Number(props.row.unlocked_amount_total ?? 0) < 0 ? 'text-negative text-weight-bold' : 'text-weight-bold'"
            data-testid="company-unlocked-amount"
          >
            {{ formatCurrency(props.row.unlocked_amount_total ?? 0) }}
          </span>
        </q-td>
      </template>

      <!-- Locked Allocations Count -->
      <template #body-cell-locked_allocation_count="props">
        <q-td :props="props" align="center">
          <q-badge color="amber-2" text-color="amber-10" class="text-weight-bold q-px-sm q-py-xs" data-testid="company-locked-count">
            <q-icon name="lock" size="12px" class="q-mr-xs" />
            {{ props.row.locked_allocation_count ?? 0 }}
          </q-badge>
        </q-td>
      </template>

      <!-- Export CSV Action -->
      <template #body-cell-actions="props">
        <q-td :props="props" align="right">
          <q-btn
            unelevated
            color="primary"
            icon="download"
            label="Export CSV"
            size="sm"
            :loading="exportingCompanyId === props.row.id"
            :disable="exportingCompanyId !== null"
            :data-testid="`btn-export-csv-${props.row.id}`"
            @click="onExportCompany(props.row)"
          />
        </q-td>
      </template>
    </q-table>
  </q-page>
</template>
