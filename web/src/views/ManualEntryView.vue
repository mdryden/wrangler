<script setup lang="ts">
import { computed, nextTick, onMounted, ref, watch } from "vue"
import { Notify, useQuasar } from "quasar"
import type { QForm, QInput } from "quasar"
import { useCompanyStore } from "../stores/companies"
import { useTransactionStore } from "../stores/transactions"
import {
  amountRules,
  calculateSplitRemainder,
  createInitialManualEntryState,
  dateRules,
  descriptionRules,
  formatAmount,
  getTodayDateString,
  prepareTransactionPayload,
  splitAmountRules,
  splitCompanyRules,
  type ManualEntryFormState,
} from "./manualEntry"

const companyStore = useCompanyStore()
const transactionStore = useTransactionStore()
const formRef = ref<QForm | null>(null)
const dateInputRef = ref<QInput | null>(null)
const isSubmitting = ref(false)

const form = ref<ManualEntryFormState>(createInitialManualEntryState())

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

// Synchronize total amount with split 0 in default single split state
watch(
  () => form.value.total_amount,
  newTotal => {
    if (form.value.splits.length === 1) {
      form.value.splits[0].amount = newTotal
    }
  },
)

// Synchronize split 0 amount when splits length reverts to 1
watch(
  () => form.value.splits.length,
  newLength => {
    if (newLength === 1) {
      form.value.splits[0].amount = form.value.total_amount
    }
  },
)

onMounted(async () => {
  if (companyStore.companies.length === 0) {
    try {
      await companyStore.fetchCompanies()
    } catch {
      // Errors handled in companyStore
    }
  }
  await nextTick()
  focusDateInput()
})

const companyOptions = computed(() =>
  companyStore.companies.map(c => ({
    label: c.name,
    value: c.id,
  })),
)

const splitRemainder = computed(() => calculateSplitRemainder(form.value.total_amount, form.value.splits))

const isBalanced = computed(() => splitRemainder.value.isBalanced)

const canSubmit = computed(() => {
  if (!isBalanced.value) return false
  if (!form.value.date || !/^\d{4}-\d{2}-\d{2}$/.test(form.value.date.trim())) return false
  if (!form.value.description || !form.value.description.trim()) return false
  if (form.value.total_amount === "" || isNaN(Number(form.value.total_amount)) || Number(form.value.total_amount) === 0) {
    return false
  }
  if (form.value.splits.length === 0) return false
  for (const s of form.value.splits) {
    if (!s.company_id || !s.company_id.trim()) return false
    if (s.amount === "" || isNaN(Number(s.amount)) || Number(s.amount) === 0) return false
  }
  return true
})

function addSplit() {
  const rem = splitRemainder.value
  let initialAmount = ""
  if (rem.remainderCents !== 0 && !isNaN(Number(rem.remainderFormatted))) {
    initialAmount = rem.remainderFormatted
  }
  form.value.splits.push({
    company_id: "",
    amount: initialAmount,
  })
}

function removeSplit(index: number) {
  if (form.value.splits.length > 1) {
    form.value.splits.splice(index, 1)
  }
}

function formatAmountOnBlur() {
  if (form.value.total_amount) {
    form.value.total_amount = formatAmount(form.value.total_amount)
    if (form.value.splits.length === 1) {
      form.value.splits[0].amount = form.value.total_amount
    }
  }
}

function formatSplitAmountOnBlur(index: number) {
  const split = form.value.splits[index]
  if (split && split.amount) {
    split.amount = formatAmount(split.amount)
  }
}

function handleDateKeydown(e: KeyboardEvent) {
  if ((e.ctrlKey || e.metaKey) && (e.key === ";" || e.code === "Semicolon")) {
    e.preventDefault()
    e.stopPropagation()
    form.value.date = getTodayDateString()
  }
}

function handleFormKeydown(e: KeyboardEvent) {
  if ((e.ctrlKey || e.metaKey) && e.key === "Enter") {
    e.preventDefault()
    submitForm()
  }
}

