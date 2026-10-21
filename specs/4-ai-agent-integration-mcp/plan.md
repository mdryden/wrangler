# Implementation Plan: AI Agent Integration (Model Context Protocol)

This implementation plan defines the step-by-step engineering tasks to integrate external AI desktop assistants with Wrangler via the Model Context Protocol (MCP) using FastMCP over HTTP/SSE, as specified in `spec.md`.

---

## Phase 1: Dependencies, Configuration & Authentication Middleware

*Goal:* Equip the backend with the FastMCP SDK, add the dedicated MCP API key configuration, and implement multi-channel authentication in the system middleware.

### 1.1 Add MCP SDK to Backend Dependencies
- Add `mcp>=1.0.0` to `dependencies` in `api/pyproject.toml`.
- Update package locking and lockfile sync using `uv`.
- Verify the package imports cleanly in Python 3.14 (`from mcp.server.fastmcp import FastMCP`).

### 1.2 Add `MCP_API_KEY` Setting to Application Configuration
- In `api/src/core/config.py`, add `MCP_API_KEY: str = ""` to the `Settings` class.
- Support reading `MCP_API_KEY` from environment variables and `.env` files.
- Default to `""` (empty string) to represent "trust-on-local-network" mode when no key is explicitly configured.

### 1.3 Update Authentication Middleware for Multi-Channel MCP Authentication
- In `api/src/core/security.py`, modify `AuthenticationMiddleware` to inspect incoming request paths:
  - If the request path begins with `/mcp` or equals `/mcp`, bypass the standard user JWT session check.
  - If `settings.MCP_API_KEY` is configured (non-empty string):
    - Extract candidate API key from one of three channels in order:
      1. URL Query parameter: `request.query_params.get("api_key")`
      2. Custom header: `request.headers.get("x-api-key")`
      3. Authorization header: `Authorization: Bearer <MCP_API_KEY>`
    - Validate candidate key against `settings.MCP_API_KEY` using constant-time comparison (`secrets.compare_digest`).
    - If missing or invalid, immediately return HTTP `401 Unauthorized` with `{"detail": "Invalid or missing MCP API key"}`.
  - If `settings.MCP_API_KEY` is empty/unset, allow the request to proceed unconditionally (trust-on-local-network mode).
- Create unit tests in `api/tests/test_mcp_auth.py` verifying:
  - Unauthenticated access when `MCP_API_KEY` is unset.
  - Successful authentication via URL query parameter `?api_key=`.
  - Successful authentication via `X-API-Key` header.
  - Successful authentication via `Authorization: Bearer` header.
  - Rejection with 401 when key is missing or mismatched.
  - Non-interference with standard JWT-protected `/api/*` endpoints.

---

## Phase 2: MCP Tools & Business Logic Service

*Goal:* Implement the FastMCP server instance and tool functions with localized session management, input normalization, dual-table deduplication, and staging insertion.

### 2.1 Implement Core MCP Tool `stage_transaction`
- Create `api/src/services/mcp.py` and instantiate `FastMCP("Wrangler")`.
- Implement `@mcp.tool()` function:
  ```python
  async def stage_transaction(
      source_label: str,
      external_id: str,
      date: str | None = None,
      total_amount: float | None = None,
      description: str | None = None,
      currency_code: str | None = None,
  ) -> str:
  ```
- Use localized SQLAlchemy session lifecycle (`SessionLocal()` within `try...finally`) for thread/concurrency safety.
- Implement input normalization:
  - Strip and lowercase `source_label`. Reject if empty.
  - Strip `external_id`. Reject if empty.
  - Construct `namespaced_external_id = f"{source_label}:{raw_external_id}"`.
  - Description: If None or empty, store as None. If provided, strip and format with prefix: `f"[{source_label}] "` if `@` in source_label else `f"[{source_label.title()}] "` (if not already present).
  - Currency: If None or empty, default to `"CAD"`. Otherwise strip and uppercase.
  - Amount: If None, store as None. If provided, convert to `Decimal(f"{total_amount:.2f}")`. Reject zero amount (`Decimal("0.00")`). Support negative amounts for refunds.
  - Date: If None or empty, store as None. If provided, parse string supporting `YYYY-MM-DD` and full ISO 8601 timestamps into a `datetime.date` object.
- Implement dual-table deduplication query:
  - Check `StagedTransaction` for `source == "mcp"` and `external_id == namespaced_external_id`.
  - Check `Transaction` for `source == "mcp"` and `external_id == namespaced_external_id`.
  - If found in staging: return `"Transaction '[mcp] {namespaced_external_id}' already exists in Wrangler (status: {staged_status}). Skipped."`
  - If found in ledger: return `"Transaction '[mcp] {namespaced_external_id}' already exists in Wrangler (status: LEDGER). Skipped."`
- Implement record persistence:
  - Create new `StagedTransaction` with `source="mcp"`, `external_id=namespaced_external_id`, `date=parsed_date`, `description=formatted_description`, `total_amount=amount_decimal`, `currency_code=currency_code`, `status="STAGED"`, `is_marked_imported=False`, `receipt_file_path=None`, and empty allocations.
  - Commit session and return confirmation string detailing staged transaction and noting missing fields if any (e.g. `"... Needs review in Wrangler: date, total_amount."`).

