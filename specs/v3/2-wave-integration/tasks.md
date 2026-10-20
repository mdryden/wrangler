# Tasks: Wave API Integration & Synchronization

## Phase 1: Database Schema, ORM Models & Entity Attribution Guard
- [x] 1.1 Update `Company` and `Allocation` Models and Create `WaveCategory` Model
- [x] 1.2 Generate and Apply Alembic Migration for Wave Integration
- [x] 1.3 Enforce Entity Attribution Constraint (1 Allocation per Entity)

## Phase 2: Wave GraphQL Service Client
- [x] 2.1 Implement Wave Service Data Schemas and GraphQL Client
- [x] 2.2 Wave GraphQL Client Unit Test Suite

## Phase 3: Wave Configuration & Category API Endpoints
- [x] 3.1 Define Pydantic Schemas for Wave Configuration & Categories
- [x] 3.2 Implement Company Wave Endpoints in Companies Router
- [x] 3.3 Company Wave Configuration API Test Suite

## Phase 4: Wave Synchronization & Allocation Category Endpoints
- [x] 4.1 Update Allocation Schemas & Implement Inline Category Assignment Endpoint
- [x] 4.2 Implement `POST /api/companies/{id}/sync-wave` Batch Sync Endpoint
- [x] 4.3 Wave Sync API Test Suite

## Phase 5: Frontend TypeScript Types & Pinia Store Integration
- [x] 5.1 Define Wave and Allocation TypeScript Types
- [x] 5.2 Implement Wave Actions in Company and Transaction Pinia Stores
- [x] 5.3 Pinia Wave Stores Unit Test Suite

## Phase 6: Frontend UI Components & Adaptive Sync View
- [x] 6.1 Update `CompanyFormDialog.vue` for Wave Integration
- [x] 6.2 Update `ExportManagerView.vue` and Helpers for Adaptive Wave Synchronization
- [x] 6.3 Clean Intake Verification in Ledger, Manual Entry, and Staging Views
- [x] 6.4 Frontend Component Test Suite for Wave UI