function focusDateInput() {
  if (dateInputRef.value) {
    if (typeof dateInputRef.value.focus === "function") {
      dateInputRef.value.focus()
    } else {
      const inputEl = (dateInputRef.value as unknown as { $el?: HTMLElement }).$el?.querySelector("input")
      inputEl?.focus()
    }
  }
}

async function resetForm(preserveCompany = true) {
  const companyToKeep = preserveCompany ? form.value.splits[0]?.company_id || "" : ""
  form.value = createInitialManualEntryState(companyToKeep)
  await nextTick()
  formRef.value?.resetValidation()
}

async function submitForm() {
  if (isSubmitting.value) return

  const valid = await formRef.value?.validate()
  if (!valid || !canSubmit.value || !isBalanced.value) {
    return
  }

  isSubmitting.value = true
  try {
    const { payload } = prepareTransactionPayload(form.value)
    await transactionStore.createTransaction(payload)

    notifySuccess("Transaction created successfully")

    // Reset form fields while preserving company attribution for rapid continuous entry
    await resetForm(true)

    // Programmatically focus date input for next expense
    await nextTick()
    focusDateInput()
  } catch (err) {
    const msg = err instanceof Error ? err.message : "Failed to create transaction"
    notifyError(msg)
  } finally {
    isSubmitting.value = false
  }
}

defineExpose({
  form,
  dateRules,
  descriptionRules,
  amountRules,
  splitCompanyRules,
  splitAmountRules,
  formatAmountOnBlur,
  formatSplitAmountOnBlur,
  addSplit,
  removeSplit,
  splitRemainder,
  isBalanced,
  canSubmit,
  handleDateKeydown,
  handleFormKeydown,
  submitForm,
  resetForm,
  focusDateInput,
  isSubmitting,
})
</script>

<style scoped>
:deep(.q-field--dense.q-field--with-bottom) {
  padding-bottom: 16px;
}
</style>

