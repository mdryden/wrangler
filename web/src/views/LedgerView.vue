<script setup lang="ts">
import { computed, onMounted, ref } from "vue"
import type { QTableColumn } from "quasar"
import { useCompanyStore } from "../stores/companies"
import { useTransactionStore } from "../stores/transactions"
import type { Transaction } from "../types/transaction"

const companyStore = useCompanyStore()
const transactionStore = useTransactionStore()

const filters = ref({
  source: "",
  company_id: null as string | null,
  start_date: "",
  end_date: "",
})

const companyOptions = computed(() => [
  { label: "All Companies", value: null },
  ...companyStore.companies.map(c => ({ label: c.name, value: c.id })),
])

const pagination = ref({
  sortBy: "date",
  descending: true,
  page: 1,
  rowsPerPage: 20,
  rowsNumber: 0,
})

const columns: QTableColumn[] = [
  {
    name: "date",
    required: true,
    label: "Date",
    align: "left",
    field: (row: Transaction) => row.date,
    sortable: true,
  },
  {
    name: "description",
    required: true,
    label: "Description",
    align: "left",
    field: (row: Transaction) => row.description,
    sortable: true,
  },
  {
    name: "total_amount",
    required: true,
    label: "Amount",
    align: "right",
    field: (row: Transaction) => row.total_amount,
    sortable: true,
  },
  {
    name: "source",
    label: "Source",
    align: "left",
    field: (row: Transaction) => row.source,
    sortable: true,
  },
  {
    name: "allocations",
    label: "Allocations",
    align: "center",
    field: (row: Transaction) => row.allocations?.length ?? 0,
    sortable: false,
  },
  {
    name: "receipt",
    label: "Receipt",
    align: "center",
    field: (row: Transaction) => (row.receipt_file_path ? "Yes" : "No"),
    sortable: false,
  },
]

function formatCurrency(amount: string | number, currencyCode = "USD"): string {
  const num = typeof amount === "string" ? parseFloat(amount) : amount
  if (Number.isNaN(num)) return "$0.00"
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: currencyCode || "USD",
  }).format(num)
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
  const { page, rowsPerPage, sortBy, descending } = props.pagination
  try {
    await transactionStore.fetchTransactions({
      page,
      rowsPerPage,
      sortBy: sortBy || undefined,
      descending: descending ?? true,
      source: filters.value.source.trim() || undefined,
      company_id: filters.value.company_id || undefined,
      start_date: filters.value.start_date || undefined,
      end_date: filters.value.end_date || undefined,
    })

    pagination.value.page = transactionStore.page
    pagination.value.rowsPerPage = transactionStore.pageSize
    pagination.value.rowsNumber = transactionStore.total
    pagination.value.sortBy = sortBy ?? "date"
    pagination.value.descending = descending ?? true
  } catch {
    // Handled in store error banner
  }
}

function applyFilters(): void {
  pagination.value.page = 1
  onRequest({ pagination: pagination.value })
}

function resetFilters(): void {
  filters.value = {
    source: "",
    company_id: null,
    start_date: "",
    end_date: "",
  }
  pagination.value.page = 1
  onRequest({ pagination: pagination.value })
}

function refresh(): void {
  onRequest({ pagination: pagination.value })
}

onMounted(() => {
  companyStore.fetchCompanies().catch(() => {})
  onRequest({ pagination: pagination.value })
})
</script>

