# Implementation Tasks: AI Agent Integration (Model Context Protocol)

## Phase 1: Dependencies, Configuration & Authentication Middleware
- [x] 1.1 Add MCP SDK to backend dependencies in `api/pyproject.toml`
- [x] 1.2 Add `MCP_API_KEY` setting to application configuration in `api/src/core/config.py`
- [x] 1.3 Update `AuthenticationMiddleware` for multi-channel MCP authentication in `api/src/core/security.py`

## Phase 2: MCP Tools & Business Logic Service
- [x] 2.1 Implement core MCP tool `stage_transaction` with dual-table deduplication in `api/src/services/mcp.py`
- [x] 2.2 Implement pre-flight verification tool `check_transaction_exists` in `api/src/services/mcp.py`
- [x] 2.3 Implement unit test suite for MCP tools and normalization logic in `api/tests/test_mcp_tools.py`

## Phase 3: FastMCP Application Mounting & Protocol Transport
- [x] 3.1 Mount FastMCP SSE sub-application and combine lifespans in `api/src/main.py`
- [x] 3.2 Implement transport and integration test suite in `api/tests/test_mcp_transport.py`

## Phase 4: Staging Pipeline & UI Integration
- [x] 4.1 Update Staging View source filter options in `web/src/views/ImportView.vue` and update frontend tests
- [x] 4.2 Implement staging lifecycle integration tests for MCP transactions in `api/tests/test_mcp_staging_lifecycle.py`
