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
- [x] 1.12 Verify database schema setup and health check endpoint

## Phase 2: Authentication & Security (Backend)
- [x] 2.1 Implement JWT utilities (create and verify tokens)
- [x] 2.2 Implement admin credential verification against environment variables
- [x] 2.3 Create `POST /api/login` endpoint
- [x] 2.4 Implement secure-by-default authentication middleware (opt-in anonymous routes for health & login) and `get_current_user` dependency
- [x] 2.5 Verify authentication and route protection using a REST client

## Phase 3: Company Management & Wave OAuth (Backend)
- [ ] 3.1 Create Company CRUD endpoints (`GET`, `POST`, `PUT`, `DELETE` at `/api/companies`)
- [ ] 3.2 Create Wave API client utility
- [ ] 3.3 Implement `GET /api/wave/oauth/authorize` endpoint with signed JWT state parameter
- [ ] 3.4 Implement `GET /api/wave/oauth/callback` endpoint and token persistence
- [ ] 3.5 Implement Wave token refresh logic in client utility
- [ ] 3.6 Verify company management and OAuth flow via REST client and browser

## Phase 4: Wave Chart of Accounts Sync
- [ ] 4.1 Implement Wave Chart of Accounts GraphQL query (filter for Expense, Asset, Income)
- [ ] 4.2 Create `POST /api/companies/{id}/sync-categories` endpoint
- [ ] 4.3 Implement upsert logic for `WaveCategory` table
- [ ] 4.4 Verify category synchronization via REST client

## Phase 5: Transaction & Allocation Management (Backend)
- [ ] 5.1 Implement intake source parser abstraction and base interface
- [ ] 5.2 Create `POST /api/transactions` endpoint (manual entry with receipt upload support)
- [ ] 5.3 Create `GET /api/transactions` endpoint with server-side pagination
- [ ] 5.4 Create `PUT /api/transactions/{id}` and `PUT /api/transactions/{id}/approve` endpoints
- [ ] 5.5 Create `PUT /api/transactions/{id}/allocations` endpoint
- [ ] 5.6 Enforce immutability validation on allocations (HTTP 400 if any allocation is `SYNCED`)
- [ ] 5.7 Implement receipt upload (`POST /api/transactions/{id}/receipt`) and retrieval (`GET /api/receipts/{path}`) endpoints
- [ ] 5.8 Verify transaction and allocation endpoints via REST client

## Phase 6: Frontend Foundation
- [x] 6.1 Initialize Vue 3 + Quasar project with Pinia
- [x] 6.2 Configure Vue Router and authentication navigation guards
- [x] 6.3 Implement Login View and integrate with `POST /api/login`
- [ ] 6.4 Implement persistent Navigation Drawer layout (Ledger, Manual Entry, Sync Manager, Settings)
- [ ] 6.5 Implement Fetch API client wrapper with automatic JWT authorization header
- [ ] 6.6 Verify frontend foundation in browser

## Phase 7: Frontend Company & Settings Management
- [ ] 7.1 Create Company Management & Settings View
- [ ] 7.2 Implement Company creation and editing forms (including `wave_equity_account_id`)
- [ ] 7.3 Implement "Connect to Wave" OAuth action button
- [ ] 7.4 Implement token status indicator (Connected/Disconnected/Expired)
- [ ] 7.5 Implement "Sync Categories" button
- [ ] 7.6 Verify Company Management UI in browser

## Phase 8: Frontend Ledger & Allocation Editor
- [ ] 8.1 Create Ledger View with server-side paginated `QTable`
- [ ] 8.2 Implement visual locking and read-only state for transactions with `SYNCED` allocations
- [ ] 8.3 Build Allocation Editor (Transaction Splitter) component
- [ ] 8.4 Integrate Allocation Editor with `PUT /api/transactions/{id}/allocations`
- [ ] 8.5 Implement receipt upload and view component
- [ ] 8.6 Implement transaction approval action UI
- [ ] 8.7 Verify Ledger and Allocation Editor UI in browser

## Phase 9: Wave Synchronization Engine (Backend)
- [ ] 9.1 Implement Wave GraphQL `documentCreate` mutation for receipts using Apollo multipart spec via `httpx`
- [ ] 9.2 Implement Wave GraphQL transaction mutation builder
- [ ] 9.3 Implement transaction grouping logic (group same-company allocations into one Wave transaction with multiple line items)
- [ ] 9.4 Implement refund and negative amount handling (flip debits/credits)
- [ ] 9.5 Implement cross-company receipt upload logic (upload receipt separately to each company)
- [ ] 9.6 Implement background task worker logic for `PENDING` allocations
- [ ] 9.7 Wrap Wave push updates and local DB state updates in local database transaction
- [ ] 9.8 Implement `POST /api/sync/wave` background task endpoint (returns `202 Accepted`)
- [ ] 9.9 Implement sync progress polling endpoint
- [ ] 9.10 Verify Wave synchronization engine

## Phase 10: Sync Manager & Polling (Frontend)
- [ ] 10.1 Create Sync Manager View displaying `PENDING` and `FAILED` allocations
- [ ] 10.2 Implement "Sync to Wave" action
- [ ] 10.3 Implement "Retry Failed" action
- [ ] 10.4 Implement polling mechanism for sync progress
- [ ] 10.5 Implement error display for failed syncs
- [ ] 10.6 Verify end-to-end Wave sync flow
