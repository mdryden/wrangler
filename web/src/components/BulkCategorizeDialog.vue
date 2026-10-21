<script setup lang="ts">
import { computed, ref, watch } from "vue"
import { useQuasar } from "quasar"
import { useTransactionStore } from "../stores/transactions"
import type { ExportAllocationRow } from "../views/exportManager"
import { countOverwrittenCategories } from "../views/exportManager"
import type { WaveCategory } from "../types/wave"

const props = defineProps<{
  modelValue: boolean
  selectedRows: ExportAllocationRow[]
  categories: WaveCategory[]
}>()

const emit = defineEmits<{
  (e: "update:modelValue", val: boolean): void
  (e: "applied", count: number): void
}>()

const $q = useQuasar()
const transactionStore = useTransactionStore()

const isOpen = computed({
  get: () => props.modelValue,
  set: (val: boolean) => emit("update:modelValue", val),
})

const selectedCategoryId = ref<string | null>(null)
const filterText = ref<string>("")
const applying = ref<boolean>(false)
const errorMessage = ref<string>("")

const overwrittenCount = computed(() => countOverwrittenCategories(props.selectedRows))

const isApplyDisabled = computed(() => {
  return props.selectedRows.length === 0 || !selectedCategoryId.value || applying.value
})

const filteredOptions = computed(() => {
  const needle = filterText.value.trim().toLowerCase()
  const all = (props.categories || []).map(cat => ({
    label: cat.name,
    value: cat.id,
    is_uncategorized: cat.is_uncategorized,
  }))
  if (!needle) return all
  return all.filter(opt => opt.label.toLowerCase().includes(needle))
})

function filterFn(val: string, update: (callbackFn: () => void) => void): void {
  update(() => {
    filterText.value = val
  })
}

watch(
  () => props.modelValue,
  visible => {
    if (visible) {
      errorMessage.value = ""
      selectedCategoryId.value = null
      filterText.value = ""
    }
  },
  { immediate: true },
)

async function onApply(): Promise<void> {
  if (!selectedCategoryId.value || props.selectedRows.length === 0) return
  applying.value = true
  errorMessage.value = ""

  try {
    const allocationIds = props.selectedRows.map(r => r.id)
    const res = await transactionStore.bulkUpdateAllocationCategory(allocationIds, selectedCategoryId.value)

    $q.notify({
      type: "positive",
      message: `Successfully assigned category to ${res.updated_count} transactions`,
      position: "top",
      timeout: 2500,
    })

    emit("applied", res.updated_count)
    emit("update:modelValue", false)
  } catch (err) {
    errorMessage.value = err instanceof Error ? err.message : "Failed to bulk assign category"
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
          <div class="text-h6 text-weight-medium">Assign Category</div>
          <div class="text-caption text-grey-7">
            Assign a Wave category to {{ selectedRows.length }} selected transaction{{ selectedRows.length === 1 ? "" : "s" }}.
          </div>
        </div>
        <q-btn v-close-popup icon="close" flat round dense />
      </q-card-section>

      <q-card-section class="q-pt-md">
        <!-- Warning banner if existing categories will be overwritten -->
        <q-banner v-if="overwrittenCount > 0" rounded dense class="bg-amber-1 text-amber-10 q-mb-md" data-testid="banner-overwrite-warning">
          <template #avatar>
            <q-icon name="warning" color="amber-10" />
          </template>
          {{ overwrittenCount }} of {{ selectedRows.length }} selected transactions already have a category assigned which will be updated.
        </q-banner>

        <div class="text-subtitle2 q-mb-sm text-grey-8">Target Wave Category</div>

        <q-select
          v-model="selectedCategoryId"
          :options="filteredOptions"
          emit-value
          map-options
          dense
          outlined
          use-input
          fill-input
          hide-selected
          input-debounce="0"
          label="Select Wave Category *"
          data-testid="select-bulk-category"
          @filter="filterFn"
        >
          <template #selected-item="scope">
            <span :class="scope.opt.is_uncategorized ? 'text-grey-7 italic' : ''">
              {{ scope.opt.label }}
            </span>
          </template>
          <template #option="scope">
            <q-item v-bind="scope.itemProps">
              <q-item-section>
                <q-item-label :class="scope.opt.is_uncategorized ? 'text-primary text-weight-medium' : ''">
                  {{ scope.opt.label }}
                </q-item-label>
                <q-item-label v-if="scope.opt.is_uncategorized" caption class="text-grey-6"> Wave System Default </q-item-label>
              </q-item-section>
            </q-item>
          </template>
          <template #no-option>
            <q-item>
              <q-item-section class="text-grey">No categories match search</q-item-section>
            </q-item>
          </template>
        </q-select>
      </q-card-section>

      <q-card-actions align="right" class="q-pa-md">
        <q-btn v-close-popup flat label="Cancel" color="grey-7" :disable="applying" data-testid="btn-cancel-bulk-category" />
        <q-btn
          label="Apply"
          color="primary"
          unelevated
          :loading="applying"
          :disable="isApplyDisabled"
          data-testid="btn-apply-bulk-category"
          @click="onApply"
        />
      </q-card-actions>
    </q-card>
  </q-dialog>
</template>
