# Implementation Plan: Vue Component Testing Framework (Vitest + @vue/test-utils + Happy-DOM)

This implementation plan details the engineering deliverables required to establish a modern Vue 3 component testing environment with Vitest, `@vue/test-utils`, `happy-dom`, and a centralized Quasar test harness, as specified in [`specs/14-vue-component-testing/spec.md`](file:///D:/src/personal/wrangler/specs/14-vue-component-testing/spec.md) and aligned with [`specs/ARCHITECTURE.md`](file:///D:/src/personal/wrangler/specs/ARCHITECTURE.md).

---

## Phase 1: Test Environment & Dependencies Configuration

### 1.1 Install Component Testing Dependencies in `web/package.json`
- **Target File:** [`web/package.json`](file:///D:/src/personal/wrangler/web/package.json)
- **Description:** Add `@vue/test-utils` and `happy-dom` to the `devDependencies` of `web/package.json`:
  - `"@vue/test-utils": "^2.4.6"`
  - `"happy-dom": "^17.0.0"`
- **Implementation Steps:**
  1. Add the dependencies to the `devDependencies` block in [`web/package.json`](file:///D:/src/personal/wrangler/web/package.json).
  2. Execute package installation across the workspace using `pnpm install` from the repository root.
  3. Verify dependencies resolve cleanly in `pnpm-lock.yaml`.

### 1.2 Configure Vitest Environment in `web/vite.config.ts`
- **Target File:** [`web/vite.config.ts`](file:///D:/src/personal/wrangler/web/vite.config.ts)
- **Description:** Update the Vite configuration to enable the Vitest test runner with `happy-dom` DOM simulation, global test utilities, and global setup hooks.
- **Implementation Steps:**
  1. Add the triple-slash reference directive `/// <reference types="vitest" />` at the top of the file.
  2. Define the `test` block inside `defineConfig`:
     - `environment: "happy-dom"`: Simulates browser window, document, and DOM standards in a lightweight headless Node process.
     - `globals: true`: Enables Vitest global APIs (`describe`, `it`, `expect`, `vi`, `beforeEach`, `afterEach`).
     - `setupFiles: ["./tests/setup.ts"]`: Specifies the setup file executed before each test suite.
     - `include: ["src/**/*.{test,spec}.ts", "tests/**/*.{test,spec}.ts"]`: Matches both collocated component specifications under `src/` and unit test suites under `tests/`.

### 1.3 Implement Global Environment Setup and Polyfills in `web/tests/setup.ts`
- **Target File:** [`web/tests/setup.ts`](file:///D:/src/personal/wrangler/web/tests/setup.ts)
- **Description:** Create the global setup file to polyfill browser APIs required by Quasar UI components and ensure cross-test DOM isolation.
- **Implementation Steps:**
  1. Create [`web/tests/setup.ts`](file:///D:/src/personal/wrangler/web/tests/setup.ts).
  2. Add `window.matchMedia` polyfill using `vi.fn()` returning standard media query list shape (`matches: false`, `media: query`, `addListener`, `removeListener`, `addEventListener`, `removeEventListener`, `dispatchEvent`).
  3. Polyfill `global.ResizeObserver` with stubbed `observe`, `unobserve`, and `disconnect` mocks.
  4. Polyfill `global.IntersectionObserver` with stubbed `observe`, `unobserve`, `disconnect`, and `takeRecords` mocks.
  5. Add an `afterEach` hook to purge `document.body.innerHTML = ""` preventing DOM leakage across test suites.
  6. Verify all 18 existing test suites in `web/tests/` continue to pass without regressions under `happy-dom`.

---

## Phase 2: Centralized Quasar Test Harness

### 2.1 Implement Quasar Mounting Harness and Body Query Helpers in `web/tests/utils/testHarness.ts`
- **Target File:** [`web/tests/utils/testHarness.ts`](file:///D:/src/personal/wrangler/web/tests/utils/testHarness.ts)
- **Description:** Create a reusable Quasar component mounting utility that standardizes Pinia root initialization, Quasar plugin injection, body container attachment, and DOM query helpers.
- **Implementation Steps:**
  1. Create directory `web/tests/utils/` if it does not already exist.
  2. Define interface `MountWithQuasarOptions<T>` extending `ComponentMountingOptions<T>`:
     - `pinia?: Pinia`: Optional custom Pinia instance (defaulting to fresh `createPinia()`).
     - `attachToBody?: boolean`: Whether to attach the mounted wrapper to `document.body` (defaults to `true`).
  3. Implement and export `mountWithQuasar<T>(component: T, options?: MountWithQuasarOptions<T>): VueWrapper<ComponentPublicInstance & T>`:
     - Initialize `activePinia = pinia || createPinia()` and set via `setActivePinia(activePinia)`.
     - Configure Quasar plugin with standard plugins: `Notify` and `Dialog`.
     - Merge `global.plugins` preserving user-provided plugins.
     - Bind `attachTo: attachToBody ? document.body : undefined`.
     - Return the typed `VueWrapper`.
  4. Implement and export DOM querying helpers for teleported elements:
     - `findInBody<T extends Element = HTMLElement>(selector: string): T | null`: Queries an element inside `document.body`.
     - `findAllInBody<T extends Element = HTMLElement>(selector: string): T[]`: Queries all elements matching selector inside `document.body`.

---

## Phase 3: Reference Component Specifications & Migration

### 3.1 Implement Mounted Component Specification for `BulkAllocateDialog`
- **Target File:** [`web/src/components/__tests__/BulkAllocateDialog.spec.ts`](file:///D:/src/personal/wrangler/web/src/components/__tests__/BulkAllocateDialog.spec.ts)
- **Description:** Refactor the test suite from legacy `fs.readFileSync` template string assertions into a comprehensive mounted Vue component specification using `mountWithQuasar`.
- **Implementation Steps:**
  1. Remove all `fs.readFileSync`, `path.resolve`, and raw regex template inspection code.
  2. Implement mounted component test cases verifying:
     - **Rendering & Structure:** Mount dialog with `modelValue: true` and staged transactions. Assert dialog title, item count caption, radio options (`[data-testid="radio-personal"]`, `[data-testid="radio-company"]`, `[data-testid="radio-clear"]`), and action buttons render in the DOM.
     - **Notice Banner Reactivity:** Verify `[data-testid="banner-overwrite-warning"]` renders and displays the correct count when staged transactions have existing allocations. Verify the banner is absent when transactions have no allocations.
     - **Entity Selection & Input Controls:** Verify selecting the "Company" radio displays `[data-testid="select-company"]`; verify selecting "Personal" or "Clear" hides the company selector.
     - **Button Disabled States:** Verify `[data-testid="btn-apply-allocation"]` is disabled when `selectedTransactions` is empty. Verify it is disabled when "Company" is selected without a chosen company ID. Verify it is enabled when "Personal" is selected with valid transactions.
     - **Action Dispatch & Event Emissions:** Mock `apiClient.post` for `/api/staging/bulk-allocate`. Click Apply button. Assert `apiClient.post` was called with expected payload (`staged_transaction_ids`, `is_personal`, `company_id`, `clear`). Assert `applied` and `update:modelValue` (`false`) events are emitted. Assert Quasar `Notify` toast was triggered.
     - **Cancel / Close:** Click `[data-testid="btn-cancel-allocation"]`. Assert no API calls were made and the dialog closes.
  3. Retain pure unit test suites for `countOverwrittenTransactions` and `buildBulkAllocatePayload`.

### 3.2 Migrate and Implement Mounted Component Specification for `BulkCategorizeDialog`
- **Target Files:**
  - Create: [`web/src/components/__tests__/BulkCategorizeDialog.spec.ts`](file:///D:/src/personal/wrangler/web/src/components/__tests__/BulkCategorizeDialog.spec.ts)
  - Remove: [`web/tests/bulkCategorizeDialog.test.ts`](file:///D:/src/personal/wrangler/web/tests/bulkCategorizeDialog.test.ts)
- **Description:** Relocate `BulkCategorizeDialog` testing to collocated component specs in `web/src/components/__tests__/` and replace legacy string-based checks with mounted DOM component tests.
- **Implementation Steps:**
  1. Create [`web/src/components/__tests__/BulkCategorizeDialog.spec.ts`](file:///D:/src/personal/wrangler/web/src/components/__tests__/BulkCategorizeDialog.spec.ts) importing `mountWithQuasar` and `BulkCategorizeDialog.vue`.
  2. Implement mounted component test cases verifying:
     - **Rendering & Structure:** Mount with `modelValue: true`, selected allocation rows, and Wave categories. Assert dialog title, category selector (`[data-testid="select-bulk-category"]`), and action buttons are present in the DOM.
     - **Warning Banner Reactivity:** Mount with rows where some have `wave_category_id`; verify `[data-testid="banner-overwrite-warning"]` is visible with correct count. Mount with unassigned rows; verify warning banner is not rendered.
     - **Category Selection & Disabled States:** Verify `[data-testid="btn-apply-bulk-category"]` is disabled when no category is selected or when `selectedRows` is empty. Verify Apply button becomes enabled once a valid category is selected.
     - **Action Dispatch & Event Emissions:** Mock `apiClient.post` for `/api/allocations/bulk-category`. Trigger Apply button click. Assert `transactionStore.bulkUpdateAllocationCategory` dispatches `/api/allocations/bulk-category` with matching `allocation_ids` and `wave_category_id`. Assert `applied` and `update:modelValue` (`false`) events are emitted. Assert Quasar `Notify` toast is triggered.
     - **Cancel / Close:** Verify clicking `[data-testid="btn-cancel-bulk-category"]` closes the dialog without dispatching API requests.
  3. Retain pure helper unit tests for `countOverwrittenCategories` and category option filtering.
  4. Delete the deprecated test file [`web/tests/bulkCategorizeDialog.test.ts`](file:///D:/src/personal/wrangler/web/tests/bulkCategorizeDialog.test.ts).

### 3.3 Migrate and Implement Mounted Component Specification for `StagedTransactionEditDialog`
- **Target Files:**
  - Create: [`web/src/components/__tests__/stagedTransactionEdit.test.ts`](file:///D:/src/personal/wrangler/web/src/components/__tests__/stagedTransactionEdit.test.ts)
  - Create: [`web/src/components/__tests__/StagedTransactionEditDialog.spec.ts`](file:///D:/src/personal/wrangler/web/src/components/__tests__/StagedTransactionEditDialog.spec.ts)
  - Remove: [`web/src/components/__tests__/stagedTransactionEdit.spec.ts`](file:///D:/src/personal/wrangler/web/src/components/__tests__/stagedTransactionEdit.spec.ts)
- **Description:** Split calculation helper unit tests into `stagedTransactionEdit.test.ts` and replace the UI regex string inspection tests with a mounted DOM component specification in `StagedTransactionEditDialog.spec.ts` using `mountWithQuasar`.
- **Implementation Steps:**
  1. Extract pure calculation and state helper unit tests (initialization, personal/business toggle, split balancing, receipt state, URL trimming, AI suggestion computation and dismissal) from [`stagedTransactionEdit.spec.ts`](file:///D:/src/personal/wrangler/web/src/components/__tests__/stagedTransactionEdit.spec.ts) into [`web/src/components/__tests__/stagedTransactionEdit.test.ts`](file:///D:/src/personal/wrangler/web/src/components/__tests__/stagedTransactionEdit.test.ts).
  2. Create mounted component specification [`web/src/components/__tests__/StagedTransactionEditDialog.spec.ts`](file:///D:/src/personal/wrangler/web/src/components/__tests__/StagedTransactionEditDialog.spec.ts) using `mountWithQuasar` to test `StagedTransactionEditDialog.vue`:
     - **Persistent Affordances & Receipt Controls (Spatial Stability):** Mount with a staged transaction without a receipt (`receipt_file_path: null`). Assert `[data-testid="btn-staged-view-receipt"]` and `[data-testid="btn-staged-scan-receipt"]` exist in rendered DOM with disabled attributes and are not conditionally removed by `v-if`. Mount with an attached receipt file path and assert both buttons are enabled.
     - **Clearable Receipt Attachment:** Mount with a staged receipt. Emit `@clear` on `[data-testid="input-staged-receipt"]`. Assert receipt state is marked for removal and suggestions are cleared.
     - **Interactive AI Field Suggestions:** Mount with active AI suggestions for date, total_amount, and description. Assert suggestion action buttons and match indicators render in DOM. Click `btn-accept-suggestion-date` and verify the date input reactively updates to suggested value and match indicator appears. Click `btn-dismiss-suggestion-description` and verify the description suggestion banner is dismissed from view.
     - **Investigation URL Link:** Mount with staged transaction containing a URL. Assert external link button `btn-open-url` is rendered in input append slot with `target="_blank"`, `rel="noopener noreferrer"`, and tooltip.
     - **Split Balance Validation & Save Flow:** Verify Save button is disabled when allocation splits do not balance the total amount. Set valid balanced splits and click Save button; assert store action receives prepared payload and dialog emits `saved`.
  3. Delete the legacy hybrid specification file [`web/src/components/__tests__/stagedTransactionEdit.spec.ts`](file:///D:/src/personal/wrangler/web/src/components/__tests__/stagedTransactionEdit.spec.ts).
