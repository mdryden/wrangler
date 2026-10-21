<script setup lang="ts">
import { computed, onMounted, ref } from "vue"
import { Notify, useQuasar, type QTableColumn } from "quasar"
import BulkAllocateDialog from "../components/BulkAllocateDialog.vue"
import StagedTransactionEditDialog from "../components/StagedTransactionEditDialog.vue"
import { useCompanyStore } from "../stores/companies"
import {
  buildQuickAssignPayload,
  canRunImporter,
  formatImporterSummaryToast,
  getAcceptedFileTypesAttr,
  getQuickAssignValue,
  getReadyToAcceptTransactions,
  getStagedAllocationSummary,
  MARK_IMPORTED_CAPABILITY_LABEL,
  PERSONAL_QUICK_ASSIGN_VALUE,
  SOURCE_FILTER_OPTIONS,
  useStagingStore,
} from "../stores/staging"
import { useTransactionStore } from "../stores/transactions"
import type { ImporterMetadata, StagedStatus, StagedTransaction } from "../types/staging"
import {
  formatStagedAmount,
  getImportNotificationType,
  getSelectedReadyIds,
  isMasterHeaderChecked,
  isMasterHeaderIndeterminate,
  stagingTableColumns,
  toggleVisibleStagedRows,
} from "./importView"

const $q = useQuasar()
const companyStore = useCompanyStore()
const stagingStore = useStagingStore()
const transactionStore = useTransactionStore()

const selectedImporterId = ref<string | null>(null)
const importerFile = ref<File | File[] | null>(null)
const runningImporter = ref<boolean>(false)

const filters = ref<{
  status: StagedStatus
  source: string
}>({
  status: "STAGED",
  source: "",
})

const selectedRowIds = ref<string[]>([])
const acceptingBatch = ref<boolean>(false)

const editDialogVisible = ref<boolean>(false)
const bulkAllocateDialogVisible = ref<boolean>(false)
const selectedStagedTransaction = ref<StagedTransaction | null>(null)

