<script setup lang="ts">
import { computed, onMounted, ref } from "vue"
import { Notify, useQuasar, type QTableColumn } from "quasar"
import TransactionEditDialog from "../components/TransactionEditDialog.vue"
import { useCompanyStore } from "../stores/companies"
import { useTransactionStore } from "../stores/transactions"
import type { Allocation, Transaction } from "../types/transaction"
import {
  canDeleteTransaction,
  DELETE_LOCKED_TOOLTIP,
  formatCurrency,
  getAllocationItemLabel,
  getAllocationLabel,
  getSingleAllocationCompany,
  getTransactionLockBadge,
  getTransactionLockStatus,
  hasLockedAllocations,
  isTransactionFullyLocked,
  isTransactionPartiallyLocked,
  UNLOCK_WARNING_MESSAGE,
} from "./ledger"

import { useRoute, useRouter } from "vue-router"

const companyStore = useCompanyStore()
const transactionStore = useTransactionStore()

let route: ReturnType<typeof useRoute> | null = null
let routerInstance: ReturnType<typeof useRouter> | null = null
try {
  route = useRoute()
  routerInstance = useRouter()
} catch {
  // Outside router context in standalone unit tests
}

const editDialogVisible = ref<boolean>(false)
const selectedTransaction = ref<Transaction | null>(null)

// Confirmation dialog state for unlocking an allocation or all allocations on a transaction
const unlockConfirmVisible = ref<boolean>(false)
const pendingUnlockTransaction = ref<Transaction | null>(null)
const pendingUnlockAllocation = ref<Allocation | null>(null)

// Confirmation dialog state for deleting a transaction
const deleteConfirmVisible = ref<boolean>(false)
const pendingDeleteTransaction = ref<Transaction | null>(null)

const filters = ref({
  source: "",
  company_id: null as string | null,
  start_date: "",
  end_date: "",
  transaction_id: null as string | null,
})

function notifySuccess(message: string) {
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

function notifyError(message: string) {
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

const companyOptions = computed(() => [
  { label: "All Companies", value: null },
  ...companyStore.companies.map(c => ({ label: c.name, value: c.id })),
])

const companyMap = computed(() => new Map(companyStore.companies.map(c => [c.id, c.name])))

function getAllocationDisplay(row: Transaction) {
  return getAllocationLabel(row, companyMap.value)
}

const pagination = ref({
  sortBy: "date",
  descending: true,
  page: 1,
  rowsPerPage: 20,
  rowsNumber: 0,
})

const columns = computed<QTableColumn[]>(() => [
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
    align: "left",
    field: (row: Transaction) => getAllocationDisplay(row),
    sortable: false,
  },
  {
    name: "receipt",
    label: "Receipt",
    align: "center",
    field: (row: Transaction) => (row.receipt_file_path ? "Yes" : "No"),
    sortable: false,
  },
  {
    name: "actions",
    label: "Actions",
    align: "right",
    field: () => "",
    sortable: false,
  },
])

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
      transaction_id: filters.value.transaction_id || undefined,
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
    transaction_id: null,
  }
  if (routerInstance && route?.query?.transaction_id) {
    routerInstance.replace({ query: { ...route.query, transaction_id: undefined } }).catch(() => {})
  }
  pagination.value.page = 1
  onRequest({ pagination: pagination.value })
}

function refresh(): void {
  onRequest({ pagination: pagination.value })
}

function openEditDialog(row: Transaction): void {
  selectedTransaction.value = row
  editDialogVisible.value = true
}

