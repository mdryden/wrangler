---
status: Implemented
subsystems:
  - Platform & Shell
amendments: []
supersedes: null
superseded_by: null
---

# Specification: Vue Component Testing Framework (Vitest + @vue/test-utils + Happy-DOM)

## 1. Overview & Objectives

Wrangler currently utilizes Vitest for running store, utility, and API client tests in the `web/` package. However, because no DOM simulation environment or component mounting harness was configured, UI testing was forced into a fragile string-matching anti-pattern: reading `.vue` Single File Components from the disk via `fs.readFileSync` and asserting against raw template strings and regexes.

This specification establishes a robust, modern Vue 3 component testing framework for Wrangler using **Vitest**, **`@vue/test-utils` (v2)**, and **`happy-dom`**, complete with a centralized **Quasar test harness** (`mountWithQuasar`) that handles Quasar UI plugins (`Notify`, `Dialog`), teleported elements (`<q-dialog>`), Pinia state, and Vue Router integration.

### Core Objectives
1. **Real Component Mounting & Interaction:** Enable true DOM-level mounting of Vue 3 components, firing simulated user events (`click`, `input`, `select`), testing reactive property updates, and inspecting rendered DOM outputs.
2. **Quasar Compatibility:** Provide seamless support for Quasar components and plugins (`QDialog`, `QBtn`, `QSelect`, `Notify`, `Dialog`) without manual per-test boilerplate.
3. **Teleport Support:** Enable seamless DOM querying for Quasar dialogs and overlays that teleport to `document.body`.
4. **Integration-First Store Testing:** Establish a standard pattern where components interact with real Pinia stores and mocked API boundaries, verifying end-to-end user flows while also supporting isolated store mocks where needed.
5. **Reference Implementations:** Migrate [`BulkAllocateDialog`](file:///D:/src/personal/wrangler/web/src/components/BulkAllocateDialog.vue), [`BulkCategorizeDialog`](file:///D:/src/personal/wrangler/web/src/components/BulkCategorizeDialog.vue), and [`StagedTransactionEditDialog`](file:///D:/src/personal/wrangler/web/src/components/StagedTransactionEditDialog.vue) from template-string checks to full rendered component specifications.

---

## 2. Architectural Invariants & Scope Boundaries

### Non-Negotiable Invariants
- **Zero Backend / Database Impact:** This feature is strictly constrained to the frontend test tooling and configuration under `web/`. No changes to `api/` or SQLite schemas are permitted.
- **Fast Headless Execution:** Tests must run entirely in a headless Node process via `happy-dom` without spawning external browser binaries (Playwright/Chrome).
- **Test Command Compatibility:** `pnpm test`, `pnpm test:changed`, `pnpm --filter web test`, and `pnpm --filter web test:changed` must execute cleanly without special flags or interactive prompts.
- **Backwards Compatibility:** All existing 18 test suites in `web/tests/` (testing pure stores, helpers, and API clients) must continue to pass without regressions under `happy-dom`.

### Scope Boundary
- **In-Scope (Targeted Phase):**
  - Installing `@vue/test-utils` and `happy-dom` in `web/package.json`.
  - Configuring `web/vite.config.ts` (or `vitest.config.ts`) with `environment: 'happy-dom'` and a global setup file.
  - Creating `web/tests/setup.ts` with browser API polyfills/shims required by Quasar (e.g. `matchMedia`, `ResizeObserver`).
  - Creating `web/tests/utils/testHarness.ts` exporting `mountWithQuasar` and dialog cleanup helpers.
  - Rewriting [`web/src/components/__tests__/BulkAllocateDialog.spec.ts`](file:///D:/src/personal/wrangler/web/src/components/__tests__/BulkAllocateDialog.spec.ts) to mount and test `BulkAllocateDialog.vue`.
  - Migrating `web/tests/bulkCategorizeDialog.test.ts` into a mounted component specification `web/src/components/__tests__/BulkCategorizeDialog.spec.ts`.
  - Splitting [`web/src/components/__tests__/stagedTransactionEdit.spec.ts`](file:///D:/src/personal/wrangler/web/src/components/__tests__/stagedTransactionEdit.spec.ts): retaining pure calculation helper tests in `stagedTransactionEdit.test.ts` and rewriting the UI template regex assertions into a mounted component specification `web/src/components/__tests__/StagedTransactionEditDialog.spec.ts`.
- **Out-of-Scope (Deferred):**
  - Full rewrite of all other legacy string-based tests (e.g. `ManualEntryView`, `ImportView`, `MainLayout`). These will be incrementally modernized in follow-up specs or during active feature changes touching those views.
  - End-to-end browser testing (Playwright E2E).

---

## 3. Technology Stack & Dependencies

### Package Additions (`web/package.json`)
The following devDependencies must be added to `web/package.json`:

```json
{
  "devDependencies": {
    "@vue/test-utils": "^2.4.6",
    "happy-dom": "^17.0.0"
  }
}
```

- **`@vue/test-utils`:** Official Vue 3 testing library providing `mount`, `shallowMount`, DOM querying (`wrapper.find`, `wrapper.findAll`), and event triggers (`wrapper.trigger`).
- **`happy-dom`:** Lightweight, high-performance DOM implementation for Node.js, providing `window`, `document`, and web standard APIs necessary for Vue and Quasar rendering.

---

## 4. Configuration & Global Test Setup

### 4.1 Vitest Configuration (`web/vite.config.ts`)
Update `web/vite.config.ts` to configure the Vitest test environment and setup file:

```typescript
/// <reference types="vitest" />
import { defineConfig } from "vite"
import vue from "@vitejs/plugin-vue"
import { quasar, transformAssetUrls } from "@quasar/vite-plugin"

export default defineConfig({
  plugins: [
    vue({
      template: { transformAssetUrls },
    }),
    quasar({
      devTreeshaking: true,
    }),
  ],
  test: {
    environment: "happy-dom",
    globals: true,
    setupFiles: ["./tests/setup.ts"],
    include: [
      "src/**/*.{test,spec}.ts",
      "tests/**/*.{test,spec}.ts",
    ],
  },
  server: {
    port: 3000,
    proxy: {
      "/api": {
        target: "http://localhost:8000",
        changeOrigin: true,
      },
    },
  },
})
```

### 4.2 Global Test Setup File (`web/tests/setup.ts`)
Quasar components often access browser environment APIs (`window.matchMedia`, `ResizeObserver`, `IntersectionObserver`) that may be missing or partially implemented in Node DOM environments. The setup file ensures these are polyfilled cleanly:

```typescript
import { afterEach, vi } from "vitest"

// Polyfill window.matchMedia for Quasar responsive layout checks
if (typeof window !== "undefined") {
  Object.defineProperty(window, "matchMedia", {
    writable: true,
    value: vi.fn().mockImplementation(query => ({
      matches: false,
      media: query,
      onchange: null,
      addListener: vi.fn(), // deprecated
      removeListener: vi.fn(), // deprecated
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      dispatchEvent: vi.fn(),
    })),
  })

  // Polyfill ResizeObserver
  global.ResizeObserver = class ResizeObserver {
    observe = vi.fn()
    unobserve = vi.fn()
    disconnect = vi.fn()
  } as unknown as typeof ResizeObserver

  // Polyfill IntersectionObserver
  global.IntersectionObserver = class IntersectionObserver {
    observe = vi.fn()
    unobserve = vi.fn()
    disconnect = vi.fn()
    takeRecords = vi.fn().mockReturnValue([])
  } as unknown as typeof IntersectionObserver
}

// Clean up DOM between test runs to avoid cross-test element leaks
afterEach(() => {
  document.body.innerHTML = ""
})
```

---

## 5. Test Harness Design (`mountWithQuasar`)

To avoid repetitive mounting boilerplate across component tests, a centralized test harness module must be created at `web/tests/utils/testHarness.ts`.

### 5.1 Harness Interface & Responsibilities
The harness must:
1. Initialize a fresh Pinia root instance by default (or accept a custom Pinia instance, e.g. `createTestingPinia`).
2. Register the Quasar Vue plugin with standard plugins: `Notify` and `Dialog`.
3. Provide an isolated mount container attached to `document.body` so teleported elements (`<q-dialog>`, `<q-menu>`, `<q-tooltip>`) are reachable via DOM queries.
4. Export utility functions for locating teleported dialogs and dismissing open overlays.

```typescript
// web/tests/utils/testHarness.ts
import { mount, type ComponentMountingOptions, type VueWrapper } from "@vue/test-utils"
import { Quasar, Notify, Dialog } from "quasar"
import { createPinia, setActivePinia, type Pinia } from "pinia"
import type { ComponentPublicInstance } from "vue"

export interface MountWithQuasarOptions<T> extends ComponentMountingOptions<T> {
  pinia?: Pinia
  attachToBody?: boolean
}

/**
 * Mounts a Vue component with Quasar plugins and Pinia configured.
 */
export function mountWithQuasar<T>(
  component: T,
  options: MountWithQuasarOptions<T> = {},
): VueWrapper<ComponentPublicInstance & T> {
  const { pinia, attachToBody = true, global = {}, ...mountOptions } = options

  // Set active Pinia (default to a fresh root if not provided)
  const activePinia = pinia || createPinia()
  setActivePinia(activePinia)

  const plugins = [
    activePinia,
    [Quasar, { plugins: { Notify, Dialog } }],
    ...(global.plugins || []),
  ]

  const container = attachToBody ? document.body : undefined

  return mount(component as any, {
    attachTo: container,
    global: {
      ...global,
      plugins,
    },
    ...mountOptions,
  }) as VueWrapper<ComponentPublicInstance & T>
}

/**
 * Helper to query elements teleported to document.body (e.g., active QDialog contents).
 */
export function findInBody<T extends Element = HTMLElement>(selector: string): T | null {
  return document.body.querySelector<T>(selector)
}

/**
 * Helper to query all elements teleported to document.body.
 */
export function findAllInBody<T extends Element = HTMLElement>(selector: string): T[] {
  return Array.from(document.body.querySelectorAll<T>(selector))
}
```

---

## 6. Directory & Naming Conventions

To ensure consistent project structure and high discoverability:

1. **Component Specifications:**
   - Collocated in `__tests__/` subdirectories adjacent to the target component:
     - `web/src/components/__tests__/<ComponentName>.spec.ts`
     - `web/src/views/__tests__/<ViewName>.spec.ts`
   - Use the `.spec.ts` extension to denote mounted behavior and DOM specifications.
2. **Unit / Store / Helper Tests:**
   - Pure state machines, API wrappers, calculation helpers, and router tests remain in `web/tests/`.
   - Use the `.test.ts` extension.
3. **Test Utility Helpers:**
   - Centralized in `web/tests/utils/`.

---

## 7. Reference Implementations

Three critical dialog components will be implemented using the new framework to serve as reference examples for the codebase:

### 7.1 `BulkAllocateDialog.spec.ts`
**Target File:** `web/src/components/__tests__/BulkAllocateDialog.spec.ts`

**Tests to Implement (Replacing string-inspection tests):**
1. **Rendering & Structure:**
   - Mount with `modelValue: true` and a list of staged transactions.
   - Assert that the dialog header, subtitle, radio options, and action buttons are rendered in the DOM (using `data-testid`).
2. **Notice Banner Reactivity:**
   - When mounted with transactions that have existing allocations, assert `[data-testid="banner-overwrite-warning"]` exists and displays the correct count.
   - When mounted with unallocated transactions, assert the overwrite banner is absent from the DOM.
3. **Entity Selection & Input Controls:**
   - Selecting "Company" (`data-testid="radio-company"`) reveals the company selector (`data-testid="select-company"`).
   - Selecting "Personal" (`data-testid="radio-personal"`) hides the company selector.
   - Selecting "Clear" (`data-testid="radio-clear"`) hides the company selector.
4. **Button Disabled States:**
   - Assert `btn-apply-allocation` is disabled when `selectedTransactions` is empty.
   - Assert `btn-apply-allocation` is disabled when "Company" is selected but no company is chosen.
   - Assert `btn-apply-allocation` is enabled when "Personal" is selected with valid transactions.
5. **Action Dispatch & Event Emissions:**
   - Mock `apiClient.post`.
   - Click `btn-apply-allocation`.
   - Verify `apiClient.post` was called with `/api/staging/bulk-allocate` and the correct payload.
   - Verify `applied` and `update:modelValue` (with `false`) events were emitted.
   - Verify Quasar `Notify` toast was triggered.
6. **Cancel / Close:**
   - Click `btn-cancel-allocation`.
   - Verify no API calls were made and the dialog closes.

### 7.2 `BulkCategorizeDialog.spec.ts`
**Target File:** `web/src/components/__tests__/BulkCategorizeDialog.spec.ts` (migrated from `web/tests/bulkCategorizeDialog.test.ts`)

**Tests to Implement (Replacing string-inspection tests):**
1. **Rendering & Structure:**
   - Mount with `modelValue: true`, selected allocation rows, and categories.
   - Assert dialog title, category selector (`data-testid="select-bulk-category"`), and action buttons are present in the DOM.
2. **Warning Banner Reactivity:**
   - Mount with rows where some already have `wave_category_id`. Assert warning banner is visible.
   - Mount with rows having no assigned categories. Assert warning banner is not rendered.
3. **Category Selection & Disabled State:**
   - With no category selected, verify `btn-apply-bulk-category` has `:disable="true"`.
   - Update model to a valid category ID, verify Apply button becomes enabled.
4. **Action Dispatch & Event Emissions:**
   - Mock `apiClient.post`.
   - Trigger Apply button click.
   - Verify store action calls `/api/transactions/bulk-category`.
   - Verify `applied` and `update:modelValue` (with `false`) events are emitted.
   - Verify Quasar `Notify` toast is displayed.
5. **Pure Helper Functions:**
   - Retain unit tests for `countOverwrittenCategories` and option filtering alongside the component tests.

### 7.3 `StagedTransactionEditDialog.spec.ts`
**Target File:** `web/src/components/__tests__/StagedTransactionEditDialog.spec.ts`
*(Note: Pure calculation helper unit tests remain in `web/src/components/__tests__/stagedTransactionEdit.test.ts`)*

**Tests to Implement (Replacing string-inspection and regex matching):**
1. **Persistent Affordances & Receipt Controls (Spatial Stability):**
   - Mount with a staged transaction having no receipt (`receipt_file_path: null`).
   - Assert `[data-testid="btn-staged-view-receipt"]` and `[data-testid="btn-staged-scan-receipt"]` exist in the rendered DOM and have attribute `:disable="true"` / `disabled`.
   - Assert neither button was conditionally removed by `v-if`.
   - Mount with a staged transaction having a receipt file path. Assert both buttons are enabled.
2. **Clearable Receipt Attachment:**
   - Mount with a staged receipt. Emit `@clear` on `[data-testid="input-staged-receipt"]`.
   - Assert receipt state is marked for removal and suggestions are cleared.
3. **Interactive AI Field Suggestions:**
   - Mount with AI suggestions for date, total_amount, and description.
   - Assert suggestion banners and match indicators are rendered.
   - Click `btn-accept-suggestion-date` $\rightarrow$ verify form input for date reactively updates to the suggested value and the match indicator appears.
   - Click `btn-dismiss-suggestion-description` $\rightarrow$ verify the description suggestion banner is dismissed from view.
4. **Investigation URL Link:**
   - When staged transaction includes a `url`, verify external link button `btn-open-url` is rendered in the input append slot with `target="_blank"`, `rel="noopener noreferrer"`, and tooltip.
5. **Split Balance Validation & Save Flow:**
   - Assert Save button is disabled when allocation splits do not balance the total amount.
   - Set valid balanced splits and click Save $\rightarrow$ verify store action receives the prepared payload and the dialog emits `saved`.

---

## 8. Verification Scenarios & Acceptance Criteria

### Automated Verification Matrix

| Scenario | Command | Expected Outcome |
| :--- | :--- | :--- |
| **All Web Tests** | `pnpm --filter web test` | All test suites (existing unit tests + new component specs) pass with 100% success. |
| **Changed Files Only** | `pnpm --filter web test:changed` | Fast incremental test execution succeeds on touched files. |
| **Full Workspace Test Suite** | `pnpm test` | Runs both `api` (pytest) and `web` (vitest) cleanly without errors. |
| **Frontend Typecheck & Lint** | `pnpm --filter web lint` | `vue-tsc` typechecking passes with zero TypeScript errors on all test files and harness code. |
| **Frontend Code Formatting** | `pnpm --filter web format` | Prettier check passes without formatting violations. |

### Architectural Acceptance Criteria
- [ ] No `fs.readFileSync` or raw template regex checks remain in `BulkAllocateDialog.spec.ts`, `BulkCategorizeDialog.spec.ts`, or `stagedTransactionEdit.spec.ts`.
- [ ] Pure calculation unit tests for `stagedTransactionEdit.ts` are preserved 100% in `stagedTransactionEdit.test.ts`.
- [ ] Quasar components mount with their real reactive DOM structures across all three reference dialogs.
- [ ] Teleported dialog contents are successfully queried and interacted with via `happy-dom`.
- [ ] Existing non-component test suites in `web/tests/` (16 other test files) pass with zero modifications or regressions.
- [ ] Running `pnpm test` finishes under standard developer time expectations (<10 seconds).
