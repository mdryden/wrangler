<script setup lang="ts">
import { computed, ref, watch } from "vue"
import { Notify, useQuasar, type QForm } from "quasar"
import { useCompanyStore } from "../stores/companies"
import { useStagingStore } from "../stores/staging"
import { useTransactionStore } from "../stores/transactions"
import type { StagedTransaction } from "../types/staging"
import type { ReceiptParseResponse } from "../types/transaction"
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
import { PERSONAL_SPLIT_TOOLTIP } from "./transactionEdit"
import {
  acceptAiSuggestion,
  addStagedEditSplit,
  canSaveStagedTransactionEdit,
  clearStagedAllocations,
  clearStagedReceipt,
  computeAiSuggestions,
  createInitialAiSuggestionsState,
  createStagedTransactionEditState,
  dismissAiSuggestion,
  hasEffectiveStagedReceipt,
  markStagedReceiptForRemoval,
  prepareStagedTransactionEditPayload,
  removeStagedEditSplit,
  stageStagedReceiptFile,
  syncSingleStagedSplitAmount,
  toggleStagedPersonalExpense,
  type StagedAiSuggestionsState,
  type StagedTransactionEditFormState,
} from "./stagedTransactionEdit"

const props = defineProps<{
  modelValue: boolean
  stagedTransaction: StagedTransaction | null
}>()

const emit = defineEmits<{
  (e: "update:modelValue", val: boolean): void
  (e: "saved", staged: StagedTransaction): void
}>()

const companyStore = useCompanyStore()
const stagingStore = useStagingStore()
const transactionStore = useTransactionStore()
const formRef = ref<QForm | null>(null)
const saving = ref<boolean>(false)
const isParsingReceipt = ref<boolean>(false)
const errorMessage = ref<string>("")
const aiSuggestions = ref<StagedAiSuggestionsState>(createInitialAiSuggestionsState())

