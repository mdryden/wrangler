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
        <q-form ref="formRef" @submit.prevent>
          <q-card-section class="q-gutter-y-md">
            <!-- Row 1: Date & Company -->
            <div class="row q-col-gutter-md">
              <div class="col-12 col-sm-6">
                <q-input
                  ref="dateInputRef"
                  v-model="form.date"
                  outlined
                  dense
                  label="Date *"
                  placeholder="YYYY-MM-DD"
                  mask="####-##-##"
                  :rules="dateRules"
                  data-testid="input-date"
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
                <q-select
                  v-model="form.company_id"
                  outlined
                  dense
                  emit-value
                  map-options
                  label="Company *"
                  :options="companyOptions"
                  :loading="companyStore.loading"
                  :rules="companyRules"
                  data-testid="select-company"
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
            </div>

            <!-- Row 2: Description & Total Amount -->
            <div class="row q-col-gutter-md">
              <div class="col-12 col-sm-8">
                <q-input
                  v-model="form.description"
                  outlined
                  dense
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

              <div class="col-12 col-sm-4">
                <q-input
                  v-model="form.total_amount"
                  type="number"
                  step="0.01"
                  outlined
                  dense
                  label="Total Amount *"
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

            <!-- Row 3: Receipt Attachment -->
            <div class="row q-col-gutter-md">
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
          </q-card-section>
        </q-form>
      </q-card>
    </div>
  </q-page>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from "vue"
import type { QForm, QInput } from "quasar"
import { useCompanyStore } from "../stores/companies"
import {
  amountRules,
  companyRules,
  createInitialManualEntryState,
  dateRules,
  descriptionRules,
  formatAmount,
  type ManualEntryFormState,
} from "./manualEntry"

const companyStore = useCompanyStore()
const formRef = ref<QForm | null>(null)
const dateInputRef = ref<QInput | null>(null)

const form = ref<ManualEntryFormState>(createInitialManualEntryState())

onMounted(async () => {
  if (companyStore.companies.length === 0) {
    try {
      await companyStore.fetchCompanies()
    } catch {
      // Errors handled in companyStore
    }
  }
})

const companyOptions = computed(() =>
  companyStore.companies.map(c => ({
    label: c.name,
    value: c.id,
  })),
)

function formatAmountOnBlur() {
  if (form.value.total_amount) {
    form.value.total_amount = formatAmount(form.value.total_amount)
  }
}

defineExpose({
  form,
  dateRules,
  companyRules,
  descriptionRules,
  amountRules,
  formatAmountOnBlur,
})
</script>
