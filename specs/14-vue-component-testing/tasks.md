# Tasks: Vue Component Testing Framework (Vitest + @vue/test-utils + Happy-DOM)

## Phase 1: Test Environment & Dependencies Configuration
- [x] 1.1 Install component testing dependencies in `web/package.json`
- [x] 1.2 Configure Vitest environment in `web/vite.config.ts`
- [x] 1.3 Implement global environment setup and polyfills in `web/tests/setup.ts`

## Phase 2: Centralized Quasar Test Harness
- [x] 2.1 Implement Quasar mounting harness and body query helpers in `web/tests/utils/testHarness.ts`

## Phase 3: Reference Component Specifications & Migration
- [x] 3.1 Implement mounted component specification for `BulkAllocateDialog` in `web/src/components/__tests__/BulkAllocateDialog.spec.ts`
- [x] 3.2 Migrate and implement mounted component specification for `BulkCategorizeDialog` in `web/src/components/__tests__/BulkCategorizeDialog.spec.ts` and remove `web/tests/bulkCategorizeDialog.test.ts`
- [x] 3.3 Migrate and implement mounted component specification for `StagedTransactionEditDialog` in `web/src/components/__tests__/StagedTransactionEditDialog.spec.ts`, preserve helper tests in `web/src/components/__tests__/stagedTransactionEdit.test.ts`, and remove `web/src/components/__tests__/stagedTransactionEdit.spec.ts`
