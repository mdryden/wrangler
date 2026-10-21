# Task Checklist: Staged Bulk Allocations & Actions

## Phase 1: Backend Schemas, Endpoints & Automated Pytest Suite
- [x] 1.1 Request and Response Pydantic Schemas for Bulk Staging Actions in `api/src/schemas/staging.py`
- [x] 1.2 Bulk Allocation Endpoint in Staging Router in `api/src/routers/staging.py`
- [x] 1.3 Bulk Dismiss Endpoint in Staging Router in `api/src/routers/staging.py`
- [x] 1.4 Backend Automated Pytest Suite in `api/tests/test_staging_api.py`

## Phase 2: Frontend Data Contracts & Store Methods
- [x] 2.1 Frontend TypeScript Types in `web/src/types/staging.ts`
- [x] 2.2 Staging Store Actions in `web/src/stores/staging.ts`

## Phase 3: Bulk Allocation Dialog Component
- [x] 3.1 Bulk Allocation Dialog Component & Logic in `web/src/components/BulkAllocateDialog.vue`
- [x] 3.2 Bulk Allocation Dialog Automated Tests in `web/src/components/__tests__/BulkAllocateDialog.spec.ts`

## Phase 4: Staging Table Selection & Contextual Bulk Action Bar in ImportView
- [x] 4.1 Decoupled Selection & Master Header Checkbox in `web/src/views/ImportView.vue` and `web/src/views/importView.ts`
- [x] 4.2 Contextual Bulk Action Toolbar & Dialog Integration in `web/src/views/ImportView.vue`
- [x] 4.3 Frontend Vitest Integration Tests in `web/tests/stagingBulkActions.test.ts`
