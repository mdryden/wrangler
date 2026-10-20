# Implementation Tasks: AI Receipt Integration & Multi-Provider Architecture

## Phase 1: Backend Dependencies & AI Abstraction Layer
- [x] 1.1 Add `pypdf` dependency & AI configuration settings
- [x] 1.2 Implement AI provider base interface and parse result schema
- [x] 1.3 Implement Mock Receipt Parser Provider
- [x] 1.4 Implement OpenAI Receipt Parser Provider
- [x] 1.5 Implement AI Provider Factory
- [x] 1.6 AI Abstraction Layer Unit Test Suite

## Phase 2: Receipt Parser Importer & Backend Multi-File Processing
- [x] 2.1 Implement `ReceiptParserImporter` and register in default importers
- [x] 2.2 Update Importer Schemas with `failed_files`
- [x] 2.3 Extend Importers Router for multi-file concurrency, resilient error handling & pre-AI deduplication
- [x] 2.4 Implement ad-hoc receipt parse endpoint
- [x] 2.5 Importer & Receipts API Test Suite

## Phase 3: Frontend Types, Stores & Pinia State
- [x] 3.1 Update staging types and store with multi-file upload & failure reporting
- [x] 3.2 Add receipt parsing types and action to transaction store
- [x] 3.3 Pinia Staging & Transaction Receipt Store Unit Test Suite

## Phase 4: Frontend UI Views (ImportView & ManualEntryView)
- [x] 4.1 Update `ImportView.vue` for multi-file receipt staging & batch feedback
- [x] 4.2 Restructure `ManualEntryView.vue` for receipt-first layout & AI auto-fill
- [x] 4.3 Frontend Component Test Suite for receipt import and manual entry auto-fill
