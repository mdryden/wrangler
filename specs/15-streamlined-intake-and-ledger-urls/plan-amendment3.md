# Implementation Plan: Amendment 3 - URL-Activated Staging Row Quick Actions & Keyboard Triage Workstation

This implementation plan defines the deliverables required to implement the URL-activated staging quick triage sub-row and contextual keyboard shortcut workflow specified in [`specs/15-streamlined-intake-and-ledger-urls/spec-amendment3.md`](file:///D:/src/personal/wrangler/specs/15-streamlined-intake-and-ledger-urls/spec-amendment3.md).

Wrangler serves as an ingestion, deduplication, and entity attribution layer. During high-volume intake (notably Amazon order synchronization), transactions often arrive without descriptions or entity tags, requiring the user to open source investigation URLs in external browser tabs. This amendment establishes a contextual triage strip rendered directly beneath the active staging row upon URL click, coupled with keyboard shortcuts (`X` for 100% Personal, `C` for generic company edit dialog, `1..N` for direct company split pre-selection, and `Escape` for dismiss), drastically reducing manual click friction.

The plan is divided into sequential, deliverable-driven phases with atomic implementation tasks in dependency order. Per [`specs/ARCHITECTURE.md`](file:///D:/src/personal/wrangler/specs/ARCHITECTURE.md) and the amendment specification, no database migrations or backend API changes are required. Each task specifies concrete files, components, utilities, and automated Vitest test coverage adhering to development standards defined in [`AGENTS.md`](file:///D:/src/personal/wrangler/AGENTS.md).

---

## Phase 1: Pure Keyboard Shortcut Logic & Form Pre-selection Utilities

*Goal:* Implement the pure keyboard shortcut evaluator and form pre-selection state creator with comprehensive Vitest unit test coverage.

### 1.1 Pure Keyboard Shortcut Handler & Types
- **File:** [`web/src/views/importView.ts`](file:///D:/src/personal/wrangler/web/src/views/importView.ts)
- **Description:** Implement the pure shortcut evaluator and state interface to handle keystrokes when an active staging row action strip is visible.
- **Details:**
  - Define and export interface `StagingShortcutContext`:
    ```typescript
    export interface StagingShortcutContext {
      activeActionRowId: string | null
      stagedTransactions: StagedTransaction[]
      companies: Company[]
      isDialogOpen: boolean
      onPersonal: (row: StagedTransaction) => void
      onCompanyEdit: (row: StagedTransaction, defaultCompanyId?: string | null) => void
      onDismissStrip: () => void
    }
    ```
  - Implement and export `handleStagingKeyboardShortcut(event: KeyboardEvent, context: StagingShortcutContext): boolean`:
    - Return `false` immediately if `!context.activeActionRowId` or `context.isDialogOpen`.
    - Guard against modifier keys: if `event.ctrlKey || event.metaKey || event.altKey`, return `false` to preserve system/browser shortcuts (such as `Ctrl+C`).
    - Guard against typing in form inputs: if `target` is `INPUT`, `TEXTAREA`, `SELECT`, or `target.isContentEditable`, return `false`.
    - Locate active transaction in `context.stagedTransactions`. If not found or `activeRow.status !== "STAGED"`, return `false`.
    - Evaluate normalized `key = event.key.toLowerCase()`:
      - `key === "x"`: call `event.preventDefault()`, call `context.onPersonal(activeRow)`, and return `true`.
      - `key === "c"`: call `event.preventDefault()`, call `context.onCompanyEdit(activeRow, null)`, and return `true`.
      - Regex `/^[1-9]$/.test(event.key)`: calculate index `idx = Number(event.key) - 1`. If `idx >= 0 && idx < context.companies.length`, call `event.preventDefault()`, call `context.onCompanyEdit(activeRow, context.companies[idx].id)`, and return `true`.
      - `key === "escape"`: call `event.preventDefault()`, call `context.onDismissStrip()`, and return `true`.
      - Otherwise, return `false`.
- **Automated Tests:** In [`web/src/views/__tests__/importView.spec.ts`](file:///D:/src/personal/wrangler/web/src/views/__tests__/importView.spec.ts):
  - Unit tests for `handleStagingKeyboardShortcut`:
    - Dispatches `onPersonal` and calls `preventDefault()` on `x` and `X`.
    - Dispatches `onCompanyEdit` with `null` company ID and calls `preventDefault()` on `c` and `C`.
    - Dispatches `onCompanyEdit` with matching company ID on digit keys `1..N`.
    - Ignores digit keys exceeding available companies count.
    - Dispatches `onDismissStrip` and calls `preventDefault()` on `Escape`.
    - Returns `false` when `isDialogOpen` is `true`, `activeActionRowId` is `null`, or active row status is not `STAGED`.
    - Returns `false` when focused element is `INPUT` or `TEXTAREA`.
    - Returns `false` when `ctrlKey`, `metaKey`, or `altKey` is pressed.

### 1.2 Form Pre-selection Helper Support in `stagedTransactionEdit.ts`
- **File:** [`web/src/components/stagedTransactionEdit.ts`](file:///D:/src/personal/wrangler/web/src/components/stagedTransactionEdit.ts)
- **Description:** Enhance `createStagedTransactionEditState` to support explicit company pre-selection when opening the edit dialog from quick actions.
- **Details:**
  - In `createStagedTransactionEditState(staged: StagedTransaction, defaultCompanyId: string | null = null)`:
    - If `defaultCompanyId` is explicitly provided (`defaultCompanyId !== null && defaultCompanyId !== undefined`) and `rawAllocations.length <= 1`:
      - Initialize single split pre-allocated to the specified company:
        ```typescript
        splits = [
          {
            amount: formattedTotal,
            is_personal: false,
            company_id: defaultCompanyId,
          },
        ]
        ```
      - Set `is_personal = false`.
    - If `rawAllocations.length > 1`: preserve existing multi-split allocations while mapping to form split items.
    - If `defaultCompanyId` is not provided: retain existing initialization behavior (mapping existing allocations or defaulting to single split).
- **Automated Tests:** In [`web/src/components/__tests__/stagedTransactionEdit.test.ts`](file:///D:/src/personal/wrangler/web/src/components/__tests__/stagedTransactionEdit.test.ts):
  - Unit tests verifying:
    - Explicit `defaultCompanyId` on unallocated item initializes a single split with that company ID and `is_personal = false`.
    - Explicit `defaultCompanyId` on transaction currently marked Personal (`rawAllocations.length === 1`) overrides Personal with target company split.
    - Multi-split transaction (`rawAllocations.length > 1`) preserves existing splits even if `defaultCompanyId` is supplied.

---

## Phase 2: Staged Transaction Edit Dialog Integration

*Goal:* Update `StagedTransactionEditDialog` to accept a `defaultCompanyId` prop and pass it through to form initialization.

### 2.1 Add `defaultCompanyId` Prop & Watcher in `StagedTransactionEditDialog`
- **File:** [`web/src/components/StagedTransactionEditDialog.vue`](file:///D:/src/personal/wrangler/web/src/components/StagedTransactionEditDialog.vue)
- **Description:** Extend the component props definition and form synchronization watcher to consume the pre-selected company ID.
- **Details:**
  - Update `defineProps`:
    ```typescript
    const props = defineProps<{
      modelValue: boolean
      stagedTransaction: StagedTransaction | null
      defaultCompanyId?: string | null
    }>()
    ```
  - Update the dialog visibility and transaction watcher:
    ```typescript
    watch(
      () => [props.modelValue, props.stagedTransaction, props.defaultCompanyId] as const,
      ([visible, staged, defaultCompId]) => {
        if (visible && staged) {
          errorMessage.value = ""
          const resolvedCompId =
            defaultCompId ??
            (companyStore.companies.length === 1 ? companyStore.companies[0].id : null)
          form.value = createStagedTransactionEditState(staged, resolvedCompId)
          aiSuggestions.value = createInitialAiSuggestionsState()
        } else {
          aiSuggestions.value = createInitialAiSuggestionsState()
        }
      },
      { immediate: true },
    )
    ```
- **Automated Tests:** In [`web/src/components/__tests__/StagedTransactionEditDialog.spec.ts`](file:///D:/src/personal/wrangler/web/src/components/__tests__/StagedTransactionEditDialog.spec.ts):
  - Mount component with `defaultCompanyId="comp-2"` and verify the form splits reflect `company_id="comp-2"`.
  - Mount component without `defaultCompanyId` and verify single-company fallback behaves as before when only 1 company exists in store.

---

## Phase 3: Staging Review Table URL-Activated Quick Action Strip & Keyboard Wiring

*Goal:* Implement the expandable `<q-tr>` sub-row, URL click trigger, triage action handlers, and global keyboard event listeners in `ImportView.vue`.

### 3.1 Expanded Quick Triage Sub-Row Layout & Action Handlers
- **File:** [`web/src/views/ImportView.vue`](file:///D:/src/personal/wrangler/web/src/views/ImportView.vue)
- **Description:** Implement reactive state, URL activation handler, triage button handlers, and the expanded action strip layout directly below the active table row.
- **Details:**
  - Add reactive state variables:
    ```typescript
    const activeActionRowId = ref<string | null>(null)
    const editDialogDefaultCompanyId = ref<string | null>(null)
    ```
  - Update URL button click handler:
    - On clicking the URL button (`btn-open-url`), set `activeRowId.value = props.row.id`. If `props.row.status === "STAGED"`, set `activeActionRowId.value = props.row.id`. (The browser continues to open the URL in a new tab via `:href` and `target="_blank"`).
  - Implement action handlers:
    - `onActionStripPersonal(row: StagedTransaction)`:
      - Call `stagingStore.updateStagedTransaction(row.id, buildQuickAssignPayload(row, PERSONAL_QUICK_ASSIGN_VALUE))`.
      - Display positive toast `notifySuccess("Marked as Personal")`.
      - Set `activeActionRowId.value = null`.
    - `onActionStripCompany(row: StagedTransaction)`:
      - Set `activeActionRowId.value = null`.
      - Set `editDialogDefaultCompanyId.value = null`.
      - Open edit dialog: `openEditDialog(row)`.
    - `onActionStripCompanyByIndex(row: StagedTransaction, idx: number)`:
      - Set `activeActionRowId.value = null`.
      - Retrieve `targetComp = companyStore.companies[idx]`.
      - Set `editDialogDefaultCompanyId.value = targetComp ? targetComp.id : null`.
      - Open edit dialog: `openEditDialog(row)`.
    - `dismissActionStrip()`:
      - Set `activeActionRowId.value = null`.
  - Update `openEditDialog` signature:
    - Support optional `defaultCompanyId: string | null = null`, setting `editDialogDefaultCompanyId.value = defaultCompanyId`.
  - Pass `:default-company-id="editDialogDefaultCompanyId"` to `<StagedTransactionEditDialog>`.
  - Refactor `<q-table>` template to use `#body="props"`:
    - Primary row: `<q-tr :props="props" :class="tableRowClass(props.row)" @click="onRowClick($event, props.row)" @dblclick="openEditDialog(props.row)">`
      - Render existing columns in order: `select`, `url`, `actions`, `allocations`, `date`, `description`, `total_amount`, `receipt`.
      - Ensure URL button click sets active action row: `@click.stop="onOpenUrl(props.row)"`.
    - Expanded action strip sub-row:
      ```html
      <q-tr
        v-if="activeActionRowId === props.row.id && props.row.status === 'STAGED'"
        :props="props"
        class="staged-action-strip-row"
        data-testid="row-staged-action-strip"
      >
        <q-td :colspan="columns.length" class="q-pa-xs">
          <div class="staged-action-strip row items-center justify-between q-px-md q-py-xs bg-blue-grey-1 rounded-borders">
            <div class="row items-center q-gutter-sm">
              <span class="text-caption text-weight-bold text-grey-8 row items-center q-mr-xs">
                <q-icon name="bolt" color="amber-9" size="18px" class="q-mr-xs" />
                Quick Triage:
              </span>
              <q-btn
                unelevated
                dense
                size="sm"
                color="positive"
                icon="person"
                label="Personal Expense (X)"
                data-testid="btn-action-strip-personal"
                @click.stop="onActionStripPersonal(props.row)"
              >
                <q-tooltip>Mark 100% Personal (Shortcut: X)</q-tooltip>
              </q-btn>
              <q-btn
                unelevated
                dense
                size="sm"
                color="primary"
                icon="business"
                label="Company Expense (C)"
                data-testid="btn-action-strip-company"
                @click.stop="onActionStripCompany(props.row)"
              >
                <q-tooltip>Open Edit Dialog (Shortcut: C)</q-tooltip>
              </q-btn>
              <q-separator vertical class="q-mx-xs" v-if="companyStore.companies.length > 0" />
              <q-btn
                v-for="(comp, idx) in companyStore.companies"
                :key="comp.id"
                outline
                dense
                size="sm"
                color="primary"
                class="bg-white"
                :label="`${comp.name} (${idx + 1})`"
                :data-testid="`btn-action-strip-comp-${comp.id}`"
                @click.stop="onActionStripCompanyByIndex(props.row, idx)"
              >
                <q-tooltip>Edit with {{ comp.name }} pre-selected (Shortcut: {{ idx + 1 }})</q-tooltip>
              </q-btn>
            </div>
            <q-btn
              flat
              round
              dense
              size="xs"
              icon="close"
              color="grey-6"
              aria-label="Close triage actions"
              data-testid="btn-action-strip-close"
              @click.stop="dismissActionStrip"
            >
              <q-tooltip>Close quick actions (Esc)</q-tooltip>
            </q-btn>
          </div>
        </q-td>
      </q-tr>
      ```
  - Scoped CSS styling for action strip:
    - Subtle background `bg-blue-grey-1` (`#eceff1`), `1px solid rgba(0, 0, 0, 0.08)`, border radius.

### 3.2 Window Keyboard Event Listener & Component Lifecycle
- **File:** [`web/src/views/ImportView.vue`](file:///D:/src/personal/wrangler/web/src/views/ImportView.vue)
- **Description:** Wire global `keydown` event listener to evaluate contextual shortcuts using `handleStagingKeyboardShortcut`.
- **Details:**
  - In `ImportView.vue`:
    ```typescript
    function onKeydown(event: KeyboardEvent): void {
      handleStagingKeyboardShortcut(event, {
        activeActionRowId: activeActionRowId.value,
        stagedTransactions: stagingStore.stagedTransactions,
        companies: companyStore.companies,
        isDialogOpen: editDialogVisible.value || bulkAllocateDialogVisible.value,
        onPersonal: onActionStripPersonal,
        onCompanyEdit: (row, defaultCompId) => {
          activeActionRowId.value = null
          editDialogDefaultCompanyId.value = defaultCompId ?? null
          openEditDialog(row)
        },
        onDismissStrip: dismissActionStrip,
      })
    }

    onMounted(() => {
      window.addEventListener("keydown", onKeydown)
    })

    onUnmounted(() => {
      window.removeEventListener("keydown", onKeydown)
    })
    ```
  - Ensure filters reset and row dismissals set `activeActionRowId.value = null`.

### 3.3 Component & Integration Test Suite
- **File:** [`web/src/views/__tests__/importView.spec.ts`](file:///D:/src/personal/wrangler/web/src/views/__tests__/importView.spec.ts)
- **Description:** Implement comprehensive test coverage for URL activation, quick triage strip actions, dialog opening, and template structure.
- **Details:**
  - Component tests:
    - URL button click sets `activeActionRowId` and renders `row-staged-action-strip`.
    - Clicking `btn-action-strip-personal` sets allocation to 100% Personal, triggers success notification, and dismisses strip.
    - Clicking `btn-action-strip-company` opens edit dialog with standard defaults and dismisses strip.
    - Clicking `btn-action-strip-comp-{id}` opens edit dialog with `defaultCompanyId` bound to matching company and dismisses strip.
    - Clicking `btn-action-strip-close` dismisses strip without changing allocation.
    - Keyboard event listener triggers corresponding actions on `x`, `c`, `1`, `Escape` when strip is active.
    - Template structural assertions verify required testids, tooltips, and persistent affordances.