### 2.2 Implement Pre-flight Verification Tool `check_transaction_exists`
- In `api/src/services/mcp.py`, implement `@mcp.tool()` function:
  ```python
  async def check_transaction_exists(
      source_label: str,
      external_id: str,
  ) -> dict:
  ```
- Normalize `namespaced_external_id = f"{source_label.strip().lower()}:{external_id.strip()}"`.
- Query `StagedTransaction` and `Transaction` where `source == "mcp"` and `external_id == namespaced_external_id`.
- Return dictionary contract:
  - If found in `StagedTransaction`: `{"exists": True, "location": "staged", "status": staged_tx.status}` (`STAGED`, `ACCEPTED`, or `DISMISSED`).
  - If found in `Transaction`: `{"exists": True, "location": "ledger", "status": "COMMITTED"}`.
  - If not found: `{"exists": False, "location": None, "status": None}`.

### 2.3 Implement Unit Test Suite for MCP Tools and Normalization Logic
- Create `api/tests/test_mcp_tools.py` covering:
  - Input normalization (case-insensitivity of `source_label`, whitespace trimming, title casing prepended to description).
  - Validation: rejecting empty `source_label`, empty `external_id`, or `0.00` total amount.
  - Date parsing: standard `YYYY-MM-DD` and ISO 8601 timestamps with times/offsets.
  - Negative amounts (refunds and credits) successfully staged.
  - Dual-table deduplication against staging (status `STAGED`, `ACCEPTED`, `DISMISSED`) and ledger (`COMMITTED`).
  - Idempotent skip responses ensuring no duplicate records or errors on re-ingestion.
  - Pre-flight `check_transaction_exists` output across all states (non-existent, staged, dismissed, ledger).

---

## Phase 3: FastMCP Application Mounting & Protocol Transport

*Goal:* Expose the FastMCP server over HTTP/SSE by mounting its ASGI application onto FastAPI at `/mcp` with proper lifespan coordination.

### 3.1 Mount FastMCP SSE Sub-Application and Combine Lifespans
- In `api/src/main.py`:
  - Import the FastMCP server instance from `services.mcp`.
  - Extract the underlying ASGI sub-application for SSE transport (`mcp.sse_app()` / `mcp.http_app(transport="sse")`).
  - Merge the FastMCP ASGI lifespan with the existing FastAPI `lifespan` handler (ensuring receipt storage directory creation runs alongside MCP session startup and shutdown).
  - Mount the FastMCP sub-application to FastAPI at prefix `/mcp` via `app.mount("/mcp", mcp_app)`.
  - Ensure server entry point configuration supports binding to `0.0.0.0:8000` for LAN connectivity.

### 3.2 Implement Transport and Integration Test Suite
- Create `api/tests/test_mcp_transport.py` testing over ASGI `httpx.AsyncClient`:
  - Connect to `GET /mcp/sse` and verify the Server-Sent Events stream initialization.
  - Test authentication enforcement on `/mcp/sse` and `/mcp/messages/` endpoints with query parameter (`?api_key=`), custom header (`X-API-Key`), and Bearer token (`Authorization: Bearer`).
  - Verify rejection with 401 when an invalid key is provided to transport endpoints.
  - Verify MCP client tool listing and initialization protocol handshake.

---

## Phase 4: Staging Pipeline & UI Integration

*Goal:* Ensure seamless user experience in the Wrangler UI Staging Area for records ingested via MCP tools, verifying filtering, allocation, acceptance, and dismissal.

### 4.1 Update Staging View Source Filter Options in Frontend
- In `web/src/views/ImportView.vue`:
  - Update the Source filter control to support selecting or filtering by `"mcp"`.
  - Include `"mcp"` in source filter options alongside existing sources (`"manual"`, `"wrangler_csv"`, `"amazon_csv"`, `"google_groups"`).
- Update frontend tests in `web/src/views/__tests__/importView.spec.ts` to verify filtering by `"mcp"`.

### 4.2 Implement Staging Lifecycle Integration Tests for MCP Transactions
- Create `api/tests/test_mcp_staging_lifecycle.py` verifying full end-to-end integration:
  - Transactions ingested via `stage_transaction` appear in staging queries (`GET /api/staging?status=STAGED` and `GET /api/staging?source=mcp`).
  - Ingested records start in `STAGED` status with zero allocations and `is_ready = False`.
  - User allocation assignment: updating allocations (`PUT /api/staging/{id}`) marks record as ready (`is_ready = True`).
  - Batch acceptance: accepting staged MCP transaction (`POST /api/staging/accept`) converts record to Ledger `Transaction` and `Allocation` records.
  - Dismissal: dismissing staged MCP transaction (`POST /api/staging/{id}/dismiss`) updates status to `DISMISSED`.
  - Idempotency verification: calling `stage_transaction` again after acceptance or dismissal returns the expected skip response without error.
