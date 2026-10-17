<script setup lang="ts">
import { computed, ref, watch } from "vue"
import { Notify, useQuasar, type QForm } from "quasar"
import { useCompanyStore } from "../stores/companies"
import { useTransactionStore } from "../stores/transactions"
import type { Transaction } from "../types/transaction"
import {
  amountRules,
  calculateSplitRemainder,
  dateRules,
  descriptionRules,
  formatAmount,
  getTodayDateString,
  splitAmountRules,
  splitCompanyRules,
} from "../views/manualEntry"
import {
  addEditSplit,
  canSaveTransactionEdit,
  createTransactionEditState,
  getEditLockState,
  hasEffectiveReceipt,
  hasReceiptChanges,
  markReceiptForRemoval,
  PERSONAL_SPLIT_TOOLTIP,
  prepareTransactionEditPayload,
  removeEditSplit,
  stageReceiptFile,
  syncSingleSplitAmount,
  togglePersonalExpense,
  UNLOCK_WARNING_MESSAGE,
  type TransactionEditFormState,
} from "./transactionEdit"

const props = defineProps<{
  modelValue: boolean
  transaction: Transaction | null
}>()

const emit = defineEmits<{
  (e: "update:modelValue", val: boolean): void
  (e: "saved", tx: Transaction): void
}>()

const companyStore = useCompanyStore()
const transactionStore = useTransactionStore()
const formRef = ref<QForm | null>(null)
const saving = ref<boolean>(false)
const errorMessage = ref<string>("")

// Unlock confirmation dialog state for per-allocation unlocking
const unlockDialogVisible = ref<boolean>(false)
const pendingUnlockIndex = ref<number | null>(null)

const form = ref<TransactionEditFormState>({
  date: "",
  description: "",
  total_amount: "",
  is_personal: false,
  existing_receipt_path: null,
  staged_receipt_file: null,
  remove_receipt: false,
  splits: [],
})

const isOpen = computed({
  get: () => props.modelValue,
  set: (val: boolean) => emit("update:modelValue", val),
})

const companyOptions = computed(() =>
  companyStore.companies.map(c => ({
    label: c.name,
    value: c.id,
  })),
)

const lockState = computed(() => getEditLockState(form.value))
const splitRemainder = computed(() => calculateSplitRemainder(form.value.total_amount, form.value.splits))
const isBalanced = computed(() => splitRemainder.value.isBalanced)
const hasReceipt = computed(() => hasEffectiveReceipt(form.value))
const receiptModified = computed(() => hasReceiptChanges(form.value))
const canSave = computed(() => canSaveTransactionEdit(form.value))

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

watch(
  () => [props.modelValue, props.transaction] as const,
  ([visible, tx]) => {
    if (visible && tx) {
      errorMessage.value = ""
      unlockDialogVisible.value = false
      pendingUnlockIndex.value = null
      const defaultCompId = companyStore.companies[0]?.id ?? null
      form.value = createTransactionEditState(tx, defaultCompId)
    }
  },
  { immediate: true },
)

watch(
  () => form.value.total_amount,
  () => {
    syncSingleSplitAmount(form.value)
  },
)

function onTotalAmountBlur(): void {
  if (form.value.total_amount) {
    form.value.total_amount = formatAmount(form.value.total_amount)
    syncSingleSplitAmount(form.value)
  }
}

function onSplitAmountBlur(index: number): void {
  const split = form.value.splits[index]
  if (split && split.amount) {
    split.amount = formatAmount(split.amount)
  }
}

function onPersonalToggle(val: boolean): void {
  const defaultCompId = companyStore.companies[0]?.id ?? null
  togglePersonalExpense(form.value, val, defaultCompId)
}

function onAddSplit(): void {
  addEditSplit(form.value, null)
}

function onRemoveSplit(index: number): void {
  removeEditSplit(form.value, index)
}

function onReceiptSelected(file: File | null): void {
  stageReceiptFile(form.value, file)
}

function onRemoveReceipt(): void {
  markReceiptForRemoval(form.value)
}

async function onViewReceipt(): Promise<void> {
  try {
    if (form.value.staged_receipt_file) {
      const blobUrl = URL.createObjectURL(form.value.staged_receipt_file)
      if (typeof window !== "undefined" && typeof window.open === "function") {
        window.open(blobUrl, "_blank")
      } else if (typeof globalThis.open === "function") {
        globalThis.open(blobUrl, "_blank")
      }
      return
    }
    if (form.value.existing_receipt_path) {
      await transactionStore.openReceiptInNewTab(form.value.existing_receipt_path)
    }
  } catch (err) {
    const msg = err instanceof Error ? err.message : "Failed to open receipt"
    errorMessage.value = msg
    notifyError(msg)
  }
}

