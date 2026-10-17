# Implementation Tasks

This file tracks the execution progress of the tasks defined in [plan.md](plan.md). The implementation agent will check off tasks as they are completed.

## Phase 1: Database Schema, ORM Models & Company Deletion Guard
- [ ] 1.1 Create `StagedTransaction` and `StagedAllocation` ORM models (`api/src/models/staged_transaction.py`, `api/src/models/staged_allocation.py`)
- [ ] 1.2 Generate and apply Alembic migration for staging tables (`staged_transactions` and `staged_allocations`)
- [ ] 1.3 Enforce `StagedAllocation` reference check on `Company` deletion (`DELETE /api/companies/{company_id}`)

## Phase 2: Backend Importer Framework & Registry
- [ ] 2.1 Implement core importer data structures, `ImporterValidationError`, and `BaseImporter` ABC (`api/src/services/importers/base.py`)
- [ ] 2.2 Implement `BaseCsvImporter` shared CSV pipeline and parsing utilities (`api/src/services/importers/csv_base.py`)
- [ ] 2.3 Implement Importer Registry (`api/src/services/importers/registry.py`)

## Phase 3: Backend Importer & Staging API Endpoints
- [ ] 3.1 Define Pydantic schemas for importers and staged transactions (`api/src/schemas/importer.py`, `api/src/schemas/staging.py`)
- [ ] 3.2 Implement importer discovery and execution endpoints (`GET /api/importers`, `POST /api/importers/{importer_id}/run` in `api/src/routers/importers.py`)
- [ ] 3.3 Implement staging list, update, and receipt management endpoints (`GET /api/staging`, `PUT /api/staging/{staged_id}`, `POST /api/staging/{staged_id}/receipt`, `DELETE /api/staging/{staged_id}/receipt` in `api/src/routers/staging.py`)
- [ ] 3.4 Implement staging dismiss, restore, and batch ledger acceptance endpoints (`POST /api/staging/{staged_id}/dismiss`, `POST /api/staging/{staged_id}/restore`, `POST /api/staging/accept` in `api/src/routers/staging.py`)

## Phase 4: Frontend Import & Staging Workflow UI
- [ ] 4.1 Define frontend TypeScript interfaces and Pinia store for importers and staging (`web/src/types/staging.ts`, `web/src/stores/staging.ts`)
- [ ] 4.2 Register `/import` navigation item and route (`web/src/layouts/nav.ts`, `web/src/router/routes.ts`)
- [ ] 4.3 Build Staged Transaction & Allocation Editor Dialog (`web/src/components/stagedTransactionEdit.ts`, `web/src/components/StagedTransactionEditDialog.vue`)
- [ ] 4.4 Build Import & Staging View (`web/src/views/ImportView.vue`) with Importer Runner Panel, Staging Review Table, inline allocation controls, and Batch Action Bar