<template>
  <q-page class="q-pa-md">
    <!-- Page Header -->
    <div class="row items-center justify-between q-mb-md">
      <div>
        <div class="text-h5 text-weight-bold text-grey-9">Ledger</div>
        <div class="text-caption text-grey-7">Review, filter, and allocate transactions.</div>
      </div>
      <div class="row items-center q-gutter-sm">
        <q-btn
          flat
          dense
          round
          icon="refresh"
          color="grey-7"
          aria-label="Refresh Transactions"
          data-testid="btn-refresh"
          :loading="transactionStore.loading"
          @click="refresh"
        >
          <q-tooltip>Refresh transactions</q-tooltip>
        </q-btn>
      </div>
    </div>

    <!-- Error Banner -->
    <q-banner v-if="transactionStore.error" rounded dense inline-actions class="bg-negative text-white q-mb-md">
      <template #avatar>
        <q-icon name="error" color="white" />
      </template>
      {{ transactionStore.error }}
      <template #action>
        <q-btn flat label="Retry" color="white" @click="refresh" />
      </template>
    </q-banner>

    <!-- Filters Section -->
    <q-card flat bordered class="q-mb-md filter-card bg-grey-1">
      <q-card-section class="q-py-sm">
        <div class="row q-col-gutter-sm items-center">
          <!-- Source Filter -->
          <div class="col-12 col-sm-6 col-md-3">
            <q-input
              v-model="filters.source"
              dense
              outlined
              clearable
              bg-color="white"
              label="Source"
              placeholder="e.g. manual..."
              data-testid="filter-source"
              @keyup.enter="applyFilters"
            >
              <template #prepend>
                <q-icon name="search" />
              </template>
            </q-input>
          </div>

          <!-- Company Filter -->
          <div class="col-12 col-sm-6 col-md-3">
            <q-select
              v-model="filters.company_id"
              dense
              outlined
              emit-value
              map-options
              bg-color="white"
              label="Company"
              :options="companyOptions"
              data-testid="filter-company"
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
              v-model="filters.start_date"
              type="date"
              dense
              outlined
              clearable
              stack-label
              bg-color="white"
              label="Start Date"
              data-testid="filter-start-date"
              @keyup.enter="applyFilters"
            />
          </div>

          <!-- End Date Filter -->
          <div class="col-12 col-sm-6 col-md-2">
            <q-input
              v-model="filters.end_date"
              type="date"
              dense
              outlined
              clearable
              stack-label
              bg-color="white"
              label="End Date"
              data-testid="filter-end-date"
              @keyup.enter="applyFilters"
            />
          </div>

          <!-- Filter Action Buttons -->
          <div class="col-12 col-md-2 row items-center justify-end q-gutter-xs">
            <q-btn color="primary" unelevated icon="filter_list" label="Filter" data-testid="btn-apply-filters" @click="applyFilters" />
            <q-btn flat color="grey-7" icon="clear" label="Reset" data-testid="btn-reset-filters" @click="resetFilters" />
          </div>
        </div>
      </q-card-section>
    </q-card>

    <!-- Transactions Table -->
    <q-table
      :rows="transactionStore.transactions"
      :columns="columns"
      row-key="id"
      :loading="transactionStore.loading"
      v-model:pagination="pagination"
      :rows-per-page-options="[10, 20, 50, 100]"
      flat
      bordered
      class="shadow-1 transaction-table"
      @request="onRequest"
    >
      <!-- Date Column -->
      <template #body-cell-date="props">
        <q-td :props="props">
          <div class="text-weight-medium">{{ props.row.date }}</div>
        </q-td>
      </template>

      <!-- Description Column -->
      <template #body-cell-description="props">
        <q-td :props="props">
          <div class="text-weight-medium">{{ props.row.description }}</div>
          <div v-if="props.row.external_id" class="text-caption text-grey-6">ID: {{ props.row.external_id }}</div>
        </q-td>
      </template>

      <!-- Amount Column -->
      <template #body-cell-total_amount="props">
        <q-td :props="props" align="right">
          <span :class="Number(props.row.total_amount) < 0 ? 'text-negative text-weight-bold' : 'text-weight-bold'">
            {{ formatCurrency(props.row.total_amount, props.row.currency_code) }}
          </span>
        </q-td>
      </template>

      <!-- Source Column -->
      <template #body-cell-source="props">
        <q-td :props="props">
          <q-chip dense size="sm" color="blue-1" text-color="primary" class="text-weight-bold">
            {{ props.row.source }}
          </q-chip>
        </q-td>
      </template>

      <!-- Allocations Column -->
      <template #body-cell-allocations="props">
        <q-td :props="props" align="center">
          <q-badge color="grey-2" text-color="grey-9" class="q-px-sm q-py-xs">
            {{ props.row.allocations ? props.row.allocations.length : 0 }} split(s)
          </q-badge>
        </q-td>
      </template>

      <!-- Receipt Column -->
      <template #body-cell-receipt="props">
        <q-td :props="props" align="center">
          <q-icon v-if="props.row.receipt_file_path" name="receipt" color="primary" size="20px">
            <q-tooltip>Receipt attached</q-tooltip>
          </q-icon>
          <span v-else class="text-grey-5">—</span>
        </q-td>
      </template>

      <!-- Empty State -->
      <template #no-data>
        <div class="full-width row flex-center text-grey-7 q-gutter-sm q-pa-lg">
          <q-icon size="2em" name="receipt_long" />
          <span>No transactions found. Try adjusting your filters.</span>
        </div>
      </template>
    </q-table>
  </q-page>
</template>