async function onToggleSplitLock(index: number): Promise<void> {
  const split = form.value.splits[index]
  if (!split) return

  if (split.is_locked) {
    pendingUnlockIndex.value = index
    unlockDialogVisible.value = true
  } else {
    if (split.id) {
      try {
        const updatedAlloc = await transactionStore.lockAllocation(split.id, true)
        split.is_locked = updatedAlloc.is_locked
      } catch (err) {
        const msg = err instanceof Error ? err.message : "Failed to lock allocation"
        errorMessage.value = msg
        notifyError(msg)
      }
    } else {
      split.is_locked = true
    }
  }
}

async function confirmUnlockSplit(): Promise<void> {
  const index = pendingUnlockIndex.value
  unlockDialogVisible.value = false
  pendingUnlockIndex.value = null
  if (index === null) return

  const split = form.value.splits[index]
  if (!split) return

  if (split.id) {
    try {
      const updatedAlloc = await transactionStore.lockAllocation(split.id, false)
      split.is_locked = updatedAlloc.is_locked
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Failed to unlock allocation"
      errorMessage.value = msg
      notifyError(msg)
    }
  } else {
    split.is_locked = false
  }
}

function cancelUnlockSplit(): void {
  unlockDialogVisible.value = false
  pendingUnlockIndex.value = null
}

function handleDateKeydown(e: KeyboardEvent): void {
  if ((e.ctrlKey || e.metaKey) && (e.key === ";" || e.code === "Semicolon")) {
    e.preventDefault()
    e.stopPropagation()
    if (!lockState.value.isDateDisabled) {
      form.value.date = getTodayDateString()
    }
  }
}

async function onSubmit(): Promise<void> {
  if (!props.transaction || saving.value) return
  if (!canSave.value) return

  if (!lockState.value.isFullyLocked && formRef.value) {
    const valid = await formRef.value.validate()
    if (!valid) return
  }

  errorMessage.value = ""
  saving.value = true

  try {
    const { payload } = prepareTransactionEditPayload(form.value)
    const updated = await transactionStore.updateTransaction(props.transaction.id, payload)
    notifySuccess("Transaction updated successfully")
    emit("saved", updated)
    isOpen.value = false
  } catch (err) {
    const msg = err instanceof Error ? err.message : "Failed to update transaction"
    errorMessage.value = msg
    notifyError(msg)
  } finally {
    saving.value = false
  }
}

defineExpose({
  form,
  lockState,
  splitRemainder,
  isBalanced,
  hasReceipt,
  receiptModified,
  canSave,
  saving,
  errorMessage,
  unlockDialogVisible,
  pendingUnlockIndex,
  onTotalAmountBlur,
  onSplitAmountBlur,
  onPersonalToggle,
  onAddSplit,
  onRemoveSplit,
  onReceiptSelected,
  onRemoveReceipt,
  onViewReceipt,
  onToggleSplitLock,
  confirmUnlockSplit,
  cancelUnlockSplit,
  onSubmit,
})
</script>

