# Implementation Tasks

This file tracks the execution progress of the tasks defined in [plan.md](plan.md). The implementation agent will check off tasks as they are completed.

## Phase 1: Backend Foundation and Database Setup
- [x] 1.1 Initialize Python environment and dependencies (FastAPI, Uvicorn, SQLAlchemy/SQLModel, Pydantic, Alembic)
- [x] 1.2 Set up project structure (`routers/`, `models/`, `schemas/`, `services/`, `core/`, `database.py`)
- [x] 1.3 Create configuration module for environment variables (`ADMIN_USERNAME`, `ADMIN_PASSWORD`, JWT secrets, Wave OAuth config, `RECEIPT_STORAGE_DIR`)
- [x] 1.4 Initialize SQLite database connection and ORM setup
- [x] 1.5 Define `Company` ORM model
- [x] 1.6 Define `WaveCategory` ORM model
- [x] 1.7 Define `Transaction` ORM model with unique constraint on `(source, external_id)`
- [x] 1.8 Define `Allocation` ORM model with `sync_status` enum
- [x] 1.9 Set up Alembic and apply initial migrations
- [x] 1.10 Ensure receipt storage directory creation on startup
- [x] 1.11 Implement SQLite health check endpoint (`GET /api/health`)

## Phase 2: Authentication & Security (Backend)
- [x] 2.1 Implement JWT utilities (create and verify tokens)
- [x] 2.2 Implement admin credential verification against environment variables
- [x] 2.3 Create `POST /api/login` endpoint
- [x] 2.4 Implement secure-by-default authentication middleware (opt-in anonymous routes for health & login) and `get_current_user` dependency

## Phase 3: Company Management & Wave OAuth (Backend)
- [x] 3.1 Create Company CRUD endpoints (`GET`, `POST`, `PUT`, `DELETE` at `/api/companies`)
- [x] 3.2 Create Wave API client utility
- [x] 3.3 Implement `GET /api/wave/oauth/authorize` endpoint with signed JWT state parameter
- [x] 3.4 Implement `GET /api/wave/oauth/callback` endpoint and token persistence
- [x] 3.5 Implement Wave token refresh logic in client utility

## Phase 4: Wave Chart of Accounts Sync
- [x] 4.1 Implement Wave Chart of Accounts GraphQL query (filter for Expense, Asset, Income)
- [x] 4.2 Create `POST /api/companies/{id}/sync-categories` endpoint
- [x] 4.3 Implement upsert logic for `WaveCategory` table

## Phase 5: Transaction & Allocation Management (Backend)
- [x] 5.1 Implement intake source parser abstraction and base interface
- [x] 5.2 Create `POST /api/transactions` endpoint (manual entry with receipt upload support)
- [x] 5.3 Create `GET /api/transactions` endpoint with server-side pagination
- [x] 5.4 Create `PUT /api/transactions/{id}` and `PUT /api/transactions/{id}/approve` endpoints
- [x] 5.5 Create `PUT /api/transactions/{id}/allocations` endpoint
- [x] 5.6 Enforce immutability validation on allocations (HTTP 400 if any allocation is `SYNCED`)
- [x] 5.7 Implement receipt upload (`POST /api/transactions/{id}/receipt`) and retrieval (`GET /api/receipts/{path}`) endpoints

## Phase 6: Frontend Foundation
- [x] 6.1 Initialize Vue 3 + Quasar project with Pinia
- [x] 6.2 Configure Vue Router and authentication navigation guards
- [x] 6.3 Implement Login View and integrate with `POST /api/login`
- [x] 6.4 Implement persistent Navigation Drawer layout (Ledger, Manual Entry, Sync Manager, Settings)
- [x] 6.5 Implement Fetch API client wrapper with automatic JWT authorization header

## Phase 7: Frontend Company & Settings Management
- [x] 7.1 Create Company Management & Settings View
- [x] 7.2 Implement Company creation and editing forms (including `wave_equity_account_id`)
- [x] 7.3 Implement "Connect to Wave" OAuth action button
- [x] 7.4 Implement token status indicator (Connected/Disconnected/Expired)
- [x] 7.5 Implement "Sync Categories" button

## Phase 8: Revert Wave Integration (Backend & Database)
- [x] 8.1 Remove Wave configuration settings from backend (`core/config.py`)
- [x] 8.2 Remove Wave routers (`routers/wave_oauth.py`), category sync endpoints, Wave service, and Wave schemas
- [x] 8.3 Update `Company` ORM model and schemas to remove Wave attributes and enforce unique name
- [x] 8.4 Update `Allocation` ORM model to remove Wave fields, restrict `SyncStatus` enum to `PENDING` and `SYNCED`, and drop `WaveCategory` model
- [x] 8.5 Update allocation endpoints to remove Wave categories and restrict company deletion if linked to allocations
- [x] 8.6 Generate and execute Alembic migration for SQLite schema cleanup

## Phase 9: Backend Export & Sync Reconciliation Endpoints
- [x] 9.1 Implement transaction filtering on `GET /api/transactions` (source, approval, date range)
- [x] 9.2 Implement single allocation reversion endpoint (`PUT /api/allocations/{id}/revert`)
- [x] 9.3 Implement RFC 4180 CSV export utility for Wave format (`Date,Description,Amount`)
- [x] 9.4 Implement `GET /api/companies/{id}/export-transactions` endpoint
- [x] 9.5 Implement `POST /api/companies/{id}/mark-synced` endpoint
- [x] 9.6 Implement `POST /api/companies/{id}/revert-synced` endpoint

## Phase 10: Frontend Wave Reversion & Settings Updates
- [x] 10.1 Remove Wave OAuth UI and actions from Settings (`SettingsView.vue`, `TokenStatusBadge.vue`)
- [x] 10.2 Update Company dialog, types, and store to remove Wave fields and display transaction counts
- [x] 10.3 Update navigation drawer and routing for Export Manager (`/export-manager`)

## Phase 11: Frontend Ledger & Allocation Editor
- [x] 11.1 Build Ledger View with server-side pagination and filters
- [ ] 11.2 Implement visual locking for synced transactions and reversion action
- [ ] 11.3 Build Allocation Editor (Transaction Splitter) component without Wave categories
- [ ] 11.4 Integrate Allocation Editor with backend API (`PUT /api/transactions/{id}/allocations`)
- [ ] 11.5 Implement receipt file upload and direct download link
- [ ] 11.6 Implement transaction approval toggle UI

## Phase 12: Frontend Export Manager UI
- [ ] 12.1 Build Export Manager View with Pending Exports Summary
- [ ] 12.2 Implement "Export CSV" download action per company
- [ ] 12.3 Implement "Mark as Synced" action per company
- [ ] 12.4 Build Reconciliation & History section with reversion

## Phase 13: Manual Expense Intake & Rapid Entry Form
- [ ] 13.1 Update `POST /api/transactions` endpoint and schemas for company attribution and atomic allocations
- [ ] 13.2 Build Manual Entry form controls and datepicker in `ManualEntryView.vue`
- [ ] 13.3 Implement inline allocation splitter with real-time balance validation
- [ ] 13.4 Implement keyboard shortcuts, rapid continuous entry reset, and auto-focus
- [ ] 13.5 Verify Manual Entry end-to-end in browser

