# Implementation Plan: Collapsible Icon-Rail Sidebar Navigation

This implementation plan details the engineering deliverables required to transition the Wrangler desktop navigation to a full-height collapsible sidebar with a 60px icon rail and a dedicated external trigger button in the main header toolbar, as specified in [`specs/v2/7-collapsible-sidebar/spec.md`](file:///D:/src/personal/wrangler/specs/v2/7-collapsible-sidebar/spec.md).

The plan is organized into sequential phases and atomic implementation tasks. Each task specifies concrete deliverables and automated test coverage in [`web/tests/`](file:///D:/src/personal/wrangler/web/tests/) adhering to project conventions and development standards defined in [`AGENTS.md`](file:///D:/src/personal/wrangler/AGENTS.md).

---

## Phase 1: Persistent Pinia Application Store

*Goal:* Equip the Pinia application store with reactive, persistent sidebar state across page reloads and browser sessions.

### 1.1 Pinia App Store Sidebar State & LocalStorage Persistence
- In [`web/src/stores/app.ts`](file:///D:/src/personal/wrangler/web/src/stores/app.ts):
  - Export constant `STORAGE_KEY_SIDEBAR_COLLAPSED = "wrangler_sidebar_collapsed"`.
  - Safely retrieve initial persistence value using `typeof window !== "undefined"` guard:
    - `storedCollapsed = typeof window !== "undefined" ? localStorage.getItem(STORAGE_KEY_SIDEBAR_COLLAPSED) === "true" : false`.
  - Declare reactive state: `const sidebarCollapsed = ref<boolean>(storedCollapsed)`.
  - Implement action `toggleSidebar(): void`:
    - Negates `sidebarCollapsed.value`.
    - If `typeof window !== "undefined"`, writes `localStorage.setItem(STORAGE_KEY_SIDEBAR_COLLAPSED, String(sidebarCollapsed.value))`.
  - Implement action `setSidebarCollapsed(collapsed: boolean): void`:
    - Assigns `sidebarCollapsed.value = collapsed`.
    - If `typeof window !== "undefined"`, writes `localStorage.setItem(STORAGE_KEY_SIDEBAR_COLLAPSED, String(collapsed))`.
  - Return `sidebarCollapsed`, `toggleSidebar`, and `setSidebarCollapsed` alongside existing `appName` and `initialized` refs from [`useAppStore`](file:///D:/src/personal/wrangler/web/src/stores/app.ts).

### 1.2 App Store Unit Test Suite
- In [`web/tests/appStore.test.ts`](file:///D:/src/personal/wrangler/web/tests/appStore.test.ts):
  - Create new Vitest test suite testing [`useAppStore`](file:///D:/src/personal/wrangler/web/src/stores/app.ts) using in-memory `localStorage` mock and active Pinia instances reset in `beforeEach`.
  - Implement test verifying default initial state: when `localStorage` has no record, `sidebarCollapsed` is `false`.
  - Implement test verifying persisted initial state: when `localStorage.getItem("wrangler_sidebar_collapsed")` is `"true"`, `sidebarCollapsed` initializes to `true`.
  - Implement test verifying `toggleSidebar()` flips state from `false` to `true` and writes `"true"` to `localStorage`, and subsequent invocation flips back to `false` and writes `"false"`.
  - Implement test verifying `setSidebarCollapsed(true)` and `setSidebarCollapsed(false)` directly updates `sidebarCollapsed` and synchronizes with `localStorage`.

---

## Phase 2: Collapsible Sidebar Layout, Dedicated External Trigger & Hotkey Navigation

*Goal:* Update the application layout to full-height left drawer mode (`view="lHh Lpr lFf"`), replace the header hamburger button with the dedicated external `panel-left` trigger, move application branding to the top of the sidebar, render mini-mode contextual tooltips, and register global keyboard hotkey toggling (`Ctrl+B` / `Cmd+B`).

### 2.1 Full-Height Layout View, Docked Drawer & Sidebar Branding
- In [`web/src/layouts/MainLayout.vue`](file:///D:/src/personal/wrangler/web/src/layouts/MainLayout.vue):
  - Update `<q-layout view="...">` from `"hHh Lpr fFf"` to `"lHh Lpr lFf"`.
  - Update `<q-drawer>` configuration attributes:
    - `:mini="appStore.sidebarCollapsed"`
    - `:mini-width="60"`
    - `:width="240"`
    - `:breakpoint="0"` (permanently docks sidebar on desktop)
    - `v-model="drawerOpen"` (bound to `const drawerOpen = ref<boolean>(true)`)
    - `show-if-above`, `bordered`, `side="left"`, `class="bg-grey-1 text-grey-8"`
  - Relocate application branding from `<q-toolbar>` to the top of `<q-scroll-area class="fit">` inside `<q-drawer>`:
    - Container row with `class="row items-center q-px-md q-py-md cursor-pointer no-wrap"` and conditional alignment `:class="appStore.sidebarCollapsed ? 'justify-center' : 'justify-start'"` that routes to `ledger` on click.
    - Wallet icon: `<q-icon name="account_balance_wallet" size="sm" color="primary" />`.
    - Title text: `<span v-show="!appStore.sidebarCollapsed" class="text-subtitle1 text-weight-bold text-grey-9 q-ml-sm">Wrangler</span>`.
    - Horizontal divider: `<q-separator />`.
  - Wrap navigation section label `<q-item-label header ...>Navigation</q-item-label>` with `v-show="!appStore.sidebarCollapsed"`.

### 2.2 Dedicated External Sidebar Trigger Button & Mini-Rail Tooltips
- In [`web/src/layouts/MainLayout.vue`](file:///D:/src/personal/wrangler/web/src/layouts/MainLayout.vue):
  - In `<q-header>` > `<q-toolbar>`, remove the legacy hamburger `<q-btn icon="menu">`.
  - Add the dedicated external sidebar trigger button as the first toolbar child, flush against the drawer separator border:
    - Button styling: `<q-btn flat dense round class="q-mr-sm" aria-label="Toggle sidebar" :title="appStore.sidebarCollapsed ? 'Expand sidebar (Ctrl+B)' : 'Collapse sidebar (Ctrl+B)'" @click="appStore.toggleSidebar">`.
    - Panel-left SVG icon:
      ```html
      <svg
        xmlns="http://www.w3.org/2000/svg"
        width="20"
        height="20"
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        stroke-width="2"
        stroke-linecap="round"
        stroke-linejoin="round"
      >
        <rect width="18" height="18" x="3" y="3" rx="2" />
        <path d="M9 3v18" />
      </svg>
      ```
    - Trigger button tooltip:
      ```html
      <q-tooltip anchor="bottom right" self="top left" :offset="[8, 8]">
        {{ appStore.sidebarCollapsed ? 'Expand sidebar (Ctrl+B)' : 'Collapse sidebar (Ctrl+B)' }}
      </q-tooltip>
      ```
  - In `<q-drawer>` > `<q-list>` navigation items:
    - Ensure item container has `class="rounded-borders q-mx-xs q-mb-xs"`.
    - Set avatar section styling: `<q-item-section avatar style="min-width: 40px"><q-icon :name="item.icon" size="sm" /></q-item-section>`.
    - Add contextual floating tooltip for mini rail mode:
      ```html
      <q-tooltip
        v-if="appStore.sidebarCollapsed"
        anchor="center right"
        self="center left"
        :offset="[14, 14]"
        class="bg-grey-9 text-white shadow-3 text-caption text-weight-medium"
      >
        {{ item.label }}
      </q-tooltip>
      ```

### 2.3 Global Keyboard Shortcut (`Ctrl+B` / `Cmd+B`) with Input Target Guarding
- In [`web/src/layouts/MainLayout.vue`](file:///D:/src/personal/wrangler/web/src/layouts/MainLayout.vue):
  - In `<script setup lang="ts">`, import `onMounted`, `onUnmounted` from `"vue"` and `useAppStore` from `"../stores/app"`.
  - Implement `handleKeydown(event: KeyboardEvent): void`:
    - Check if hotkey matches: `(event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "b"`.
    - Check target element: `const target = event.target as HTMLElement | null`. If `target && (target.tagName === "INPUT" || target.tagName === "TEXTAREA" || target.isContentEditable)`, return immediately without intercepting.
    - Call `event.preventDefault()` to prevent browser bookmarks bar hotkey behavior.
    - Invoke `appStore.toggleSidebar()`.
  - Register listener in lifecycle hooks:
    - `onMounted(() => { window.addEventListener("keydown", handleKeydown) })`.
    - `onUnmounted(() => { window.removeEventListener("keydown", handleKeydown) })`.

---

## Phase 3: Layout Unit & Integration Tests

*Goal:* Expand the frontend layout test suite to verify hotkey handling, input element guards, layout configuration contracts, and navigation item preservation.

### 3.1 Keyboard Shortcut Hotkey & Input Guard Unit Tests
- In [`web/tests/layout.test.ts`](file:///D:/src/personal/wrangler/web/tests/layout.test.ts):
  - Add test suite verifying hotkey handling behavior with `useAppStore` and mocked DOM events.
  - Verify `(ctrlKey: true, key: "b")` triggers `appStore.toggleSidebar()` and calls `event.preventDefault()`.
  - Verify `(metaKey: true, key: "b")` (macOS hotkey) triggers `appStore.toggleSidebar()` and calls `event.preventDefault()`.
  - Verify keydown events originating from typing targets (`<input>`, `<textarea>`, and elements with `contenteditable="true"`) are ignored and do not invoke `toggleSidebar()`.
  - Verify non-matching key combinations (e.g., plain `"b"`, `Ctrl+A`, `Alt+B`) do not invoke `toggleSidebar()`.

### 3.2 Layout Template & Navigation Rail Specification Unit Tests
- In [`web/tests/layout.test.ts`](file:///D:/src/personal/wrangler/web/tests/layout.test.ts):
  - Preserve existing navigation configuration tests verifying all 5 primary items (`ledger`, `import`, `manual-entry`, `export-manager`, `settings`).
  - Add structural contract assertions verifying:
    - Layout view configuration specifies `"lHh Lpr lFf"`.
    - Drawer settings specify `:mini-width="60"`, `:width="240"`, and `:breakpoint="0"`.
    - External trigger button contains Lucide `panel-left` SVG markup (`<rect width="18" height="18" ...>` and `<path d="M9 3v18" />`) and `aria-label="Toggle sidebar"`.
    - External trigger tooltip displays dynamic hotkey instructions (`Expand sidebar (Ctrl+B)` / `Collapse sidebar (Ctrl+B)`).
    - Top branding header is relocated inside drawer scroll area with wallet icon and title.
    - Navigation rail items include contextual tooltips guarded by `sidebarCollapsed`.
