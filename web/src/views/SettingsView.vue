<template>
  <q-page class="q-pa-md">
    <!-- Page Header -->
    <div class="row items-center justify-between q-mb-md">
      <div>
        <div class="text-h5 text-weight-bold text-grey-9">Company Management & Settings</div>
        <div class="text-caption text-grey-7">
          Configure business entities, Wave OAuth connections, and synchronize Chart of Accounts categories.
        </div>
      </div>
      <div class="row items-center q-gutter-sm">
        <q-btn
          flat
          dense
          round
          icon="refresh"
          color="grey-7"
          aria-label="Refresh Companies"
          :loading="companyStore.loading"
          @click="loadCompanies"
        >
          <q-tooltip>Refresh companies</q-tooltip>
        </q-btn>
        <q-btn color="primary" icon="add" label="Add Company" unelevated @click="openAddDialog" />
      </div>
    </div>

    <!-- Error Banner -->
    <q-banner v-if="companyStore.error" rounded dense inline-actions class="bg-negative text-white q-mb-md">
      <template #avatar>
        <q-icon name="error" color="white" />
      </template>
      {{ companyStore.error }}
      <template #action>
        <q-btn flat label="Retry" color="white" @click="loadCompanies" />
      </template>
    </q-banner>

    <!-- Empty State -->
    <q-card v-if="!companyStore.loading && companyStore.companies.length === 0" flat bordered class="text-center q-pa-xl bg-grey-1">
      <q-icon name="domain_disabled" size="64px" color="grey-5" class="q-mb-sm" />
      <div class="text-h6 text-grey-8 text-weight-medium">No Companies Configured</div>
      <div class="text-body2 text-grey-6 q-mb-md" style="max-width: 480px; margin-left: auto; margin-right: auto">
        Add your business entity to begin allocating transactions and synchronizing expenses with Wave.
      </div>
      <q-btn color="primary" icon="add" label="Add First Company" unelevated @click="openAddDialog" />
    </q-card>

    <!-- Companies Table -->
    <q-table
      v-else
      :rows="companyStore.companies"
      :columns="columns"
      row-key="id"
      :loading="companyStore.loading"
      flat
      bordered
      :pagination="{ rowsPerPage: 10 }"
      class="company-table shadow-1"
    >
      <template #body-cell-name="props">
        <q-td :props="props">
          <div class="row items-center no-wrap">
            <q-avatar size="32px" color="blue-1" text-color="primary" icon="business" class="q-mr-sm" />
            <div>
              <div class="text-weight-bold text-body2">{{ props.row.name }}</div>
              <div v-if="props.row.wave_business_id" class="text-caption text-grey-6 font-mono">ID: {{ props.row.wave_business_id }}</div>
            </div>
          </div>
        </q-td>
      </template>

      <template #body-cell-wave_equity_account_id="props">
        <q-td :props="props">
          <code class="bg-grey-2 q-px-xs q-py-none text-caption text-weight-medium rounded-borders">
            {{ props.row.wave_equity_account_id }}
          </code>
          <q-tooltip>Anchor equity account ID used for double-entry balancing in Wave</q-tooltip>
        </q-td>
      </template>

      <template #body-cell-status="props">
        <q-td :props="props">
          <TokenStatusBadge :company="props.row" />
        </q-td>
      </template>

      <template #body-cell-actions="props">
        <q-td :props="props" align="right">
          <div class="row items-center justify-end q-gutter-xs no-wrap">
            <!-- Connect / Reconnect to Wave OAuth -->
            <q-btn
              :outline="!props.row.wave_access_token"
              :flat="!!props.row.wave_access_token"
              size="sm"
              color="primary"
              :icon="props.row.wave_access_token ? 'refresh' : 'link'"
              :label="props.row.wave_access_token ? 'Reconnect Wave' : 'Connect to Wave'"
              :loading="!!companyStore.connectingOAuth[props.row.id]"
              @click="onConnectWave(props.row)"
            >
              <q-tooltip>
                {{ props.row.wave_access_token ? "Re-authenticate Wave connection" : "Connect this company to Wave via OAuth" }}
              </q-tooltip>
            </q-btn>

            <!-- Sync Categories -->
            <q-btn
              outline
              size="sm"
              color="secondary"
              icon="sync"
              label="Sync Categories"
              :loading="!!companyStore.syncingCategories[props.row.id]"
              @click="onSyncCategories(props.row)"
            >
              <q-tooltip> Fetch and cache latest Chart of Accounts categories from Wave </q-tooltip>
            </q-btn>

            <!-- Edit Company -->
            <q-btn flat round dense size="sm" color="grey-8" icon="edit" aria-label="Edit company" @click="openEditDialog(props.row)">
              <q-tooltip>Edit company details</q-tooltip>
            </q-btn>

            <!-- Delete Company -->
            <q-btn
              flat
              round
              dense
              size="sm"
              color="negative"
              icon="delete"
              aria-label="Delete company"
              @click="onDeleteCompany(props.row)"
            >
              <q-tooltip>Delete company</q-tooltip>
            </q-btn>
          </div>
        </q-td>
      </template>
    </q-table>

    <!-- Company Add / Edit Dialog -->
    <CompanyFormDialog v-model="dialogVisible" :company="selectedCompany" @saved="onCompanySaved" />
  </q-page>
