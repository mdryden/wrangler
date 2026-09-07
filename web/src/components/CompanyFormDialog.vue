<template>
  <q-dialog v-model="isOpen" persistent>
    <q-card style="min-width: 440px; max-width: 550px; width: 100%">
      <q-card-section class="row items-center q-pb-none">
        <div class="text-h6 text-weight-bold">
          {{ isEditMode ? "Edit Company" : "Add Company" }}
        </div>
        <q-space />
        <q-btn icon="close" flat round dense v-close-popup :disable="saving" />
      </q-card-section>

      <q-card-section class="q-pt-sm">
        <div class="text-caption text-grey-7">
          {{ isEditMode ? "Update company details." : "Configure a new company entity for expense allocation." }}
        </div>

        <q-banner v-if="errorMessage" rounded dense inline-actions class="bg-negative text-white q-mt-sm">
          <template #avatar>
            <q-icon name="error" color="white" />
          </template>
          {{ errorMessage }}
          <template #action>
            <q-btn flat round dense icon="close" size="sm" @click="errorMessage = ''" />
          </template>
        </q-banner>

        <q-form ref="formRef" class="q-gutter-y-md q-mt-sm" @submit.prevent="onSubmit">
          <q-input
            v-model="name"
            label="Company Name *"
            placeholder="e.g. Acme Corp or Consulting LLC"
            outlined
            dense
            :rules="[val => (!!val && val.trim().length > 0) || 'Company name is required']"
            :disable="saving"
            autofocus
          >
            <template #prepend>
              <q-icon name="business" />
            </template>
          </q-input>

          <q-card-actions align="right" class="q-pt-md q-px-none">
            <q-btn flat label="Cancel" color="grey-7" v-close-popup :disable="saving" />
            <q-btn type="submit" :label="isEditMode ? 'Update Company' : 'Create Company'" color="primary" unelevated :loading="saving" />
          </q-card-actions>
        </q-form>
      </q-card-section>
    </q-card>
  </q-dialog>
</template>

<script setup lang="ts">
import { computed, ref, watch } from "vue"
import { useQuasar, type QForm } from "quasar"
import { useCompanyStore } from "../stores/companies"
import type { Company } from "../types/company"

const props = defineProps<{
  modelValue: boolean
  company: Company | null
}>()

const emit = defineEmits<{
  (e: "update:modelValue", val: boolean): void
  (e: "saved", company: Company): void
}>()

const $q = useQuasar()
const companyStore = useCompanyStore()

const formRef = ref<QForm | null>(null)
const name = ref<string>("")
const saving = ref<boolean>(false)
const errorMessage = ref<string>("")

const isOpen = computed({
  get: () => props.modelValue,
  set: (val: boolean) => emit("update:modelValue", val),
})

const isEditMode = computed(() => !!props.company)

// Reset or populate fields whenever dialog opens or company changes
watch(
  () => [props.modelValue, props.company] as const,
  ([visible, comp]) => {
    if (visible) {
      errorMessage.value = ""
      if (comp) {
        name.value = comp.name || ""
      } else {
        name.value = ""
      }
    }
  },
  { immediate: true },
)

async function onSubmit(): Promise<void> {
  errorMessage.value = ""
  saving.value = true

  try {
    let result: Company
    if (isEditMode && props.company) {
      result = await companyStore.updateCompany(props.company.id, {
        name: name.value.trim(),
      })
      $q.notify({
        type: "positive",
        message: `Company "${result.name}" updated successfully`,
        position: "top",
        timeout: 2500,
      })
    } else {
      result = await companyStore.createCompany({
        name: name.value.trim(),
      })
      $q.notify({
        type: "positive",
        message: `Company "${result.name}" created successfully`,
        position: "top",
        timeout: 2500,
      })
    }

    emit("saved", result)
    isOpen.value = false
  } catch (err) {
    errorMessage.value = err instanceof Error ? err.message : "Failed to save company"
    $q.notify({
      type: "negative",
      message: errorMessage.value,
      position: "top",
      timeout: 4000,
    })
  } finally {
    saving.value = false
  }
}
</script>
