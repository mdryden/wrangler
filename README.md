# Wrangler - Family Accounting App

A private internal web tool for reviewing, allocating, and synchronizing financial transactions across personal expenses and business entities with [Wave](https://waveapps.com).

---

## Architecture & Monorepo Layout

This project is organized as a monorepo managed with `pnpm`:

```
wrangler/
├── api/                   # Backend FastAPI service
│   ├── src/               # Application source code
│   │   ├── core/          # Configuration & security (config.py)
│   │   ├── models/        # SQLAlchemy database models
│   │   ├── routers/       # API route controllers
│   │   ├── schemas/       # Pydantic request/response schemas
│   │   ├── services/      # Business logic & Wave API clients
│   │   ├── database.py    # Database connection & session factory
│   │   └── main.py        # FastAPI application entry point
│   ├── .env               # Environment configuration & secrets
│   └── pyproject.toml     # Python dependencies managed by uv
├── web/                   # Frontend Vue 3 + Quasar app (Phase 6)
├── specs/                 # SDD specifications, plan, and task tracking
├── package.json           # Monorepo root scripts & pnpm configuration
├── pnpm-workspace.yaml    # Workspace definition
└── README.md
```

---

## Prerequisites

Ensure the following tools are installed on your workstation:

- **Python**: Python 3.14.x managed via [uv](https://docs.astral.sh/uv/)
- **Node.js**: Node 20+ (managed via `nvm`)
- **pnpm**: Fast, disk space efficient package manager

---

## Development Setup

### 1. Backend Setup

The backend dependencies are managed using `uv`:

```bash
cd api
uv sync
```

### 2. Environment Configuration

The backend environment is configured via `api/.env`:

| Variable | Description | Default |
| :--- | :--- | :--- |
| `ADMIN_USERNAME` | Single admin user login | `admin` |
| `ADMIN_PASSWORD` | Single admin user password | `admin` |
| `JWT_SECRET_KEY` | Cryptographic secret for signing JWT sessions | (Generated 256-bit hex) |
| `JWT_ACCESS_TOKEN_EXPIRE_MINUTES` | Token expiration time in minutes | `1440` (24h) |
| `WAVE_CLIENT_ID` | Wave API OAuth application client ID | |
| `WAVE_CLIENT_SECRET` | Wave API OAuth application client secret | |
| `WAVE_REDIRECT_URI` | Wave OAuth redirect URI | `http://localhost:8000/api/wave/oauth/callback` |
| `RECEIPT_STORAGE_DIR` | Absolute or relative path for receipt files | `receipts` |
| `DATABASE_URL` | SQLite database connection string | `sqlite:///./wrangler.db` |
| `MCP_API_KEY` | Optional API key protecting MCP endpoints over SSE | `""` (Trust on local network) |

---

## Running in Development

Use `pnpm` from the root workspace directory to run services:

### Start Development Servers

```bash
# Start all workspace services in parallel (API on :8000, Web on :3000)
pnpm dev

# Or start backend only (runs `uv run python src/main.py`)
pnpm dev:api
# or
pnpm --filter api dev

# Or start backend directly from api/ directory
cd api
uv run python src/main.py
```

The server will launch with auto-reload enabled:
- **API Base URL**: `http://localhost:8000`
- **Interactive Swagger Docs**: `http://localhost:8000/docs`
- **ReDoc Documentation**: `http://localhost:8000/redoc`
- **Health Check**: `http://localhost:8000/api/health`

---

## AI Agent Integration (Model Context Protocol / MCP)

Wrangler exposes an authenticated **Model Context Protocol (MCP)** tool server over HTTP/SSE, allowing external desktop AI assistants (such as Goose, Claude Desktop, Askimo Desktop, or Cursor) to stage financial transactions directly into Wrangler's Staging Area.

### Endpoints
- **SSE Event Stream**: `http://<server-host>:8000/mcp/sse`
- **Client Messages**: `http://<server-host>:8000/mcp/messages/`

Wrangler binds to `0.0.0.0:8000`, enabling connections from `localhost` in local development or your server's LAN IP address (e.g. `http://192.168.1.50:8000/mcp/sse`) on a home network without requiring SSL/TLS.

### Authentication
If `MCP_API_KEY` is configured in `api/.env`, incoming requests must present the key via one of three channels:
1. **URL Query Parameter**: `http://<server-host>:8000/mcp/sse?api_key=your_mcp_api_key`
2. **HTTP Header**: `X-API-Key: your_mcp_api_key`
3. **Authorization Header**: `Authorization: Bearer your_mcp_api_key`

If `MCP_API_KEY` is left blank (default), authentication is disabled for trust-on-local-network operation.

### Client Configuration

#### Goose Configuration
Add the Wrangler extension to your Goose configuration (`~/.config/goose/config.yaml`):

```yaml
extensions:
  wrangler:
    type: sse
    uri: http://localhost:8000/mcp/sse
    # If MCP_API_KEY is configured:
    # uri: http://localhost:8000/mcp/sse?api_key=your_mcp_api_key
    # Or using custom headers:
    # headers:
    #   x-api-key: your_mcp_api_key
```

#### Generic SSE MCP Client Configuration (JSON)
For MCP clients using JSON configuration (e.g., Claude Desktop, Cursor):

```json
{
  "mcpServers": {
    "wrangler": {
      "url": "http://localhost:8000/mcp/sse",
      "headers": {
        "x-api-key": "your_mcp_api_key"
      }
    }
  }
}
```

> **Note:** For LAN connections from other devices on your local network, replace `localhost:8000` with the server's IP address (e.g. `http://192.168.1.50:8000/mcp/sse`).

### Available MCP Tools

| Tool | Parameters | Description |
| :--- | :--- | :--- |
| `stage_transaction` | `source_label`: string (e.g. `'amazon'`)<br>`external_id`: string (e.g. `'114-1234567-8901234'`)<br>`date`: string (`YYYY-MM-DD` or ISO timestamp)<br>`total_amount`: float (non-zero; negative for refunds)<br>`description`: string<br>`currency_code`: string (default `'CAD'`) | Ingests a transaction into Wrangler's Staging Area (`source = "mcp"`). Performs automated dual-table deduplication against existing staged and ledger transactions, returning an idempotent skip confirmation if already recorded. |
| `check_transaction_exists` | `source_label`: string<br>`external_id`: string | Pre-flight check to verify if a transaction exists in Wrangler before running scraping operations. Returns `{"exists": bool, "location": "staged"\|"ledger"\|null, "status": "STAGED"\|"ACCEPTED"\|"DISMISSED"\|"COMMITTED"\|null}`. |

---

## AI-Driven Development Workflow

This project takes a spec-driven approach to development. The process is as follows:
1. Use agy agent "sdd-architect" to create a new specification in `specs/<version>/N-short-name/<spec.md>`.
2. Use agy agent "sdd-planner" to create a plan and tasks for the specification in `specs/<version>/N-short-name/<plan.md>`.
3. Use agy agent "sdd-coder" to implement tasks defined in the plan.

Once a spec has been fully implemented, remove the tasks.md file.  The spec.md and plan.md files are retained for future AI context.
