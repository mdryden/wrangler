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

---

## Running in Development

Use `pnpm` from the root workspace directory to run services:

### Start the API in Hot-Reload Mode

```bash
pnpm dev:api
```

*(or simply `pnpm dev`, which executes `uv run --directory api uvicorn main:app --reload`)*

The server will launch with auto-reload enabled:
- **API Base URL**: `http://localhost:8000`
- **Interactive Swagger Docs**: `http://localhost:8000/docs`
- **ReDoc Documentation**: `http://localhost:8000/redoc`
- **Health Check**: `http://localhost:8000/api/health`