const pagination = ref({
  sortBy: "date",
  descending: true,
  page: 1,
  rowsPerPage: 50,
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

function notifyWarning(message: string): void {
  try {
    const q = useQuasar()
    if (q?.notify) {
      q.notify({ type: "warning", message, position: "top", timeout: 6000 })
      return
    }
  } catch {
    // fallback
  }
  Notify.create({ type: "warning", message, position: "top", timeout: 6000 })
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

const selectedImporter = computed<ImporterMetadata | null>(() => {
  if (!selectedImporterId.value) return null
  return stagingStore.importers.find(imp => imp.importer_id === selectedImporterId.value) ?? null
})

const importerOptions = computed(() =>
  stagingStore.importers.map(imp => ({
    label: imp.display_name,
    value: imp.importer_id,
    description: imp.description,
  })),
)

const isRunImporterEnabled = computed(() => canRunImporter(selectedImporter.value, importerFile.value))

const acceptedFileTypes = computed(() => getAcceptedFileTypesAttr(selectedImporter.value))

const statusOptions: { label: string; value: StagedStatus }[] = [
  { label: "Staged", value: "STAGED" },
  { label: "Dismissed", value: "DISMISSED" },
  { label: "Accepted", value: "ACCEPTED" },
]

const companyMap = computed(() => new Map(companyStore.companies.map(c => [c.id, c.name])))

const quickAssignOptions = computed(() => [
  { label: "Personal", value: PERSONAL_QUICK_ASSIGN_VALUE },
  ...companyStore.companies.map(c => ({ label: c.name, value: c.id })),
])

const readyTransactionsToAccept = computed(() => getReadyToAcceptTransactions(stagingStore.stagedTransactions, selectedRowIds.value))

const readyAcceptCount = computed(() => readyTransactionsToAccept.value.length)

const totalReadyCount = computed(() => stagingStore.stagedTransactions.filter(r => r.status === "STAGED" && r.is_ready).length)

const visibleStagedRows = computed(() => stagingStore.stagedTransactions.filter(r => r.status === "STAGED"))

const isHeaderChecked = computed(() =>
  isMasterHeaderChecked(
    visibleStagedRows.value.map(r => r.id),
    selectedRowIds.value,
  ),
)

const isHeaderIndeterminate = computed(() =>
  isMasterHeaderIndeterminate(
    visibleStagedRows.value.map(r => r.id),
    selectedRowIds.value,
  ),
)

const selectedTransactions = computed(() => stagingStore.stagedTransactions.filter(r => selectedRowIds.value.includes(r.id)))

const selectedReadyCount = computed(() => readyTransactionsToAccept.value.length)

const columns: QTableColumn[] = stagingTableColumns

function onSelectImporter(importerId: string | null): void {
  selectedImporterId.value = importerId
  importerFile.value = null
}

async function onRunImporter(): Promise<void> {
  if (!selectedImporter.value || !isRunImporterEnabled.value) return
  runningImporter.value = true
  try {
    const result = await stagingStore.runImporter(
      selectedImporter.value.importer_id,
      selectedImporter.value.input_type === "file" ? importerFile.value : null,
    )
    const summaryToast = formatImporterSummaryToast(result)
    if (getImportNotificationType(result) === "warning") {
      notifyWarning(summaryToast)
    } else {
      notifySuccess(summaryToast)
    }
    importerFile.value = null
    await refreshStagingTable()
  } catch (err) {
    const msg = err instanceof Error ? err.message : "Failed to run importer"
    notifyError(msg)
  } finally {
    runningImporter.value = false
  }
}

async function onRequest(props: {
  pagination: {
    page: number
    rowsPerPage: number
  }
}): Promise<void> {
  const { page, rowsPerPage } = props.pagination
  if (pagination.value.page !== page || pagination.value.rowsPerPage !== rowsPerPage) {
    selectedRowIds.value = []
  }
  try {
    await stagingStore.fetchStagedTransactions({
      status: filters.value.status,
      source: filters.value.source.trim() || null,
      page,
      page_size: rowsPerPage,
    })
    pagination.value.page = stagingStore.page
    pagination.value.rowsPerPage = stagingStore.pageSize
    pagination.value.rowsNumber = stagingStore.total

    // Prune any selected row IDs that are no longer STAGED
    const validStagedIds = new Set(stagingStore.stagedTransactions.filter(r => r.status === "STAGED").map(r => r.id))
    selectedRowIds.value = selectedRowIds.value.filter(id => validStagedIds.has(id))
  } catch {
    // Error handled in store banner
  }
}

async function refreshStagingTable(): Promise<void> {
  await onRequest({ pagination: pagination.value })
}

function applyFilters(): void {
  pagination.value.page = 1
  selectedRowIds.value = []
  onRequest({ pagination: pagination.value })
}

function resetFilters(): void {
  filters.value = {
    status: "STAGED",
    source: "",
  }
  selectedRowIds.value = []
  pagination.value.page = 1
  onRequest({ pagination: pagination.value })
}

function isRowSelected(id: string): boolean {
  return selectedRowIds.value.includes(id)
}

function toggleRowSelection(row: StagedTransaction, checked: boolean): void {
  if (row.status !== "STAGED") return
  if (checked) {
    if (!selectedRowIds.value.includes(row.id)) {
      selectedRowIds.value = [...selectedRowIds.value, row.id]
    }
  } else {
    selectedRowIds.value = selectedRowIds.value.filter(id => id !== row.id)
  }
}

function toggleAllVisibleRows(): void {
  selectedRowIds.value = toggleVisibleStagedRows(
    visibleStagedRows.value.map(r => r.id),
    selectedRowIds.value,
  )
}

function clearSelection(): void {
  selectedRowIds.value = []
}

function openBulkAllocateDialog(): void {
  bulkAllocateDialogVisible.value = true
}

async function onBulkAllocateApplied(): Promise<void> {
  selectedRowIds.value = []
  await refreshStagingTable()
}

function onBulkDismiss(): void {
  if (selectedRowIds.value.length === 0) return
  const count = selectedRowIds.value.length
  $q.dialog({
    title: "Confirm Bulk Dismiss",
    message: `Are you sure you want to dismiss ${count} selected transaction${count === 1 ? "" : "s"}?`,
    cancel: true,
    persistent: true,
    ok: {
      label: "Dismiss",
      color: "negative",
      unelevated: true,
    },
  }).onOk(async () => {
    try {
      const res = await stagingStore.bulkDismissStaged(selectedRowIds.value)
      selectedRowIds.value = []
      notifySuccess(`Successfully dismissed ${res.dismissed_count} transaction(s)`)
      if (res.mark_imported_errors && res.mark_imported_errors.length > 0) {
        notifyWarning(`Dismissed, but failed to mark imported: ${res.mark_imported_errors.join("; ")}`)
      }
      await refreshStagingTable()
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Failed to bulk dismiss transactions"
      notifyError(msg)
    }
  })
}

async function onQuickAssignChange(row: StagedTransaction, value: string | null): Promise<void> {
  if (row.status !== "STAGED") return
  try {
    const payload = buildQuickAssignPayload(row, value)
    await stagingStore.updateStagedTransaction(row.id, payload)
    notifySuccess(value ? "Allocation updated" : "Reset to Unallocated")
  } catch (err) {
    const msg = err instanceof Error ? err.message : "Failed to update allocation"
    notifyError(msg)
  }
}

function openEditDialog(row: StagedTransaction): void {
  selectedStagedTransaction.value = row
  editDialogVisible.value = true
}

function onStagedSaved(): void {
  refreshStagingTable()
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

async function onUploadRowReceipt(row: StagedTransaction, file: File | null): Promise<void> {
  if (!file || row.status !== "STAGED") return
  try {
    await stagingStore.uploadStagedReceipt(row.id, file)
    notifySuccess("Receipt attached")
  } catch (err) {
    const msg = err instanceof Error ? err.message : "Failed to upload receipt"
    notifyError(msg)
  }
}

async function onRemoveRowReceipt(row: StagedTransaction): Promise<void> {
  if (row.status !== "STAGED" || !row.receipt_file_path) return
  try {
    await stagingStore.deleteStagedReceipt(row.id)
    notifySuccess("Receipt removed")
  } catch (err) {
    const msg = err instanceof Error ? err.message : "Failed to remove receipt"
    notifyError(msg)
  }
}

async function onDismissRow(row: StagedTransaction): Promise<void> {
  if (row.status !== "STAGED") return
  try {
    const dismissed = await stagingStore.dismissStagedTransaction(row.id)
    selectedRowIds.value = selectedRowIds.value.filter(id => id !== row.id)
    notifySuccess("Staged transaction dismissed")
    if (dismissed.mark_imported_error) {
      notifyWarning(
        `Dismissed locally, but failed to mark as imported in source: ${dismissed.mark_imported_error}. Please mark it manually in the external system.`,
      )
    }
    await refreshStagingTable()
  } catch (err) {
    const msg = err instanceof Error ? err.message : "Failed to dismiss staged transaction"
    notifyError(msg)
  }
}

async function onRestoreRow(row: StagedTransaction): Promise<void> {
  if (row.status !== "DISMISSED") return
  try {
    await stagingStore.restoreStagedTransaction(row.id)
    notifySuccess("Transaction restored to staging")
    await refreshStagingTable()
  } catch (err) {
    const msg = err instanceof Error ? err.message : "Failed to restore transaction"
    notifyError(msg)
  }
}

async function onAcceptSelected(): Promise<void> {
  const readyIds = getSelectedReadyIds(selectedRowIds.value, stagingStore.stagedTransactions)
  if (readyIds.length === 0) return

  acceptingBatch.value = true
  try {
    const response = await stagingStore.acceptStagedTransactions(readyIds)
    selectedRowIds.value = []
    notifySuccess(`Accepted ${response.accepted_count} transaction(s) into Ledger`)
    if (response.mark_imported_errors && response.mark_imported_errors.length > 0) {
      notifyWarning(
        `Accepted into Ledger, but failed to mark as imported in external source: ${response.mark_imported_errors.join("; ")}. Please mark manually in the source system.`,
      )
    }
    await refreshStagingTable()
  } catch (err) {
    const msg = err instanceof Error ? err.message : "Failed to accept staged transactions"
    notifyError(msg)
  } finally {
    acceptingBatch.value = false
  }
}

async function onAcceptAllReady(): Promise<void> {
  const allReady = stagingStore.stagedTransactions.filter(r => r.status === "STAGED" && r.is_ready)
  if (allReady.length === 0) return

  acceptingBatch.value = true
  try {
    const allReadyIds = allReady.map(r => r.id)
    const response = await stagingStore.acceptStagedTransactions(allReadyIds)
    selectedRowIds.value = []
    notifySuccess(`Accepted ${response.accepted_count} transaction(s) into Ledger`)
    if (response.mark_imported_errors && response.mark_imported_errors.length > 0) {
      notifyWarning(
        `Accepted into Ledger, but failed to mark as imported in external source: ${response.mark_imported_errors.join("; ")}. Please mark manually in the source system.`,
      )
    }
    await refreshStagingTable()
  } catch (err) {
    const msg = err instanceof Error ? err.message : "Failed to accept staged transactions"
    notifyError(msg)
  } finally {
    acceptingBatch.value = false
  }
}

async function onAcceptBatch(): Promise<void> {
  if (selectedRowIds.value.length > 0) {
    await onAcceptSelected()
  } else {
    await onAcceptAllReady()
  }
}

onMounted(() => {
  companyStore.fetchCompanies().catch(() => {})
  stagingStore.fetchImporters().catch(() => {})
  refreshStagingTable()
})

defineExpose({
  selectedImporterId,
  selectedImporter,
  importerFile,
  runningImporter,
  isRunImporterEnabled,
  acceptedFileTypes,
  filters,
  pagination,
  columns,
  selectedRowIds,
  acceptingBatch,
  readyTransactionsToAccept,
  readyAcceptCount,
  editDialogVisible,
  selectedStagedTransaction,
  companyMap,
  quickAssignOptions,
  onSelectImporter,
  onRunImporter,
  onRequest,
  refreshStagingTable,
  applyFilters,
  resetFilters,
  isRowSelected,
  toggleRowSelection,
  onQuickAssignChange,
  openEditDialog,
  onStagedSaved,
  openReceipt,
  onUploadRowReceipt,
  onRemoveRowReceipt,
  onDismissRow,
  onRestoreRow,
  onAcceptBatch,
})
</script>

<template>
  <q-page class="q-pa-md">
    <!-- Page Header -->
    <div class="row items-center justify-between q-mb-md">
      <div>
        <div class="text-h5 text-weight-bold text-grey-9">Import &amp; Staging</div>
        <div class="text-caption text-grey-7">
          Run transaction importers, review and allocate staged items, and accept ready transactions into the Ledger.
        </div>
      </div>
      <div class="row items-center q-gutter-sm">
        <q-btn
          flat
          dense
          round
          icon="refresh"
          color="grey-7"
          aria-label="Refresh Staging"
          data-testid="btn-refresh-staging"
          :loading="stagingStore.loadingStaging || stagingStore.loadingImporters"
          @click="refreshStagingTable"
        >
          <q-tooltip>Refresh staged transactions</q-tooltip>
        </q-btn>
      </div>
    </div>

    <!-- Error Banner -->
    <q-banner v-if="stagingStore.error" rounded dense inline-actions class="bg-negative text-white q-mb-md">
      <template #avatar>
        <q-icon name="error" color="white" />
      </template>
      {{ stagingStore.error }}
      <template #action>
        <q-btn flat label="Retry" color="white" @click="refreshStagingTable" />
      </template>
    </q-banner>

    <!-- Importer Runner Panel -->
    <q-card flat bordered class="q-mb-md bg-white" data-testid="importer-runner-panel">
      <q-card-section class="q-py-md">
        <div class="text-subtitle1 text-weight-bold text-grey-9 q-mb-sm">Run Importer</div>
        <div class="row q-col-gutter-md items-start">
          <!-- Importer Select Dropdown -->
          <div class="col-12 col-md-4">
            <q-select
              :model-value="selectedImporterId"
              dense
              outlined
              clearable
              emit-value
              map-options
              label="Select Importer"
              :options="importerOptions"
              :loading="stagingStore.loadingImporters"
              data-testid="select-importer"
              @update:model-value="onSelectImporter"
            >
              <template #prepend>
                <q-icon name="cloud_upload" />
              </template>
              <template #option="scope">
                <q-item v-bind="scope.itemProps">
                  <q-item-section>
                    <q-item-label>{{ scope.opt.label }}</q-item-label>
                    <q-item-label caption>{{ scope.opt.description }}</q-item-label>
                  </q-item-section>
                </q-item>
              </template>
            </q-select>
          </div>

          <!-- Dynamic Input Control -->
          <div class="col-12 col-md-5">
            <q-file
              v-if="selectedImporter && selectedImporter.input_type === 'file'"
              v-model="importerFile"
              dense
              outlined
              clearable
              label="Import File"
              :accept="acceptedFileTypes"
              :multiple="selectedImporter?.importer_id === 'receipt_parser'"
              :use-chips="true"
              :hint="Array.isArray(importerFile) && importerFile.length > 1 ? `${importerFile.length} files selected` : undefined"
              data-testid="input-importer-file"
            >
              <template #prepend>
                <q-icon name="attach_file" />
              </template>
            </q-file>

            <div
              v-else-if="selectedImporter && selectedImporter.input_type === 'none'"
              class="row items-center q-gutter-sm"
              style="min-height: 40px"
              data-testid="badge-importer-integration-source"
            >
              <q-badge color="blue-1" text-color="primary" class="q-px-sm q-py-xs text-weight-medium">
                <q-icon name="sync" size="14px" class="q-mr-xs" />
                Pulls directly from integration source ({{ selectedImporter.source_name }})
              </q-badge>
            </div>

            <div v-else class="text-caption text-grey-6 row items-center" style="min-height: 40px">
              Select an importer above to configure its input source.
            </div>
          </div>

          <!-- Run Importer Button -->
          <div class="col-12 col-md-3 row justify-end items-center" style="min-height: 40px">
            <q-btn
              unelevated
              color="primary"
              icon="play_arrow"
              label="Run Importer"
              :loading="runningImporter"
              :disable="!isRunImporterEnabled || runningImporter"
              data-testid="btn-run-importer"
              @click="onRunImporter"
            />
          </div>
        </div>

        <!-- Selected Importer Description & Capability Chip -->
        <div v-if="selectedImporter" class="row items-center q-gutter-sm q-mt-sm">
          <span class="text-caption text-grey-7" data-testid="importer-description">
            {{ selectedImporter.description }}
          </span>
          <q-chip
            v-if="selectedImporter.supports_mark_imported"
            dense
            size="sm"
            color="teal-1"
            text-color="teal-9"
            icon="verified"
            data-testid="chip-supports-mark-imported"
          >
            {{ MARK_IMPORTED_CAPABILITY_LABEL }}
          </q-chip>
        </div>
      </q-card-section>
    </q-card>

    <!-- Filter Controls & Action Bar -->
    <q-card flat bordered class="q-mb-md bg-grey-1">
      <!-- Filters (Full Width) -->
      <q-card-section class="q-py-sm">
        <div class="row q-col-gutter-sm items-center">
          <!-- Status Filter -->
          <div class="col-12 col-sm-4 col-md-3">
            <q-select
              v-model="filters.status"
              dense
              outlined
              emit-value
              map-options
              bg-color="white"
              label="Status"
              :options="statusOptions"
              data-testid="filter-staging-status"
              @update:model-value="applyFilters"
            />
          </div>

          <!-- Source Filter -->
          <div class="col-12 col-sm-5 col-md-4">
            <q-select
              v-model="filters.source"
              dense
              outlined
              clearable
              emit-value
              map-options
              bg-color="white"
              label="Source"
              :options="SOURCE_FILTER_OPTIONS"
              data-testid="filter-staging-source"
              @update:model-value="applyFilters"
            />
          </div>

          <!-- Filter Button -->
          <div class="col-auto">
            <q-btn
              color="primary"
              unelevated
              icon="filter_list"
              label="Filter"
              data-testid="btn-apply-staging-filters"
              @click="applyFilters"
            />
          </div>
        </div>
      </q-card-section>

      <q-separator />

      <!-- Action Toolbar (Below Filters, Oriented Horizontally, Always Visible & Disabled When Inapplicable) -->
      <q-card-section class="q-py-sm" data-testid="batch-action-bar">
        <div class="row items-center q-gutter-sm">
          <q-chip dense color="blue-1" text-color="primary" class="text-weight-bold" data-testid="chip-selected-count">
            {{ selectedRowIds.length }} selected
          </q-chip>

          <q-space />

          <q-btn
            flat
            color="negative"
            icon="delete_outline"
            :label="`Dismiss (${selectedRowIds.length})`"
            :disable="selectedRowIds.length === 0"
            data-testid="btn-dismiss-selected"
            @click="onBulkDismiss"
          />

          <q-btn
            unelevated
            color="primary"
            icon="tune"
            :label="`Allocate (${selectedRowIds.length})`"
            :disable="selectedRowIds.length === 0"
            data-testid="btn-bulk-allocate"
            @click="openBulkAllocateDialog"
          />

          <q-btn
            unelevated
            color="positive"
            icon="done_all"
            :label="`Accept (${selectedReadyCount} ready)`"
            :loading="acceptingBatch"
            :disable="selectedReadyCount === 0 || acceptingBatch"
            data-testid="btn-accept-selected"
            @click="onAcceptSelected"
          >
            <q-tooltip v-if="selectedReadyCount === 0"> None of the selected transactions are ready to accept </q-tooltip>
          </q-btn>
        </div>
      </q-card-section>
    </q-card>

    <!-- Staging Review Table -->
    <q-table
      :rows="stagingStore.stagedTransactions"
      :columns="columns"
      row-key="id"
      :loading="stagingStore.loadingStaging"
      v-model:pagination="pagination"
      :rows-per-page-options="[20, 50, 100]"
      flat
      bordered
      class="shadow-1 staging-table"
      data-testid="table-staging"
      @request="onRequest"
    >
      <!-- Master Selection Checkbox in Header -->
      <template #header-cell-select="props">
        <q-th :props="props" align="center">
          <q-checkbox
            :model-value="isHeaderChecked"
            :indeterminate="isHeaderIndeterminate"
            dense
            color="primary"
            data-testid="checkbox-select-all"
            :disable="visibleStagedRows.length === 0"
            @update:model-value="toggleAllVisibleRows"
          />
        </q-th>
      </template>

      <!-- Selection Checkbox Column -->
      <template #body-cell-select="props">
        <q-td :props="props" align="center">
          <q-checkbox
            :model-value="isRowSelected(props.row.id)"
            dense
            color="primary"
            :data-testid="`checkbox-select-${props.row.id}`"
            :disable="props.row.status !== 'STAGED'"
            @update:model-value="(val: boolean) => toggleRowSelection(props.row, val)"
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
          <div class="text-weight-medium">
            <span v-if="props.row.description">{{ props.row.description }}</span>
            <span v-else class="text-italic text-grey-6">Unlabeled transaction</span>
          </div>
          <div class="row items-center q-gutter-xs text-caption no-wrap">
            <q-chip dense size="xs" color="blue-1" text-color="primary" class="text-weight-bold">
              {{ props.row.source }}
            </q-chip>
            <q-btn
              v-if="props.row.url"
              flat
              round
              dense
              size="xs"
              icon="open_in_new"
              color="primary"
              :href="props.row.url"
              target="_blank"
              rel="noopener noreferrer"
              data-testid="btn-open-url"
            >
              <q-tooltip>Open URL</q-tooltip>
            </q-btn>
          </div>
        </q-td>
      </template>

      <!-- Amount Column -->
      <template #body-cell-total_amount="props">
        <q-td :props="props" align="right">
          <span :class="Number(props.row.total_amount) < 0 ? 'text-negative text-weight-bold' : 'text-weight-bold'">
            {{ formatStagedAmount(props.row.total_amount) }}
          </span>
        </q-td>
      </template>

      <!-- Allocation Status / Summary Column -->
      <template #body-cell-allocations="props">
        <q-td :props="props">
          <!-- Non-STAGED rows (Accepted / Dismissed): Read-only summary badge -->
          <div v-if="props.row.status !== 'STAGED'" class="row items-center no-wrap q-gutter-xs">
            <q-badge
              :color="getStagedAllocationSummary(props.row, companyMap).color"
              :text-color="getStagedAllocationSummary(props.row, companyMap).textColor"
              class="q-px-sm q-py-xs text-weight-bold ellipsis"
              style="max-width: 220px"
              data-testid="badge-staged-allocation"
            >
              {{ getStagedAllocationSummary(props.row, companyMap).label }}
              <q-tooltip>{{ getStagedAllocationSummary(props.row, companyMap).label }}</q-tooltip>
            </q-badge>
          </div>

          <!-- STAGED rows -->
          <div v-else class="row items-center no-wrap q-gutter-xs">
            <!-- Multi-Split Allocation: Compact chip + Split button -->
            <template v-if="props.row.allocations && props.row.allocations.length > 1">
              <q-chip
                dense
                clickable
                color="teal-1"
                text-color="teal-9"
                icon="call_split"
                class="text-weight-bold cursor-pointer"
                data-testid="badge-staged-allocation"
                @click="openEditDialog(props.row)"
              >
                {{ props.row.allocations.length }} splits
                <q-tooltip> {{ getStagedAllocationSummary(props.row, companyMap).label }} (Click to edit) </q-tooltip>
              </q-chip>
              <q-btn
                flat
                round
                dense
                size="sm"
                color="primary"
                icon="call_split"
                data-testid="btn-split-allocations"
                @click="openEditDialog(props.row)"
              >
                <q-tooltip>Split Allocations</q-tooltip>
              </q-btn>
            </template>

            <!-- Single Allocation or Unallocated -->
            <template v-else>
              <!-- Quick Assign Selector -->
              <q-select
                :model-value="getQuickAssignValue(props.row)"
                dense
                outlined
                clearable
                emit-value
                map-options
                options-dense
                :style="props.row.is_ready ? 'width: 195px' : 'width: 145px'"
                placeholder="Quick allocate..."
                :options="quickAssignOptions"
                :data-testid="`select-quick-assign-${props.row.id}`"
                @update:model-value="(val: string | null) => onQuickAssignChange(props.row, val)"
              >
                <template v-if="props.row.is_ready" #prepend>
                  <q-icon name="check_circle" color="positive" size="16px">
                    <q-tooltip>Ready to accept</q-tooltip>
                  </q-icon>
                </template>
              </q-select>

              <q-btn
                flat
                round
                dense
                size="sm"
                color="primary"
                icon="call_split"
                data-testid="btn-split-allocations"
                @click="openEditDialog(props.row)"
              >
                <q-tooltip>Split Allocations</q-tooltip>
              </q-btn>
            </template>
          </div>
        </q-td>
      </template>

      <!-- Receipt Column -->
      <template #body-cell-receipt="props">
        <q-td :props="props" align="center">
          <div class="row items-center justify-center no-wrap q-gutter-xs">
            <template v-if="props.row.receipt_file_path">
              <q-btn
                flat
                round
                dense
                size="sm"
                icon="receipt"
                color="primary"
                aria-label="View Receipt"
                data-testid="btn-view-staged-receipt"
                @click="openReceipt(props.row.receipt_file_path)"
              >
                <q-tooltip>View Receipt</q-tooltip>
              </q-btn>
              <template v-if="props.row.status === 'STAGED'">
                <q-btn
                  flat
                  round
                  dense
                  size="sm"
                  icon="upload_file"
                  color="grey-7"
                  aria-label="Replace Receipt"
                  data-testid="btn-replace-staged-receipt"
                  @click="openEditDialog(props.row)"
                >
                  <q-tooltip>Replace Receipt</q-tooltip>
                </q-btn>
                <q-btn
                  flat
                  round
                  dense
                  size="sm"
                  icon="delete_outline"
                  color="negative"
                  aria-label="Remove Receipt"
                  data-testid="btn-remove-staged-receipt"
                  @click="onRemoveRowReceipt(props.row)"
                >
                  <q-tooltip>Remove Receipt</q-tooltip>
                </q-btn>
              </template>
            </template>
            <template v-else-if="props.row.status === 'STAGED'">
              <q-btn
                flat
                round
                dense
                size="sm"
                icon="attach_file"
                color="grey-8"
                data-testid="btn-attach-staged-receipt"
                @click="openEditDialog(props.row)"
              >
                <q-tooltip>Attach Receipt</q-tooltip>
              </q-btn>
            </template>
            <span v-else class="text-grey-5">—</span>
          </div>
        </q-td>
      </template>

      <!-- Actions Column -->
      <template #body-cell-actions="props">
        <q-td :props="props" align="right">
          <div class="row items-center justify-end q-gutter-xs no-wrap">
            <template v-if="props.row.status === 'STAGED'">
              <q-btn
                flat
                round
                dense
                size="sm"
                color="primary"
                icon="edit"
                data-testid="btn-action-edit"
                @click="openEditDialog(props.row)"
              >
                <q-tooltip>Edit Transaction</q-tooltip>
              </q-btn>
              <q-btn
                flat
                round
                dense
                size="sm"
                color="negative"
                icon="block"
                data-testid="btn-action-dismiss"
                @click="onDismissRow(props.row)"
              >
                <q-tooltip>Dismiss Transaction</q-tooltip>
              </q-btn>
            </template>
            <template v-else-if="props.row.status === 'DISMISSED'">
              <q-btn
                flat
                round
                dense
                size="sm"
                color="primary"
                icon="restore"
                data-testid="btn-action-restore"
                @click="onRestoreRow(props.row)"
              >
                <q-tooltip>Restore Transaction</q-tooltip>
              </q-btn>
            </template>
          </div>
        </q-td>
      </template>

      <!-- Empty State -->
      <template #no-data>
        <div class="full-width row flex-center text-grey-7 q-gutter-sm q-pa-lg">
          <q-icon size="2em" name="cloud_upload" />
          <span>No staged transactions found for the current filters.</span>
        </div>
      </template>
    </q-table>

    <!-- Staged Transaction & Allocation Editor Dialog -->
    <StagedTransactionEditDialog v-model="editDialogVisible" :staged-transaction="selectedStagedTransaction" @saved="onStagedSaved" />

    <!-- Bulk Allocation Dialog -->
    <BulkAllocateDialog
      v-model="bulkAllocateDialogVisible"
      :selected-transactions="selectedTransactions"
      @applied="onBulkAllocateApplied"
    />
  </q-page>
</template>