<template>
  <q-page class="q-pa-md flex justify-center">
    <div class="full-width" style="max-width: 800px">
      <!-- Page Header -->
      <div class="q-mb-md">
        <div class="text-h5 text-weight-bold text-grey-9">Manual Entry</div>
        <div class="text-caption text-grey-7">
          Rapid entry form exclusively for business expenses. All manual transactions are attributed to a company.
        </div>
      </div>

      <!-- Main Form Card -->
      <q-card flat bordered class="q-pa-sm">
        <q-form ref="formRef" @submit.prevent="submitForm" @keydown="handleFormKeydown">
          <q-card-section class="q-pa-sm">
            <!-- Row 1: Date | Amount -->
            <div class="row q-col-gutter-md q-mb-xs">
              <div class="col-12 col-sm-6">
                <q-input
                  ref="dateInputRef"
                  v-model="form.date"
                  outlined
                  dense
                  lazy-rules="ondemand"
                  label="Date *"
                  placeholder="YYYY-MM-DD"
                  mask="####-##-##"
                  :rules="dateRules"
                  data-testid="input-date"
                  hint="Use Ctrl+; to set today"
                  @keydown="handleDateKeydown"
                >
                  <template #append>
                    <q-icon name="event" class="cursor-pointer" data-testid="icon-date-picker">
                      <q-popup-proxy cover transition-show="scale" transition-hide="scale">
                        <q-date v-model="form.date" mask="YYYY-MM-DD" :today-btn="true" data-testid="date-picker">
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
                  label="Amount *"
                  placeholder="0.00"
                  :rules="amountRules"
                  data-testid="input-total-amount"
                  @blur="formatAmountOnBlur"
                >
                  <template #prepend>
                    <span class="text-subtitle2 text-grey-7">$</span>
                  </template>
                </q-input>
              </div>
            </div>

            <!-- Row 2: Description -->
            <div class="row q-col-gutter-md q-mb-xs">
              <div class="col-12">
                <q-input
                  v-model="form.description"
                  outlined
                  dense
                  lazy-rules="ondemand"
                  label="Description / Payee *"
                  placeholder="e.g. Acme Supplies, Vendor memo..."
                  :rules="descriptionRules"
                  data-testid="input-description"
                >
                  <template #prepend>
                    <q-icon name="edit_note" />
                  </template>
                </q-input>
              </div>
            </div>

            <!-- Row 3: Receipt Attachment -->
            <div class="row q-col-gutter-md q-mb-xs">
              <div class="col-12">
                <q-file
                  v-model="form.receipt_file"
                  outlined
                  dense
                  clearable
                  label="Receipt Attachment (Optional)"
                  accept=".pdf,.png,.jpg,.jpeg,application/pdf,image/png,image/jpeg"
                  data-testid="input-receipt-file"
                >
                  <template #prepend>
                    <q-icon name="attach_file" />
                  </template>
                </q-file>
              </div>
            </div>

            <!-- Row 4: Inline Allocation Splitter (13.3) -->
            <q-separator class="q-my-md" />

            <div class="q-mb-sm">
              <div class="row items-center justify-between q-mb-sm">
                <div>
                  <div class="text-subtitle1 text-weight-bold text-grey-9">Allocations</div>
                  <div class="text-caption text-grey-7">Assign expenses across businesses (business entities only).</div>
                </div>

                <div class="row items-center q-gutter-x-sm">
                  <!-- Real-time Balance Indicator -->
                  <q-chip
                    :color="isBalanced ? 'positive' : 'warning'"
                    text-color="white"
                    :icon="isBalanced ? 'check_circle' : 'warning'"
                    dense
                    data-testid="split-balance-indicator"
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
                  <q-btn flat dense color="primary" icon="add" label="Add Split" data-testid="btn-add-split" @click="addSplit" />
                </div>
              </div>

              <!-- Splits List -->
              <div
                v-for="(split, index) in form.splits"
                :key="index"
                class="row q-col-gutter-sm items-start q-mb-xs"
                :data-testid="`split-row-${index}`"
              >
                <div class="col-12 col-sm-6">
                  <q-select
                    v-model="split.company_id"
                    outlined
                    dense
                    emit-value
                    map-options
                    lazy-rules="ondemand"
                    label="Company *"
                    :options="companyOptions"
                    :rules="splitCompanyRules"
                    :data-testid="`split-company-${index}`"
                  >
                    <template #prepend>
                      <q-icon name="business" />
                    </template>
                    <template #no-option>
                      <q-item>
                        <q-item-section class="text-grey">No companies found</q-item-section>
                      </q-item>
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
                    :label="form.splits.length === 1 ? 'Amount *' : 'Split Amount *'"
                    placeholder="0.00"
                    :rules="splitAmountRules"
                    :data-testid="`split-amount-${index}`"
                    @blur="formatSplitAmountOnBlur(index)"
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
                    :disable="form.splits.length <= 1"
                    :data-testid="`btn-remove-split-${index}`"
                    @click="removeSplit(index)"
                  >
                    <q-tooltip v-if="form.splits.length > 1">Remove split</q-tooltip>
                    <q-tooltip v-else>At least one split is required</q-tooltip>
                  </q-btn>
                </div>
              </div>
            </div>

            <!-- Row 5: Action Bar (13.4) -->
            <q-separator class="q-my-md" />

            <div class="row items-center justify-between q-pt-xs">
              <div><!-- spacer --></div>

              <div class="row items-center q-gutter-x-sm">
                <q-btn flat color="grey-7" label="Reset" data-testid="btn-reset" @click="resetForm(false)" />

                <q-btn
                  unelevated
                  color="primary"
                  label="Submit Transaction"
                  icon="check"
                  type="submit"
                  :loading="isSubmitting"
                  :disable="!canSubmit || isSubmitting"
                  data-testid="btn-submit"
                />
              </div>
            </div>
          </q-card-section>
        </q-form>
      </q-card>
    </div>
  </q-page>
</template>