<template>
  <q-dialog v-model="isOpen" persistent>
    <q-card style="min-width: 680px; max-width: 820px; width: 100%" data-testid="transaction-edit-dialog">
      <!-- Dialog Header -->
      <q-card-section class="row items-center q-pb-none">
        <div class="row items-center q-gutter-x-sm">
          <div class="text-h6 text-weight-bold">Edit Transaction</div>
          <q-badge v-if="lockState.isFullyLocked" color="amber-9" text-color="white" data-testid="dialog-badge-fully-locked">
            <q-icon name="lock" size="12px" class="q-mr-xs" />
            Fully Locked
          </q-badge>
          <q-badge v-else-if="lockState.isPartiallyLocked" color="orange-7" text-color="white" data-testid="dialog-badge-partially-locked">
            <q-icon name="lock_open" size="12px" class="q-mr-xs" />
            Partially Locked
          </q-badge>
        </div>
        <q-space />
        <q-btn icon="close" flat round dense v-close-popup :disable="saving" data-testid="btn-close-edit-dialog" />
      </q-card-section>

      <q-card-section class="q-pt-sm">
        <div class="text-caption text-grey-7 q-mb-sm">
          Update transaction details, manage receipt attachments, and adjust business or personal allocations.
        </div>

        <!-- Lock Notice Banner -->
        <q-banner v-if="lockState.isFullyLocked" rounded dense class="bg-amber-1 text-amber-10 q-mb-sm" data-testid="banner-fully-locked">
          <template #avatar>
            <q-icon name="lock" color="amber-9" />
          </template>
          All allocations are locked. Unlock an allocation below to edit transaction details or splits. Receipts can still be uploaded,
          replaced, or removed.
        </q-banner>
        <q-banner
          v-else-if="lockState.isPartiallyLocked"
          rounded
          dense
          class="bg-orange-1 text-orange-10 q-mb-sm"
          data-testid="banner-partially-locked"
        >
          <template #avatar>
            <q-icon name="info" color="orange-8" />
          </template>
          This transaction is partially locked. Date, description, and locked splits are read-only while unlocked splits remain editable.
        </q-banner>

        <!-- Error Banner -->
        <q-banner v-if="errorMessage" rounded dense inline-actions class="bg-negative text-white q-mb-sm" data-testid="banner-edit-error">
          <template #avatar>
            <q-icon name="error" color="white" />
          </template>
          {{ errorMessage }}
          <template #action>
            <q-btn flat round dense icon="close" size="sm" @click="errorMessage = ''" />
          </template>
        </q-banner>

        <q-form ref="formRef" @submit.prevent="onSubmit">
          <!-- Section 1: Transaction Metadata Controls -->
          <div class="row q-col-gutter-md q-mb-xs">
            <div class="col-12 col-sm-6">
              <q-input
                v-model="form.date"
                outlined
                dense
                lazy-rules="ondemand"
                label="Date *"
                placeholder="YYYY-MM-DD"
                mask="####-##-##"
                :disable="lockState.isDateDisabled || saving"
                :rules="dateRules"
                data-testid="edit-input-date"
                @keydown="handleDateKeydown"
              >
                <template #append>
                  <q-icon v-if="!lockState.isDateDisabled" name="event" class="cursor-pointer" data-testid="edit-icon-date-picker">
                    <q-popup-proxy cover transition-show="scale" transition-hide="scale">
                      <q-date v-model="form.date" mask="YYYY-MM-DD" :today-btn="true" data-testid="edit-date-picker">
                        <div class="row items-center justify-end">
                          <q-btn v-close-popup label="Close" color="primary" flat />
                        </div>
                      </q-date>
                    </q-popup-proxy>
                  </q-icon>
                </template>
              </q-input>
            </div>

            <div class="col-12 col-sm-6">
              <q-input
                v-model="form.total_amount"
                type="number"
                step="0.01"
                outlined
                dense
                lazy-rules="ondemand"
                label="Total Amount *"
                placeholder="0.00"
                :disable="lockState.isTotalAmountDisabled || saving"
                :rules="amountRules"
                data-testid="edit-input-total-amount"
                @blur="onTotalAmountBlur"
              >
                <template #prepend>
                  <span class="text-subtitle2 text-grey-7">$</span>
                </template>
              </q-input>
            </div>
          </div>

          <div class="row q-col-gutter-md q-mb-sm">
            <div class="col-12">
              <q-input
                v-model="form.description"
                outlined
                dense
                lazy-rules="ondemand"
                label="Description / Payee *"
                placeholder="e.g. Acme Supplies, Vendor memo..."
                :disable="lockState.isDescriptionDisabled || saving"
                :rules="descriptionRules"
                data-testid="edit-input-description"
              >
                <template #prepend>
                  <q-icon name="edit_note" />
                </template>
              </q-input>
            </div>
          </div>

          <q-separator class="q-my-sm" />

          <!-- Section 2: Receipt Management (Always Editable) -->
          <div class="q-my-sm">
            <div class="text-subtitle2 text-weight-bold text-grey-9 q-mb-xs">Receipt Attachment</div>

            <div v-if="hasReceipt" class="row items-center q-col-gutter-sm" data-testid="receipt-attached-controls">
              <div class="col-auto">
                <q-btn
                  outline
                  dense
                  color="primary"
                  icon="open_in_new"
                  label="View Receipt"
                  data-testid="btn-view-receipt"
                  :disable="saving"
                  @click="onViewReceipt"
                />
              </div>
              <div class="col">
                <q-file
                  :model-value="form.staged_receipt_file"
                  outlined
                  dense
                  clearable
                  label="Replace Receipt (.pdf, .png, .jpg)"
                  accept=".pdf,.png,.jpg,.jpeg,application/pdf,image/png,image/jpeg"
                  :disable="saving"
                  data-testid="input-replace-receipt"
                  @update:model-value="onReceiptSelected"
                >
                  <template #prepend>
                    <q-icon name="upload_file" />
                  </template>
                </q-file>
              </div>
              <div class="col-auto">
                <q-btn
                  flat
                  dense
                  color="negative"
                  icon="delete_outline"
                  label="Remove Receipt"
                  data-testid="btn-remove-receipt"
                  :disable="saving"
                  @click="onRemoveReceipt"
                />
              </div>
            </div>

            <div v-else data-testid="receipt-empty-controls">
              <q-file
                :model-value="form.staged_receipt_file"
                outlined
                dense
                clearable
                label="Upload Receipt (.pdf, .png, .jpg)"
                accept=".pdf,.png,.jpg,.jpeg,application/pdf,image/png,image/jpeg"
                :disable="saving"
                data-testid="input-upload-receipt"
                @update:model-value="onReceiptSelected"
              >
                <template #prepend>
                  <q-icon name="attach_file" />
                </template>
              </q-file>
            </div>
          </div>

          <q-separator class="q-my-sm" />

          <!-- Section 3: Personal vs. Business & Split Allocation Controls -->
          <div class="q-my-sm">
            <div class="row items-center justify-between no-wrap q-mb-xs">
              <div>
                <div class="text-subtitle2 text-weight-bold text-grey-9">Allocations</div>
                <div class="text-caption text-grey-7">Split across businesses or mark as a personal expense.</div>
              </div>

              <div class="row items-center no-wrap q-gutter-x-sm">
                <!-- Real-Time Balance Indicator -->
                <q-chip
                  :color="isBalanced ? 'positive' : 'warning'"
                  text-color="white"
                  :icon="isBalanced ? 'check_circle' : 'warning'"
                  dense
                  class="q-ma-none"
                  data-testid="edit-split-balance-indicator"
                >
                  <template v-if="!form.total_amount || isNaN(Number(form.total_amount)) || Number(form.total_amount) === 0">
                    Enter total amount
                  </template>
                  <template v-else-if="isBalanced"> Balanced ($0.00 remaining) </template>
                  <template v-else-if="splitRemainder.remainderCents > 0">
                    Unallocated: ${{ splitRemainder.remainderFormatted }} remaining
                  </template>
                  <template v-else-if="splitRemainder.remainderCents < 0">
                    Overallocated: ${{ Math.abs(Number(splitRemainder.remainderFormatted)).toFixed(2) }}
                  </template>
                  <template v-else> Enter split amounts </template>
                </q-chip>

                <!-- Add Split Button -->
                <q-btn
                  flat
                  dense
                  no-wrap
                  color="primary"
                  icon="add"
                  label="Add Split"
                  :disable="lockState.isAddSplitDisabled || saving"
                  data-testid="edit-btn-add-split"
                  @click="onAddSplit"
                />
              </div>
            </div>

            <!-- Personal Expense Toggle Row -->
            <div class="row items-center q-gutter-x-sm q-mb-sm">
              <div>
                <q-toggle
                  :model-value="form.is_personal"
                  dense
                  label="Personal Expense"
                  color="primary"
                  :disable="lockState.isPersonalToggleDisabled || saving"
                  data-testid="toggle-is-personal"
                  @update:model-value="onPersonalToggle"
                />
                <q-tooltip v-if="form.splits.length > 1" data-testid="tooltip-personal-disabled">
                  {{ PERSONAL_SPLIT_TOOLTIP }}
                </q-tooltip>
              </div>
              <span v-if="form.splits.length > 1" class="text-caption text-grey-7" data-testid="personal-split-hint">
                ({{ PERSONAL_SPLIT_TOOLTIP }})
              </span>
            </div>

            <!-- Split Rows -->
            <div
              v-for="(split, index) in form.splits"
              :key="split.id || index"
              class="row q-col-gutter-sm items-start q-mb-xs"
              :data-testid="`edit-split-row-${index}`"
            >
              <!-- Company Select Dropdown -->
              <div class="col-12 col-sm-5">
                <q-select
                  v-model="split.company_id"
                  outlined
                  dense
                  emit-value
                  map-options
                  lazy-rules="ondemand"
                  :label="form.is_personal ? 'Personal Expense (No Company)' : 'Company *'"
                  :options="companyOptions"
                  :disable="form.is_personal || split.is_locked || saving"
                  :rules="form.is_personal ? [] : splitCompanyRules"
                  :data-testid="`edit-split-company-${index}`"
                >
                  <template #prepend>
                    <q-icon :name="form.is_personal ? 'person' : 'business'" />
                  </template>
                </q-select>
              </div>

              <!-- Split Amount Input -->
              <div class="col-8 col-sm-4">
                <q-input
                  v-model="split.amount"
                  type="number"
                  step="0.01"
                  outlined
                  dense
                  lazy-rules="ondemand"
                  :readonly="form.splits.length === 1 || split.is_locked"
                  :disable="split.is_locked || saving"
                  :label="form.splits.length === 1 ? 'Amount (100%) *' : 'Split Amount *'"
                  placeholder="0.00"
                  :rules="splitAmountRules"
                  :data-testid="`edit-split-amount-${index}`"
                  @blur="onSplitAmountBlur(index)"
                >
                  <template #prepend>
                    <span class="text-subtitle2 text-grey-7">$</span>
                  </template>
                </q-input>
              </div>

              <!-- Allocation Lock Indicator & Toggle -->
              <div class="col-2 col-sm-2 flex items-center justify-center q-pt-xs">
                <q-btn
                  flat
                  dense
                  :color="split.is_locked ? 'amber-9' : 'grey-7'"
                  :icon="split.is_locked ? 'lock' : 'lock_open'"
                  :label="split.is_locked ? 'Locked' : 'Unlocked'"
                  size="sm"
                  :disable="saving"
                  :data-testid="`btn-toggle-split-lock-${index}`"
                  @click="onToggleSplitLock(index)"
                >
                  <q-tooltip>
                    {{ split.is_locked ? "Click to unlock this allocation" : "Click to lock this allocation" }}
                  </q-tooltip>
                </q-btn>
              </div>

              <!-- Remove Split Button -->
              <div class="col-2 col-sm-1 flex justify-center q-pt-xs">
                <q-btn
                  flat
                  round
                  dense
                  color="negative"
                  icon="delete"
                  :disable="form.splits.length <= 1 || split.is_locked || saving"
                  :data-testid="`edit-btn-remove-split-${index}`"
                  @click="onRemoveSplit(index)"
                >
                  <q-tooltip v-if="split.is_locked">Locked splits cannot be removed</q-tooltip>
                  <q-tooltip v-else-if="form.splits.length > 1">Remove split</q-tooltip>
                  <q-tooltip v-else>At least one split is required</q-tooltip>
                </q-btn>
              </div>
            </div>
          </div>

          <q-card-actions align="right" class="q-pt-md q-px-none">
            <q-btn flat label="Cancel" color="grey-7" v-close-popup :disable="saving" data-testid="btn-cancel-edit" />
            <q-btn
              type="submit"
              label="Save Changes"
              color="primary"
              unelevated
              :loading="saving"
              :disable="!canSave || saving"
              data-testid="btn-save-edit"
            />
          </q-card-actions>
        </q-form>
      </q-card-section>
    </q-card>
  </q-dialog>

  <!-- Per-Allocation Unlock Confirmation Warning Dialog -->
  <q-dialog v-model="unlockDialogVisible" persistent>
    <q-card style="max-width: 440px; width: 100%" data-testid="dialog-unlock-split-warning">
      <q-card-section class="row items-center">
        <q-avatar icon="warning" color="amber-9" text-color="white" class="q-mr-md" />
        <div class="text-h6 text-weight-bold">Unlock Allocation</div>
      </q-card-section>

      <q-card-section class="q-pt-none" data-testid="unlock-split-warning-message">
        {{ UNLOCK_WARNING_MESSAGE }}
      </q-card-section>

      <q-card-actions align="right">
        <q-btn flat label="Cancel" color="grey-7" data-testid="btn-cancel-unlock-split" @click="cancelUnlockSplit" />
        <q-btn unelevated label="Unlock" color="amber-9" data-testid="btn-confirm-unlock-split" @click="confirmUnlockSplit" />
      </q-card-actions>
    </q-card>
  </q-dialog>
</template>