const form = ref<StagedTransactionEditFormState>({
  date: "",
  description: "",
  total_amount: "",
  url: "",
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

const splitRemainder = computed(() => calculateSplitRemainder(form.value.total_amount, form.value.splits))
const isBalanced = computed(() => splitRemainder.value.isBalanced)
const hasReceipt = computed(() => hasEffectiveStagedReceipt(form.value))
const canSave = computed(() => canSaveStagedTransactionEdit(form.value))

const displayReceiptName = computed(() => {
  if (form.value.staged_receipt_file) {
    return form.value.staged_receipt_file.name
  }
  if (form.value.existing_receipt_path && !form.value.remove_receipt) {
    const parts = form.value.existing_receipt_path.split(/[/\\]/)
    return parts[parts.length - 1] || form.value.existing_receipt_path
  }
  return ""
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

watch(
  () => [props.modelValue, props.stagedTransaction] as const,
  ([visible, staged]) => {
    if (visible && staged) {
      errorMessage.value = ""
      form.value = createStagedTransactionEditState(staged)
      aiSuggestions.value = createInitialAiSuggestionsState()
    } else {
      aiSuggestions.value = createInitialAiSuggestionsState()
    }
  },
  { immediate: true },
)

watch(
  () => form.value.total_amount,
  () => {
    syncSingleStagedSplitAmount(form.value)
  },
)

function onTotalAmountBlur(): void {
  if (form.value.total_amount) {
    form.value.total_amount = formatAmount(form.value.total_amount)
    syncSingleStagedSplitAmount(form.value)
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
  toggleStagedPersonalExpense(form.value, val, defaultCompId)
  if (val) {
    formRef.value?.resetValidation()
  }
}

function onAddSplit(): void {
  addStagedEditSplit(form.value, null)
}

function onRemoveSplit(index: number): void {
  removeStagedEditSplit(form.value, index)
}

function onClearAllocations(): void {
  clearStagedAllocations(form.value)
}

function onReceiptSelected(file: File | null): void {
  stageStagedReceiptFile(form.value, file)
}

function onClearReceipt(): void {
  clearStagedReceipt(form.value, aiSuggestions.value)
}

function onRemoveReceipt(): void {
  onClearReceipt()
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
    if (form.value.existing_receipt_path && !form.value.remove_receipt) {
      await transactionStore.openReceiptInNewTab(form.value.existing_receipt_path)
    }
  } catch (err) {
    const msg = err instanceof Error ? err.message : "Failed to open receipt"
    errorMessage.value = msg
    notifyError(msg)
  }
}

async function onScanReceipt(): Promise<void> {
  if (!hasReceipt.value || saving.value || isParsingReceipt.value) return
  isParsingReceipt.value = true
  errorMessage.value = ""
  try {
    let parseResult: ReceiptParseResponse
    if (form.value.staged_receipt_file) {
      parseResult = await transactionStore.parseReceipt(form.value.staged_receipt_file)
    } else if (form.value.existing_receipt_path && !form.value.remove_receipt && props.stagedTransaction) {
      parseResult = await stagingStore.parseStagedReceipt(props.stagedTransaction.id)
    } else {
      return
    }
    aiSuggestions.value = computeAiSuggestions(parseResult, form.value)
    notifySuccess("Receipt parsed with AI")
  } catch (err) {
    const msg = err instanceof Error ? err.message : "Failed to parse receipt with AI"
    errorMessage.value = msg
    notifyError(msg)
  } finally {
    isParsingReceipt.value = false
  }
}

function onAcceptSuggestion(field: "date" | "total_amount" | "description"): void {
  acceptAiSuggestion(form.value, aiSuggestions.value, field)
}

function onDismissSuggestion(field: "date" | "total_amount" | "description"): void {
  dismissAiSuggestion(aiSuggestions.value, field)
}

function handleDateKeydown(e: KeyboardEvent): void {
  if ((e.ctrlKey || e.metaKey) && (e.key === ";" || e.code === "Semicolon")) {
    e.preventDefault()
    e.stopPropagation()
    form.value.date = getTodayDateString()
  }
}

async function onSubmit(): Promise<void> {
  if (!props.stagedTransaction || saving.value) return
  if (!canSave.value) return

  if (formRef.value) {
    const valid = await formRef.value.validate()
    if (!valid) return
  }

  errorMessage.value = ""
  saving.value = true

  try {
    const { payload, stagedReceiptFile } = prepareStagedTransactionEditPayload(form.value)
    const updated = await stagingStore.updateStagedTransaction(props.stagedTransaction.id, payload, stagedReceiptFile)
    notifySuccess("Staged transaction updated")
    emit("saved", updated)
    isOpen.value = false
  } catch (err) {
    const msg = err instanceof Error ? err.message : "Failed to update staged transaction"
    errorMessage.value = msg
    notifyError(msg)
  } finally {
    saving.value = false
  }
}

defineExpose({
  form,
  splitRemainder,
  isBalanced,
  hasReceipt,
  canSave,
  saving,
  isParsingReceipt,
  aiSuggestions,
  errorMessage,
  onTotalAmountBlur,
  onSplitAmountBlur,
  onPersonalToggle,
  onAddSplit,
  onRemoveSplit,
  onClearAllocations,
  onReceiptSelected,
  onClearReceipt,
  onRemoveReceipt,
  onViewReceipt,
  onScanReceipt,
  onAcceptSuggestion,
  onDismissSuggestion,
  onSubmit,
})
</script>

<template>
  <q-dialog v-model="isOpen" persistent>
    <q-card style="min-width: 680px; max-width: 820px; width: 100%" data-testid="staged-transaction-edit-dialog">
      <q-card-section class="row items-center q-pb-none">
        <div class="text-h6 text-weight-bold">Edit Staged Transaction</div>
        <q-space />
        <q-btn icon="close" flat round dense v-close-popup :disable="saving" data-testid="btn-close-staged-edit-dialog" />
      </q-card-section>

      <q-card-section class="q-pt-sm">
        <div class="text-caption text-grey-7 q-mb-sm">
          Update staged transaction details, attach or replace a receipt, and configure draft business or personal allocations.
        </div>

        <q-banner
          v-if="errorMessage"
          rounded
          dense
          inline-actions
          class="bg-negative text-white q-mb-sm"
          data-testid="banner-staged-edit-error"
        >
          <template #avatar>
            <q-icon name="error" color="white" />
          </template>
          {{ errorMessage }}
          <template #action>
            <q-btn flat round dense icon="close" size="sm" @click="errorMessage = ''" />
          </template>
        </q-banner>

        <q-form ref="formRef" @submit.prevent="onSubmit">
          <div class="row q-col-gutter-md q-mb-md">
            <div class="col-12 col-sm-6">
              <q-input
                v-model="form.date"
                outlined
                dense
                hide-bottom-space
                lazy-rules="ondemand"
                label="Date *"
                placeholder="YYYY-MM-DD"
                mask="####-##-##"
                :disable="saving"
                :rules="dateRules"
                data-testid="staged-edit-input-date"
                @keydown="handleDateKeydown"
              >
                <template #append>
                  <q-icon name="event" class="cursor-pointer">
                    <q-popup-proxy cover transition-show="scale" transition-hide="scale">
                      <q-date v-model="form.date" mask="YYYY-MM-DD" :today-btn="true">
                        <div class="row items-center justify-end">
                          <q-btn v-close-popup label="Close" color="primary" flat />
                        </div>
                      </q-date>
                    </q-popup-proxy>
                  </q-icon>
                </template>
              </q-input>
              <div
                v-if="aiSuggestions.date && !aiSuggestions.date.isMatch && !aiSuggestions.date.isDismissed"
                class="row items-center justify-between bg-blue-1 text-primary q-px-sm q-py-xs rounded-borders q-mt-xs q-mb-sm text-caption"
                data-testid="suggestion-banner-date"
              >
                <div class="row items-center no-wrap ellipsis q-mr-sm">
                  <q-icon name="auto_awesome" size="xs" class="q-mr-xs text-primary" />
                  <span>✨ AI Suggestion: {{ aiSuggestions.date.displayValue }}</span>
                </div>
                <div class="row items-center no-wrap q-gutter-x-xs">
                  <q-btn
                    flat
                    dense
                    size="sm"
                    color="positive"
                    icon="check"
                    label="Accept"
                    data-testid="btn-accept-suggestion-date"
                    @click="onAcceptSuggestion('date')"
                  />
                  <q-btn
                    flat
                    dense
                    size="sm"
                    color="grey-7"
                    icon="close"
                    label="Dismiss"
                    data-testid="btn-dismiss-suggestion-date"
                    @click="onDismissSuggestion('date')"
                  />
                </div>
              </div>
              <div
                v-else-if="aiSuggestions.date && aiSuggestions.date.isMatch && !aiSuggestions.date.isDismissed"
                class="row items-center text-positive text-caption q-mt-xs q-mb-sm q-px-xs"
                data-testid="match-indicator-date"
              >
                <q-icon name="auto_awesome" size="xs" class="q-mr-xs text-positive" />
                <span>✨ AI Match: {{ aiSuggestions.date.displayValue }} (✓)</span>
              </div>
            </div>

            <div class="col-12 col-sm-6">
              <q-input
                v-model="form.total_amount"
                type="number"
                step="0.01"
                outlined
                dense
                hide-bottom-space
                lazy-rules="ondemand"
                label="Total Amount *"
                placeholder="0.00"
                :disable="saving"
                :rules="amountRules"
                data-testid="staged-edit-input-total-amount"
                @blur="onTotalAmountBlur"
              >
                <template #prepend>
                  <span class="text-subtitle2 text-grey-7">$</span>
                </template>
              </q-input>
              <div
                v-if="aiSuggestions.total_amount && !aiSuggestions.total_amount.isMatch && !aiSuggestions.total_amount.isDismissed"
                class="row items-center justify-between bg-blue-1 text-primary q-px-sm q-py-xs rounded-borders q-mt-xs q-mb-sm text-caption"
                data-testid="suggestion-banner-total_amount"
              >
                <div class="row items-center no-wrap ellipsis q-mr-sm">
                  <q-icon name="auto_awesome" size="xs" class="q-mr-xs text-primary" />
                  <span>✨ AI Suggestion: ${{ aiSuggestions.total_amount.displayValue }}</span>
                </div>
                <div class="row items-center no-wrap q-gutter-x-xs">
                  <q-btn
                    flat
                    dense
                    size="sm"
                    color="positive"
                    icon="check"
                    label="Accept"
                    data-testid="btn-accept-suggestion-total_amount"
                    @click="onAcceptSuggestion('total_amount')"
                  />
                  <q-btn
                    flat
                    dense
                    size="sm"
                    color="grey-7"
                    icon="close"
                    label="Dismiss"
                    data-testid="btn-dismiss-suggestion-total_amount"
                    @click="onDismissSuggestion('total_amount')"
                  />
                </div>
              </div>
              <div
                v-else-if="aiSuggestions.total_amount && aiSuggestions.total_amount.isMatch && !aiSuggestions.total_amount.isDismissed"
                class="row items-center text-positive text-caption q-mt-xs q-mb-sm q-px-xs"
                data-testid="match-indicator-total_amount"
              >
                <q-icon name="auto_awesome" size="xs" class="q-mr-xs text-positive" />
                <span>✨ AI Match: ${{ aiSuggestions.total_amount.displayValue }} (✓)</span>
              </div>
            </div>
          </div>

          <div class="row q-col-gutter-md q-mb-md">
            <div class="col-12">
              <q-input
                v-model="form.description"
                outlined
                dense
                hide-bottom-space
                lazy-rules="ondemand"
                :label="form.is_personal ? 'Description / Payee (Optional)' : 'Description / Payee *'"
                :disable="saving"
                :rules="form.is_personal ? [] : descriptionRules"
                data-testid="staged-edit-input-description"
              >
                <template #prepend>
                  <q-icon name="edit_note" />
                </template>
              </q-input>
              <div
                v-if="aiSuggestions.description && !aiSuggestions.description.isMatch && !aiSuggestions.description.isDismissed"
                class="row items-center justify-between bg-blue-1 text-primary q-px-sm q-py-xs rounded-borders q-mt-xs q-mb-sm text-caption"
                data-testid="suggestion-banner-description"
              >
                <div class="row items-center no-wrap ellipsis q-mr-sm">
                  <q-icon name="auto_awesome" size="xs" class="q-mr-xs text-primary" />
                  <span>✨ AI Suggestion: {{ aiSuggestions.description.displayValue }}</span>
                </div>
                <div class="row items-center no-wrap q-gutter-x-xs">
                  <q-btn
                    flat
                    dense
                    size="sm"
                    color="positive"
                    icon="check"
                    label="Accept"
                    data-testid="btn-accept-suggestion-description"
                    @click="onAcceptSuggestion('description')"
                  />
                  <q-btn
                    flat
                    dense
                    size="sm"
                    color="grey-7"
                    icon="close"
                    label="Dismiss"
                    data-testid="btn-dismiss-suggestion-description"
                    @click="onDismissSuggestion('description')"
                  />
                </div>
              </div>
              <div
                v-else-if="aiSuggestions.description && aiSuggestions.description.isMatch && !aiSuggestions.description.isDismissed"
                class="row items-center text-positive text-caption q-mt-xs q-mb-sm q-px-xs"
                data-testid="match-indicator-description"
              >
                <q-icon name="auto_awesome" size="xs" class="q-mr-xs text-positive" />
                <span>✨ AI Match: {{ aiSuggestions.description.displayValue }} (✓)</span>
              </div>
            </div>
          </div>

          <div class="row q-col-gutter-md q-mb-sm">
            <div class="col-12">
              <q-input
                v-model="form.url"
                dense
                outlined
                label="Investigation URL"
                placeholder="https://..."
                data-testid="input-staged-url"
                class="q-mb-sm"
              >
                <template #prepend>
                  <q-icon name="link" />
                </template>
                <template #append v-if="form.url && form.url.trim()">
                  <q-btn
                    flat
                    round
                    dense
                    size="sm"
                    icon="open_in_new"
                    color="primary"
                    :href="form.url.trim()"
                    target="_blank"
                    rel="noopener noreferrer"
                    data-testid="btn-open-url"
                    @click.stop
                  >
                    <q-tooltip>Open URL</q-tooltip>
                  </q-btn>
                </template>
              </q-input>
            </div>
          </div>

          <q-separator class="q-my-sm" />

          <!-- Receipt Attachment -->
          <div class="q-my-sm">
            <div class="text-subtitle2 text-weight-bold text-grey-9 q-mb-xs">Receipt Attachment</div>

            <div class="row items-center q-col-gutter-sm" data-testid="staged-receipt-controls">
              <div class="col">
                <q-file
                  :model-value="form.staged_receipt_file"
                  outlined
                  dense
                  clearable
                  :display-value="displayReceiptName"
                  :label="hasReceipt ? 'Replace Receipt (.pdf, .png, .jpg)' : 'Upload Receipt (.pdf, .png, .jpg)'"
                  accept=".pdf,.png,.jpg,.jpeg,application/pdf,image/png,image/jpeg"
                  :disable="saving || isParsingReceipt"
                  data-testid="input-staged-receipt"
                  @update:model-value="onReceiptSelected"
                  @clear="onClearReceipt"
                >
                  <template #prepend>
                    <q-icon :name="hasReceipt ? 'upload_file' : 'attach_file'" />
                  </template>
                </q-file>
              </div>
              <div class="col-auto">
                <q-btn
                  outline
                  dense
                  color="primary"
                  icon="open_in_new"
                  label="View Receipt"
                  data-testid="btn-staged-view-receipt"
                  :disable="!hasReceipt || saving || isParsingReceipt"
                  @click="onViewReceipt"
                />
              </div>
              <div class="col-auto">
                <q-btn
                  outline
                  dense
                  color="primary"
                  icon="auto_awesome"
                  label="Scan with AI"
                  data-testid="btn-staged-scan-receipt"
                  :disable="!hasReceipt || saving || isParsingReceipt"
                  :loading="isParsingReceipt"
                  @click="onScanReceipt"
                />
              </div>
            </div>
          </div>

          <q-separator class="q-my-sm" />

          <!-- Draft Allocations -->
          <div class="q-my-sm">
            <div class="row items-center justify-between no-wrap q-mb-xs">
              <div>
                <div class="text-subtitle2 text-weight-bold text-grey-9">Draft Allocations</div>
                <div class="text-caption text-grey-7">
                  Assign to a company, split across companies, mark as personal, or leave unallocated.
                </div>
              </div>

              <div class="row items-center no-wrap q-gutter-x-sm">
                <q-chip
                  v-if="form.splits.length === 0"
                  color="warning"
                  text-color="white"
                  icon="warning"
                  dense
                  class="q-ma-none"
                  data-testid="staged-edit-unallocated-chip"
                >
                  Unallocated
                </q-chip>
                <q-chip
                  v-else
                  :color="isBalanced ? 'positive' : 'warning'"
                  text-color="white"
                  :icon="isBalanced ? 'check_circle' : 'warning'"
                  dense
                  class="q-ma-none"
                  data-testid="staged-edit-balance-chip"
                >
                  <template v-if="isBalanced">Balanced ($0.00 remaining)</template>
                  <template v-else-if="splitRemainder.remainderCents > 0">
                    Unallocated: ${{ splitRemainder.remainderFormatted }} remaining
                  </template>
                  <template v-else-if="splitRemainder.remainderCents < 0">
                    Overallocated: ${{ Math.abs(Number(splitRemainder.remainderFormatted)).toFixed(2) }}
                  </template>
                  <template v-else>Enter split amounts</template>
                </q-chip>

                <q-btn
                  v-if="form.splits.length > 0"
                  flat
                  dense
                  no-wrap
                  color="grey-8"
                  icon="clear_all"
                  label="Clear Allocations"
                  :disable="saving"
                  data-testid="staged-edit-btn-clear-allocations"
                  @click="onClearAllocations"
                />

                <q-btn
                  flat
                  dense
                  no-wrap
                  color="primary"
                  icon="add"
                  label="Add Split"
                  :disable="form.is_personal || saving"
                  data-testid="staged-edit-btn-add-split"
                  @click="onAddSplit"
                />
              </div>
            </div>

            <div class="row items-center q-gutter-x-sm q-mb-sm">
              <div>
                <q-toggle
                  :model-value="form.is_personal"
                  dense
                  label="Personal Expense"
                  color="primary"
                  :disable="form.splits.length > 1 || saving"
                  data-testid="staged-toggle-is-personal"
                  @update:model-value="onPersonalToggle"
                />
                <q-tooltip v-if="form.splits.length > 1">
                  {{ PERSONAL_SPLIT_TOOLTIP }}
                </q-tooltip>
              </div>
              <span v-if="form.splits.length > 1" class="text-caption text-grey-7"> ({{ PERSONAL_SPLIT_TOOLTIP }}) </span>
            </div>

            <div
              v-for="(split, index) in form.splits"
              :key="split.id || index"
              class="row q-col-gutter-sm items-start q-mb-xs"
              :data-testid="`staged-edit-split-row-${index}`"
            >
              <div class="col-12 col-sm-6">
                <q-select
                  v-model="split.company_id"
                  outlined
                  dense
                  emit-value
                  map-options
                  lazy-rules="ondemand"
                  :label="form.is_personal ? 'Personal Expense (No Company)' : 'Company *'"
                  :options="companyOptions"
                  :disable="form.is_personal || saving"
                  :rules="form.is_personal ? [] : splitCompanyRules"
                  :data-testid="`staged-edit-split-company-${index}`"
                >
                  <template #prepend>
                    <q-icon :name="form.is_personal ? 'person' : 'business'" />
                  </template>
                </q-select>
              </div>

              <div class="col-10 col-sm-5">
                <q-input
                  v-model="split.amount"
                  type="number"
                  step="0.01"
                  outlined
                  dense
                  lazy-rules="ondemand"
                  :readonly="form.splits.length === 1"
                  :disable="saving"
                  :label="form.splits.length === 1 ? 'Amount (100%) *' : 'Split Amount *'"
                  placeholder="0.00"
                  :rules="splitAmountRules"
                  :data-testid="`staged-edit-split-amount-${index}`"
                  @blur="onSplitAmountBlur(index)"
                >
                  <template #prepend>
                    <span class="text-subtitle2 text-grey-7">$</span>
                  </template>
                </q-input>
              </div>

              <div class="col-2 col-sm-1 flex justify-center q-pt-xs">
                <q-btn
                  flat
                  round
                  dense
                  color="negative"
                  icon="delete"
                  :disable="saving"
                  :data-testid="`staged-edit-btn-remove-split-${index}`"
                  @click="onRemoveSplit(index)"
                >
                  <q-tooltip>Remove split</q-tooltip>
                </q-btn>
              </div>
            </div>
          </div>

          <q-card-actions align="right" class="q-pt-md q-px-none">
            <q-btn flat label="Cancel" color="grey-7" v-close-popup :disable="saving" data-testid="btn-cancel-staged-edit" />
            <q-btn
              type="submit"
              label="Save Changes"
              color="primary"
              unelevated
              :loading="saving"
              :disable="!canSave || saving"
              data-testid="btn-save-staged-edit"
            />
          </q-card-actions>
        </q-form>
      </q-card-section>
    </q-card>
  </q-dialog>
</template>