</template>

<script setup lang="ts">
import { onMounted, ref } from "vue"
import { useQuasar, type QTableColumn } from "quasar"
import { useCompanyStore } from "../stores/companies"
import type { Company } from "../types/company"
import CompanyFormDialog from "../components/CompanyFormDialog.vue"
import TokenStatusBadge from "../components/TokenStatusBadge.vue"

const $q = useQuasar()
const companyStore = useCompanyStore()

const dialogVisible = ref<boolean>(false)
const selectedCompany = ref<Company | null>(null)

const columns: QTableColumn[] = [
  {
    name: "name",
    required: true,
    label: "Company Name",
    align: "left",
    field: (row: Company) => row.name,
    sortable: true,
  },
  {
    name: "wave_equity_account_id",
    label: "Wave Equity Account ID",
    align: "left",
    field: (row: Company) => row.wave_equity_account_id,
    sortable: true,
  },
  {
    name: "status",
    label: "Wave Status",
    align: "center",
    field: (row: Company) => row.wave_access_token,
    sortable: false,
  },
  {
    name: "actions",
    label: "Actions",
    align: "right",
    field: () => "",
    sortable: false,
  },
]

async function loadCompanies(): Promise<void> {
  try {
    await companyStore.fetchCompanies()
  } catch {
    // Handled in store and error banner
  }
}

function openAddDialog(): void {
  selectedCompany.value = null
  dialogVisible.value = true
}

function openEditDialog(company: Company): void {
  selectedCompany.value = company
  dialogVisible.value = true
}

function onCompanySaved(): void {
  // Store is already updated by createCompany / updateCompany in dialog
}

async function onConnectWave(company: Company): Promise<void> {
  try {
    await companyStore.connectToWave(company.id)
  } catch (err) {
    const message = err instanceof Error ? err.message : "Failed to initiate Wave authorization"
    $q.notify({
      type: "negative",
      message,
      position: "top",
      timeout: 4000,
    })
  }
}

async function onSyncCategories(company: Company): Promise<void> {
  try {
    const categories = await companyStore.syncCategories(company.id)
    $q.notify({
      type: "positive",
      message: `Successfully synced ${categories.length} categories for "${company.name}"`,
      position: "top",
      timeout: 3000,
    })
  } catch (err) {
    const message = err instanceof Error ? err.message : "Failed to sync categories from Wave"
    $q.notify({
      type: "negative",
      message,
      position: "top",
      timeout: 5000,
    })
  }
}

function onDeleteCompany(company: Company): void {
  $q.dialog({
    title: "Delete Company",
    message: `Are you sure you want to delete "${company.name}"? This action cannot be undone.`,
    cancel: true,
    persistent: true,
    ok: {
      color: "negative",
      label: "Delete",
      unelevated: true,
    },
  }).onOk(async () => {
    try {
      await companyStore.deleteCompany(company.id)
      $q.notify({
        type: "positive",
        message: `Company "${company.name}" deleted successfully`,
        position: "top",
        timeout: 2500,
      })
    } catch (err) {
      const message = err instanceof Error ? err.message : "Failed to delete company"
      $q.notify({
        type: "negative",
        message,
        position: "top",
        timeout: 4000,
      })
    }
  })
}

onMounted(() => {
  loadCompanies()
})
</script>

<style scoped>
.font-mono {
  font-family: monospace;
}
</style>
