# Tasks: Amendment 3 - Move Receipt Reference to Wave Transaction Notes

## Phase 1: Wave Client Service & Unit Tests

- [ ] 1.1 Add `notes` parameter to `WaveClient.create_money_transaction` and update client unit tests

## Phase 2: Company Wave Sync Endpoint & Integration Tests

- [ ] 2.1 Update `POST /api/companies/{company_id}/sync-wave` to populate `notes` with receipt memo and update sync API tests

## Phase 3: Wave API Reference Documentation & Skill Schema

- [ ] 3.1 Update Wave GraphQL schema snippets and skill documentation for `MoneyTransactionCreateInput.notes`
