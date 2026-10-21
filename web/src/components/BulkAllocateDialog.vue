<script setup lang="ts">
import { computed, ref, watch } from "vue"
import { useQuasar } from "quasar"
import { useCompanyStore } from "../stores/companies"
import { useStagingStore } from "../stores/staging"
import type { StagedTransaction } from "../types/staging"
import { buildBulkAllocatePayload, countOverwrittenTransactions, type BulkAllocateTargetType } from "./bulkAllocate"

const props = defineProps<{
  modelValue: boolean
  selectedTransactions: StagedTransaction[]
}>()

const emit = defineEmits<{
  (e: "update:modelValue", val: boolean): void
  (e: "applied", count: number): void
}>()

const $q = useQuasar()
const companyStore = useCompanyStore()
const stagingStore = useStagingStore()

const isOpen = computed({
  get: () => props.modelValue,
  set: (val: boolean) => emit("update:modelValue", val),
})

const targetType = ref<BulkAllocateTargetType>("personal")
const selectedCompanyId = ref<string | null>(null)
const applying = ref<boolean>(false)
const errorMessage = ref<string>("")

const companyOptions = computed(() => {
  return companyStore.companies.map(c => ({
    label: c.name,
    value: c.id,
  }))
})

const overwrittenCount = computed(() => countOverwrittenTransactions(props.selectedTransactions))

const hasOverwrites = computed(() => overwrittenCount.value > 0)

const isApplyDisabled = computed(() => {
  if (props.selectedTransactions.length === 0) return true
  if (targetType.value === "company" && !selectedCompanyId.value) return true
  return false
})

watch(
  () => props.modelValue,
  async visible => {
    if (visible) {
      errorMessage.value = ""
      targetType.value = "personal"
      if (companyStore.companies.length === 0) {
        await companyStore.fetchCompanies().catch(() => {})
      }
      if (companyStore.companies.length > 0) {
        selectedCompanyId.value = companyStore.companies[0].id
      } else {
        selectedCompanyId.value = null
      }
    }
  },
  { immediate: true },
)

async function onApply(): Promise<void> {
  if (props.selectedTransactions.length === 0) return
  applying.value = true
  errorMessage.value = ""

  try {
    const payload = buildBulkAllocatePayload(props.selectedTransactions, targetType.value, selectedCompanyId.value)

    const res = await stagingStore.bulkAllocateStaged(payload)

    $q.notify({
      type: "positive",
      message: `Successfully allocated ${res.updated_count} transactions`,
      position: "top",
      timeout: 2500,
    })

    emit("applied", res.updated_count)
    emit("update:modelValue", false)
  } catch (err) {
    errorMessage.value = err instanceof Error ? err.message : "Failed to apply bulk allocation"
    $q.notify({
      type: "negative",
      message: errorMessage.value,
      position: "top",
      timeout: 4000,
    })
  } finally {
    applying.value = false
  }
}
</script>

<template>
  <q-dialog v-model="isOpen">
    <q-card style="min-width: 440px; max-width: 520px; width: 100%">
      <q-card-section class="row items-center q-pb-none">
        <div class="col">
          <div class="text-h6 text-weight-medium">Bulk Allocate Transactions</div>
          <div class="text-caption text-grey-7">
            Assign an entity to {{ selectedTransactions.length }} selected staged transaction{{
              selectedTransactions.length === 1 ? "" : "s"
            }}.
          </div>
        </div>
        <q-btn v-close-popup icon="close" flat round dense />
      </q-card-section>

      <q-card-section class="q-pt-md">
        <!-- Notice banner for overwriting existing splits/allocations -->
        <q-banner v-if="hasOverwrites" rounded dense class="bg-amber-1 text-amber-9 q-mb-md" data-testid="banner-overwrite-warning">
          <template #avatar>
            <q-icon name="warning" color="amber-9" />
          </template>
          {{ overwrittenCount }} of {{ selectedTransactions.length }} transactions already have allocations or splits which will be
          overwritten.
        </q-banner>

        <div class="text-subtitle2 q-mb-sm text-grey-8">Target Allocation (100%)</div>

        <div class="q-gutter-y-sm">
          <q-radio v-model="targetType" val="personal" label="Personal" data-testid="radio-personal" />

          <div class="q-gutter-y-xs">
            <q-radio v-model="targetType" val="company" label="Company" data-testid="radio-company" />
            <div v-if="targetType === 'company'" class="q-pl-lg q-pt-xs">
              <q-select
                v-model="selectedCompanyId"
                :options="companyOptions"
                emit-value
                map-options
                outlined
                dense
                label="Select Company *"
                data-testid="select-company"
                :rules="[val => !!val || 'Company is required']"
              />
            </div>
          </div>

          <q-radio v-model="targetType" val="clear" label="Unallocated / Clear" data-testid="radio-clear" />
        </div>
      </q-card-section>

      <q-card-actions align="right" class="q-pa-md">
        <q-btn v-close-popup flat label="Cancel" color="grey-7" :disable="applying" data-testid="btn-cancel-allocation" />
        <q-btn
          label="Apply Allocation"
          color="primary"
          unelevated
          :loading="applying"
          :disable="isApplyDisabled"
          data-testid="btn-apply-allocation"
          @click="onApply"
        />
      </q-card-actions>
    </q-card>
  </q-dialog>
</template>
