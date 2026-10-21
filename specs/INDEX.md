# Wrangler Specification Index

This index serves as the centralized architecture and subsystem map for all specifications in Wrangler. It tracks active features, implementation statuses, primary subsystems, and supersession links.

> [!NOTE]
> For detailed data lifecycle diagrams, codebase directory mappings, subsystem decision matrices, and non-negotiable architectural invariants, consult [`specs/ARCHITECTURE.md`](file:///D:/src/personal/wrangler/specs/ARCHITECTURE.md).

---

## 1. Subsystem Directory

Features in Wrangler are organized across six primary subsystems. When researching or authoring a specification, consult the authoritative specs for the relevant subsystem(s):

| Subsystem | Scope & Responsibilities | Authoritative Specs |
| :--- | :--- | :--- |
| **Ingestion & Importers** | Ingestion pipeline, `BaseImporter` framework, file upload handling, CSV/PDF/Image parsers, file hashing, and deduplication (`source`, `external_id`). | #2, #3, #5, #8 |
| **Staging Layer** | `StagedTransaction` lifecycle (`STAGED`, `ACCEPTED`, `DISMISSED`), staging review table, quick entity allocation, bulk staging actions, and readiness calculation (`is_ready`). | #2, #4, #5, #11 |
| **Core Ledger & Allocations** | `Transaction`, `Allocation`, and `Company` entities, entity attribution invariant (max 1 split per entity), single-currency (CAD) amounts, manual transaction entry, and lock states (`is_locked`). | #1, #6, #9, #11 |
| **Accounting Export** | Export generation (Wave CSV format), export batch tracking, file correlation, and export status reconciliation. | #9 (and amendments 1, 2) |
| **AI & Agent Services** | Pluggable AI provider abstraction (`BaseReceiptParserProvider`, OpenAI, Mock), vision receipt parsing, Model Context Protocol (`FastMCP`) SSE server, and desktop agent intake tools. | #4, #8 |
| **Platform & Shell** | Navigation drawer, responsive UI layouts, Quasar component shell, JWT authentication middleware, host network LAN binding, backup services (`BACKUP_DIR`), and production deployment. | #1, #7, #10 |

---

## 2. Specification Catalog

| # | Feature / Specification | Status | Primary Subsystems | Key Invariants & Summary |
| :- | :--- | :--- | :--- | :--- |
| **01** | [`1-initial-implementation`](file:///D:/src/personal/wrangler/specs/1-initial-implementation/spec.md) | Implemented | Ledger, Platform | Baseline SQLite data model (`Transaction`, `Allocation`, `Company`), admin authentication, session JWT, manual transaction entry. *(Note: Multi-currency and Wave OAuth sections superseded).* |
| **02** | [`2-importer-framework`](file:///D:/src/personal/wrangler/specs/2-importer-framework/spec.md) | Implemented | Ingestion, Staging | `BaseImporter` abstract interface, importer registry, staging area data model (`StagedTransaction`), staging lifecycle (`STAGED`, `ACCEPTED`, `DISMISSED`), and staging review UI. |
| **03** | [`3-amazon-csv-importer`](file:///D:/src/personal/wrangler/specs/3-amazon-csv-importer/spec.md) | Implemented | Ingestion | Amazon Order Reports CSV parser, multi-item order grouping, refund handling, and item description synthesis. |
| **04** | [`4-ai-agent-integration-mcp`](file:///D:/src/personal/wrangler/specs/4-ai-agent-integration-mcp/spec.md) | Implemented | AI / Agent, Staging | FastMCP implementation on `/mcp/sse`, multi-channel `MCP_API_KEY` authentication, and `stage_transaction` intake tool for external AI desktop agents (Goose, Askimo). |
| **05** | [`5-staged-url-and-amazon-enhancements`](file:///D:/src/personal/wrangler/specs/5-staged-url-and-amazon-enhancements/spec.md) | Implemented | Ingestion, Staging | Staged transaction external order URLs, clickable URLs in UI, order item title cleaning, and deduplication refinements. |
| **06** | [`6-remove-multi-currency`](file:///D:/src/personal/wrangler/specs/6-remove-multi-currency/spec.md) | Implemented | Ledger | Locked system to a single base currency (CAD); removed FX exchange rate caching, currency conversion logic, and multi-currency schema columns. *Supersedes multi-currency in #1.* |
| **07** | [`7-collapsible-sidebar`](file:///D:/src/personal/wrangler/specs/7-collapsible-sidebar/spec.md) | Implemented | Platform | Quasar navigation drawer collapsible mini-mode, persistent toggle state in localStorage, and responsive UI polish. |
| **08** | [`8-ai-receipts-integration`](file:///D:/src/personal/wrangler/specs/8-ai-receipts-integration/spec.md) | Implemented | AI / Agent, Ingestion | Multimodal vision AI receipt extraction (images and PDFs), pluggable `BaseReceiptParserProvider` (OpenAI `gpt-4o-mini` and `MockReceiptParser`), SHA-256 deduplication, manual entry auto-fill, and batch staging scanner. |
| **09** | [`9-wave-integration`](file:///D:/src/personal/wrangler/specs/9-wave-integration/spec.md) | Implemented | Export, Ledger | Wave CSV transaction export, batch tracking metadata, and lock status reconciliation (`is_locked`). *(Active amendments: [`spec-amendment1.md`](file:///D:/src/personal/wrangler/specs/9-wave-integration/spec-amendment1.md), [`spec-amendment2.md`](file:///D:/src/personal/wrangler/specs/9-wave-integration/spec-amendment2.md)).* |
| **10** | [`10-production-deployment`](file:///D:/src/personal/wrangler/specs/10-production-deployment/spec.md) | Implemented | Platform | Multi-stage production build, static Vue SPA serving via FastAPI, LAN host binding (`0.0.0.0:8000`), centralized `DATA_DIR` and `BACKUP_DIR`. |
| **11** | [`11-bulk-staged-allocations`](file:///D:/src/personal/wrangler/specs/11-bulk-staged-allocations/spec.md) | Implemented | Staging, Ledger | Checkbox multi-select across all staging items, bulk allocation dialog (Personal / Company / Clear), bulk dismissal with importer `mark_imported` notifications, and atomic batch endpoints. |
| **12** | [`12-bulk-export-categorization`](file:///D:/src/personal/wrangler/specs/12-bulk-export-categorization/spec.md) | Draft | Accounting Export, Ledger | Decoupled visible-page multi-select in Export Manager, contextual bulk toolbar with "Assign Category", BulkCategorizeDialog with overwrite warning, and atomic batch category update endpoint. |

---

## 3. Cold Storage (`specs/vNext/`)

Specifications in `specs/vNext/` are drafted or exploratory concepts deferred to future milestones. They do not have implementation plans or tasks and are not active architectural contracts:

- [`google-groups-importer`](file:///D:/src/personal/wrangler/specs/vNext/google-groups-importer/spec.md): Parser for Google Groups email transaction notifications.
- [`browser-extension-bundle-exporter`](file:///D:/src/personal/wrangler/specs/vNext/browser-extension-bundle-exporter/spec.md): Browser extension workflow for automated order export bundling.

---

## 4. Spec Lifecycle & Modification Rules

1. **New Features:** Placed in a new sequentially numbered directory: `specs/<N>-<short-description>/` with `spec.md`, `plan.md`, and `tasks.md`.
2. **Amendments to Implemented Specs:** Once a spec is implemented, do not overwrite `spec.md`. Author incremental changes or fixes in `spec-amendment<N>.md` in the same directory.
3. **Spec Frontmatter:** Every spec should include metadata:
   ```yaml
   ---
   status: Implemented # Draft | In Progress | Implemented | Superseded
   subsystems:
     - Staging
     - Ledger
   amendments: [] # optional: e.g. [spec-amendment1.md]
   supersedes: null # optional: e.g. 1-initial-implementation (currency)
   superseded_by: null # optional: e.g. 6-remove-multi-currency
   ---
   ```