function onTransactionSaved(): void {
  refresh()
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

async function onToggleSingleAllocationLock(alloc: Allocation): Promise<void> {
  if (alloc.is_locked) {
    pendingUnlockAllocation.value = alloc
    pendingUnlockTransaction.value = null
    unlockConfirmVisible.value = true
  } else {
    try {
      await transactionStore.lockAllocation(alloc.id, true)
      notifySuccess("Allocation locked")
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Failed to lock allocation"
      notifyError(msg)
    }
  }
}

async function onToggleTransactionLock(row: Transaction): Promise<void> {
  if (row.allocations.length > 1) {
    // Handled by the per-allocation q-menu attached to the button
    return
  }
  if (row.allocations.length === 1) {
    await onToggleSingleAllocationLock(row.allocations[0])
    return
  }
  try {
    await transactionStore.lockTransaction(row.id, true)
    notifySuccess("Transaction locked")
  } catch (err) {
    const msg = err instanceof Error ? err.message : "Failed to lock transaction"
    notifyError(msg)
  }
}

async function onLockAllAllocations(row: Transaction): Promise<void> {
  try {
    await transactionStore.lockTransaction(row.id, true)
    notifySuccess("All allocations locked")
  } catch (err) {
    const msg = err instanceof Error ? err.message : "Failed to lock allocations"
    notifyError(msg)
  }
}

function onRequestUnlockAllAllocations(row: Transaction): void {
  pendingUnlockTransaction.value = row
  pendingUnlockAllocation.value = null
  unlockConfirmVisible.value = true
}

async function confirmUnlockTransaction(): Promise<void> {
  const alloc = pendingUnlockAllocation.value
  const tx = pendingUnlockTransaction.value
  unlockConfirmVisible.value = false
  pendingUnlockAllocation.value = null
  pendingUnlockTransaction.value = null

  if (alloc) {
    try {
      await transactionStore.lockAllocation(alloc.id, false)
      notifySuccess("Allocation unlocked")
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Failed to unlock allocation"
      notifyError(msg)
    }
    return
  }

  if (tx) {
    try {
      await transactionStore.lockTransaction(tx.id, false)
      notifySuccess("All allocations unlocked")
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Failed to unlock transaction"
      notifyError(msg)
    }
  }
}

function cancelUnlockTransaction(): void {
  unlockConfirmVisible.value = false
  pendingUnlockAllocation.value = null
  pendingUnlockTransaction.value = null
}

function onDeleteTransaction(row: Transaction): void {
  if (!canDeleteTransaction(row)) return
  pendingDeleteTransaction.value = row
  deleteConfirmVisible.value = true
}

async function confirmDeleteTransaction(): Promise<void> {
  const tx = pendingDeleteTransaction.value
  deleteConfirmVisible.value = false
  pendingDeleteTransaction.value = null
  if (!tx) return

  try {
    await transactionStore.deleteTransaction(tx.id)
    notifySuccess("Transaction deleted")
    refresh()
  } catch (err) {
    const msg = err instanceof Error ? err.message : "Failed to delete transaction"
    notifyError(msg)
  }
}

function cancelDeleteTransaction(): void {
  deleteConfirmVisible.value = false
  pendingDeleteTransaction.value = null
}

onMounted(() => {
  const queryTxId = route?.query?.transaction_id
  if (typeof queryTxId === "string" && queryTxId.trim()) {
    filters.value.transaction_id = queryTxId.trim()
  }
  companyStore.fetchCompanies().catch(() => {})
  onRequest({ pagination: pagination.value })
})

defineExpose({
  filters,
  pagination,
  columns,
  companyMap,
  editDialogVisible,
  selectedTransaction,
  unlockConfirmVisible,
  pendingUnlockTransaction,
  pendingUnlockAllocation,
  deleteConfirmVisible,
  pendingDeleteTransaction,
  getAllocationDisplay,
  getAllocationItemLabel,
  getSingleAllocationCompany,
  getTransactionLockStatus,
  getTransactionLockBadge,
  isTransactionFullyLocked,
  isTransactionPartiallyLocked,
  hasLockedAllocations,
  canDeleteTransaction,
  formatCurrency,
  applyFilters,
  resetFilters,
  refresh,
  openEditDialog,
  onTransactionSaved,
  openReceipt,
  onToggleTransactionLock,
  onToggleSingleAllocationLock,
  onLockAllAllocations,
  onRequestUnlockAllAllocations,
  confirmUnlockTransaction,
  cancelUnlockTransaction,
  onDeleteTransaction,
  confirmDeleteTransaction,
  cancelDeleteTransaction,
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
          <div class="row items-center no-wrap q-gutter-x-xs">
            <q-icon v-if="isTransactionFullyLocked(props.row)" name="lock" color="amber-9" size="16px" data-testid="icon-row-fully-locked">
              <q-tooltip>Fully Locked</q-tooltip>
            </q-icon>
            <q-icon
              v-else-if="isTransactionPartiallyLocked(props.row)"
              name="lock_open"
              color="orange-7"
              size="16px"
              data-testid="icon-row-partially-locked"
            >
              <q-tooltip>Partially Locked</q-tooltip>
            </q-icon>
            <span class="text-weight-medium">{{ props.row.date }}</span>
          </div>
        </q-td>
      </template>

      <!-- Description Column -->
      <template #body-cell-description="props">
        <q-td :props="props">
          <div class="text-weight-medium">{{ props.row.description }}</div>
        </q-td>
      </template>

      <!-- Amount Column -->
      <template #body-cell-total_amount="props">
        <q-td :props="props" align="right">
          <span :class="Number(props.row.total_amount) < 0 ? 'text-negative text-weight-bold' : 'text-weight-bold'">
            {{ formatCurrency(props.row.total_amount) }}
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
        <q-td :props="props">
          <div class="row items-center no-wrap q-gutter-x-xs">
            <span class="text-weight-medium" data-testid="allocation-cell">{{ getAllocationDisplay(props.row) }}</span>
            <q-badge
              v-if="isTransactionFullyLocked(props.row)"
              color="amber-2"
              text-color="amber-10"
              class="q-px-xs"
              data-testid="badge-fully-locked"
            >
              <q-icon name="lock" size="12px" class="q-mr-xs" />
              Locked
            </q-badge>
            <q-badge
              v-else-if="isTransactionPartiallyLocked(props.row)"
              color="orange-2"
              text-color="orange-10"
              class="q-px-xs"
              data-testid="badge-partially-locked"
            >
              <q-icon name="lock_open" size="12px" class="q-mr-xs" />
              Partial Lock
            </q-badge>
          </div>
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

      <!-- Actions Column -->
      <template #body-cell-actions="props">
        <q-td :props="props" align="right">
          <div class="row items-center justify-end q-gutter-xs no-wrap">
            <!-- Edit Button -->
            <q-btn
              flat
              round
              dense
              size="sm"
              color="grey-8"
              icon="edit"
              aria-label="Edit transaction"
              data-testid="btn-edit-transaction"
              @click="openEditDialog(props.row)"
            >
              <q-tooltip>Edit transaction</q-tooltip>
            </q-btn>

            <!-- Lock / Unlock Toggle Button -->
            <q-btn
              flat
              round
              dense
              size="sm"
              :color="isTransactionFullyLocked(props.row) ? 'amber-9' : isTransactionPartiallyLocked(props.row) ? 'orange-7' : 'grey-7'"
              :icon="isTransactionFullyLocked(props.row) ? 'lock' : 'lock_open'"
              :aria-label="
                props.row.allocations.length > 1
                  ? 'Manage split locks'
                  : isTransactionFullyLocked(props.row)
                    ? 'Unlock transaction'
                    : 'Lock transaction'
              "
              data-testid="btn-toggle-lock"
              @click="onToggleTransactionLock(props.row)"
            >
              <q-tooltip>
                <template v-if="props.row.allocations.length > 1">Manage split locks</template>
                <template v-else>{{ isTransactionFullyLocked(props.row) ? "Unlock transaction" : "Lock transaction" }}</template>
              </q-tooltip>

              <!-- Per-Allocation Lock Popup Menu for Multi-Split Transactions -->
              <q-menu v-if="props.row.allocations.length > 1" anchor="bottom right" self="top right" data-testid="menu-allocation-locks">
                <div style="min-width: 300px">
                  <div class="q-px-md q-py-sm bg-grey-2">
                    <div class="text-subtitle2 text-weight-bold text-grey-9">Manage Split Locks</div>
                    <div class="text-caption text-grey-7 ellipsis">{{ props.row.description }}</div>
                  </div>
                  <q-separator />
                  <q-list dense separator>
                    <q-item v-for="(alloc, idx) in props.row.allocations" :key="alloc.id" class="q-py-xs">
                      <q-item-section>
                        <q-item-label class="text-weight-medium">
                          {{ getAllocationItemLabel(alloc, companyMap) }}
                        </q-item-label>
                        <q-item-label caption>
                          {{ formatCurrency(alloc.amount) }}
                        </q-item-label>
                      </q-item-section>
                      <q-item-section side>
                        <q-btn
                          flat
                          dense
                          no-wrap
                          size="sm"
                          :color="alloc.is_locked ? 'amber-9' : 'grey-7'"
                          :icon="alloc.is_locked ? 'lock' : 'lock_open'"
                          :label="alloc.is_locked ? 'Locked' : 'Unlocked'"
                          :data-testid="`btn-toggle-alloc-lock-${idx}`"
                          @click="onToggleSingleAllocationLock(alloc)"
                        />
                      </q-item-section>
                    </q-item>
                  </q-list>
                  <q-separator />
                  <div class="row items-center justify-end q-gutter-x-xs q-px-sm q-py-xs bg-grey-1">
                    <q-btn
                      flat
                      dense
                      no-wrap
                      size="sm"
                      color="amber-9"
                      icon="lock"
                      label="Lock All"
                      :disable="isTransactionFullyLocked(props.row)"
                      data-testid="btn-lock-all-splits"
                      @click="onLockAllAllocations(props.row)"
                    />
                    <q-btn
                      flat
                      dense
                      no-wrap
                      size="sm"
                      color="grey-8"
                      icon="lock_open"
                      label="Unlock All"
                      :disable="!hasLockedAllocations(props.row)"
                      v-close-popup
                      data-testid="btn-unlock-all-splits"
                      @click="onRequestUnlockAllAllocations(props.row)"
                    />
                  </div>
                </div>
              </q-menu>
            </q-btn>

            <!-- Delete Button -->
            <div>
              <q-btn
                flat
                round
                dense
                size="sm"
                color="negative"
                icon="delete"
                aria-label="Delete transaction"
                :disable="!canDeleteTransaction(props.row)"
                data-testid="btn-delete-transaction"
                @click="onDeleteTransaction(props.row)"
              />
              <q-tooltip>
                {{ canDeleteTransaction(props.row) ? "Delete transaction" : DELETE_LOCKED_TOOLTIP }}
              </q-tooltip>
            </div>
          </div>
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

    <!-- Unified Transaction & Allocation Editor Dialog -->
    <TransactionEditDialog v-model="editDialogVisible" :transaction="selectedTransaction" @saved="onTransactionSaved" />

    <!-- Allocation / Transaction Unlock Warning Confirmation Dialog -->
    <q-dialog v-model="unlockConfirmVisible" persistent>
      <q-card style="max-width: 440px; width: 100%" data-testid="dialog-unlock-transaction-warning">
        <q-card-section class="row items-center">
          <q-avatar icon="warning" color="amber-9" text-color="white" class="q-mr-md" />
          <div class="text-h6 text-weight-bold">
            {{ pendingUnlockAllocation ? "Unlock Allocation" : "Unlock All Allocations" }}
          </div>
        </q-card-section>

        <q-card-section class="q-pt-none" data-testid="unlock-transaction-warning-message">
          {{ UNLOCK_WARNING_MESSAGE }}
        </q-card-section>

        <q-card-actions align="right">
          <q-btn flat label="Cancel" color="grey-7" data-testid="btn-cancel-unlock-transaction" @click="cancelUnlockTransaction" />
          <q-btn unelevated label="Unlock" color="amber-9" data-testid="btn-confirm-unlock-transaction" @click="confirmUnlockTransaction" />
        </q-card-actions>
      </q-card>
    </q-dialog>

    <!-- Transaction Delete Confirmation Dialog -->
    <q-dialog v-model="deleteConfirmVisible" persistent>
      <q-card style="max-width: 440px; width: 100%" data-testid="dialog-delete-transaction">
        <q-card-section class="row items-center">
          <q-avatar icon="delete" color="negative" text-color="white" class="q-mr-md" />
          <div class="text-h6 text-weight-bold">Delete Transaction</div>
        </q-card-section>

        <q-card-section class="q-pt-none">
          Are you sure you want to delete this transaction
          <strong v-if="pendingDeleteTransaction">"{{ pendingDeleteTransaction.description }}"</strong>? This action cannot be undone.
        </q-card-section>

        <q-card-actions align="right">
          <q-btn flat label="Cancel" color="grey-7" data-testid="btn-cancel-delete-transaction" @click="cancelDeleteTransaction" />
          <q-btn
            unelevated
            label="Delete"
            color="negative"
            data-testid="btn-confirm-delete-transaction"
            @click="confirmDeleteTransaction"
          />
        </q-card-actions>
      </q-card>
    </q-dialog>
  </q-page>
</template>
