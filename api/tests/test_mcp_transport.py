import httpx
import pytest
from httpx import ASGITransport
from sqlalchemy.orm import sessionmaker

from core.config import settings
from main import app
from services.mcp import mcp


@pytest.fixture
def mock_mcp_session(monkeypatch, db_session):
    testing_session_local = sessionmaker(bind=db_session.get_bind(), autocommit=False, autoflush=False)
    monkeypatch.setattr("services.mcp.SessionLocal", testing_session_local)
    return db_session


@pytest.mark.anyio
async def test_mcp_transport_auth_enforcement_and_rejection(monkeypatch):
    monkeypatch.setattr(settings, "MCP_API_KEY", "mcp-transport-secret-key")

    transport = ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://127.0.0.1") as client:
        # 1. Missing key on /mcp/sse
        res = await client.get("/mcp/sse")
        assert res.status_code == 401
        assert res.json() == {"detail": "Invalid or missing MCP API key"}

        # 2. Missing key on /mcp/messages/
        res = await client.post("/mcp/messages/")
        assert res.status_code == 401
        assert res.json() == {"detail": "Invalid or missing MCP API key"}

        # 3. Wrong key via query param
        res = await client.get("/mcp/sse?api_key=wrong-key")
        assert res.status_code == 401
        assert res.json() == {"detail": "Invalid or missing MCP API key"}

        # 4. Wrong key via custom header
        res = await client.get("/mcp/sse", headers={"x-api-key": "wrong-key"})
        assert res.status_code == 401
        assert res.json() == {"detail": "Invalid or missing MCP API key"}

        # 5. Wrong key via Bearer header
        res = await client.get("/mcp/sse", headers={"Authorization": "Bearer wrong-key"})
        assert res.status_code == 401
        assert res.json() == {"detail": "Invalid or missing MCP API key"}


@pytest.mark.anyio
async def test_mcp_transport_auth_channels_success(monkeypatch):
    import anyio

    monkeypatch.setattr(settings, "MCP_API_KEY", "mcp-transport-secret-key")

    transport = ASGITransport(app=app)
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(transport=transport, base_url="http://127.0.0.1") as client:
            # Success via Query parameter on /mcp/sse
            with anyio.move_on_after(0.2):
                async with client.stream("GET", "/mcp/sse?api_key=mcp-transport-secret-key") as response:
                    assert response.status_code == 200
                    assert "text/event-stream" in response.headers.get("content-type", "")

            # Success via X-API-Key header on /mcp/sse
            with anyio.move_on_after(0.2):
                async with client.stream("GET", "/mcp/sse", headers={"x-api-key": "mcp-transport-secret-key"}) as response:
                    assert response.status_code == 200
                    assert "text/event-stream" in response.headers.get("content-type", "")

            # Success via Authorization Bearer header on /mcp/sse
            with anyio.move_on_after(0.2):
                async with client.stream("GET", "/mcp/sse", headers={"Authorization": "Bearer mcp-transport-secret-key"}) as response:
                    assert response.status_code == 200
                    assert "text/event-stream" in response.headers.get("content-type", "")

            # Success on /mcp/messages/ endpoint with valid keys (bypasses auth, reaches message endpoint)
            res_query = await client.post("/mcp/messages/?api_key=mcp-transport-secret-key")
            assert res_query.status_code != 401

            res_header = await client.post("/mcp/messages/", headers={"x-api-key": "mcp-transport-secret-key"})
            assert res_header.status_code != 401

            res_bearer = await client.post("/mcp/messages/", headers={"Authorization": "Bearer mcp-transport-secret-key"})
            assert res_bearer.status_code != 401


@pytest.mark.anyio
async def test_mcp_transport_sse_stream_initialization(monkeypatch):
    import anyio

    monkeypatch.setattr(settings, "MCP_API_KEY", "")

    transport = ASGITransport(app=app)
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(transport=transport, base_url="http://127.0.0.1") as client:
            with anyio.move_on_after(0.2):
                async with client.stream("GET", "/mcp/sse") as response:
                    assert response.status_code == 200
                    assert "text/event-stream" in response.headers.get("content-type", "")


@pytest.mark.anyio
async def test_mcp_transport_post_sse_initialize(monkeypatch):
    monkeypatch.setattr(settings, "MCP_API_KEY", "mcp-transport-secret-key")

    transport = ASGITransport(app=app)
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(transport=transport, base_url="http://127.0.0.1") as client:
            # 1. Unauthenticated POST /mcp/sse is rejected with 401
            res_unauth = await client.post(
                "/mcp/sse",
                json={
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "initialize",
                    "params": {
                        "protocolVersion": "2024-11-05",
                        "capabilities": {},
                        "clientInfo": {"name": "goose", "version": "1.0.0"},
                    },
                },
            )
            assert res_unauth.status_code == 401

            # 2. Authenticated POST /mcp/sse with x-api-key header succeeds (200 OK)
            res = await client.post(
                "/mcp/sse",
                headers={
                    "x-api-key": "mcp-transport-secret-key",
                    "Content-Type": "application/json",
                    "Accept": "application/json, text/event-stream",
                },
                json={
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "initialize",
                    "params": {
                        "protocolVersion": "2024-11-05",
                        "capabilities": {},
                        "clientInfo": {"name": "goose", "version": "1.0.0"},
                    },
                },
            )
            assert res.status_code == 200
            data = res.json()
            assert data.get("jsonrpc") == "2.0"
            assert data.get("id") == 1
            assert "result" in data
            assert data["result"]["serverInfo"]["name"] == "Wrangler"


@pytest.mark.anyio
async def test_mcp_tool_listing_and_execution_protocol(mock_mcp_session):
    # Verify tool listing
    tools = await mcp.list_tools()
    tool_names = [t.name for t in tools]
    assert "stage_transaction" in tool_names
    assert "check_transaction_exists" in tool_names

    # Check stage_transaction tool schema/parameters
    stage_tool = next(t for t in tools if t.name == "stage_transaction")
    assert "source_label" in stage_tool.input_schema["properties"]
    assert "external_id" in stage_tool.input_schema["properties"]
    assert "date" in stage_tool.input_schema["properties"]
    assert "total_amount" in stage_tool.input_schema["properties"]
    assert "description" in stage_tool.input_schema["properties"]
    assert "currency_code" not in stage_tool.input_schema["properties"]

    # Check check_transaction_exists tool schema/parameters
    check_tool = next(t for t in tools if t.name == "check_transaction_exists")
    assert "source_label" in check_tool.input_schema["properties"]
    assert "external_id" in check_tool.input_schema["properties"]

    # Verify tool execution via call_tool protocol
    stage_res = await mcp.call_tool(
        "stage_transaction",
        {
            "source_label": "amazon",
            "external_id": "transport-tx-1",
            "date": "2026-10-17",
            "total_amount": 55.40,
            "description": "USB-C Hub",
        },
    )
    assert stage_res is not None
    assert "Successfully staged transaction" in str(stage_res)

    check_res = await mcp.call_tool(
        "check_transaction_exists",
        {
            "source_label": "amazon",
            "external_id": "transport-tx-1",
        },
    )
    assert check_res is not None
    assert "staged" in str(check_res)
