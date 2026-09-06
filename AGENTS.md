# Agent Guidelines & Development Standards

This document outlines project conventions, code styling rules, and execution commands for AI agents operating in this repository.

---

## 1. Code Styling & Formatting (Backend / `api`)

All Python code in `api/` must strictly adhere to the following standards (enforced via Ruff in [api/pyproject.toml](api/pyproject.toml)):

- **Line Length**: 160 characters (`line-length = 160`)
- **Imports**: Enforce **relative imports** for internal modules within the project.
- **Quote Style**: Double quotes (`quote-style = "double"`)
- **Indent Style**: Spaces (`indent-style = "space"`)
- **Magic Trailing Comma**: Retain trailing commas (`skip-magic-trailing-comma = false`)

---

## 2. Monorepo Workflow & Commands

This is a monorepo managed with `pnpm`:
- `api/`: Python 3.14 backend managed with `uv`
- `web/`: Vue 3 / Quasar frontend managed with `pnpm` (Phase 6)

Always run commands from the repository root. Base commands (`lint`, `format`) are check-only, while `:fix` commands write changes:

| Command | Purpose |
| :--- | :--- |
| `pnpm dev` | Run all workspace dev servers in parallel (or `pnpm dev:api` / `pnpm dev:web`) |
| `pnpm lint` | Run linter check across all projects (or `pnpm --filter api lint`) |
| `pnpm lint:fix` | Automatically apply fixes for lint errors across all projects (or `pnpm --filter api lint:fix`) |
| `pnpm format` | Check code formatting across all projects (or `pnpm --filter api format`) |
| `pnpm format:fix` | Format and write code changes across all projects (or `pnpm --filter api format:fix`) |
| `pnpm test` | Run backend test suite using Pytest (or `pnpm --filter api test`) |
| `pnpm build` | Build workspace packages (or `pnpm --filter web build`) |

---

## 3. Implementation Rules for Agents

1. **Format and Lint Verification**: After writing or modifying  code, run `pnpm format` and `pnpm lint` to ensure no formatting or lint regressions. Use `pnpm format:fix` or `pnpm lint:fix` to automatically apply fixes.
2. **Import Conventions**: Use relative imports when referencing internal modules (e.g., `from .config import settings` or `from ..database import Base`). Do not use `src.` prefixes.
3. **No Unnecessary `__init__.py`**: Subdirectories under `api/src/` (such as `routers/`, `models/`, `schemas/`, `services/`, `core/`) do not require `__init__.py` files.
4. **No Inline Python Execution**: Do not run ad-hoc inline Python snippets (`python -c "..."` or `uv run python -c "..."`) or multi-line shell commands. All testing and verification must occur through dedicated test files in `api/tests/` run via `pnpm test`.
5. **Test-Driven Verification**: Each model, endpoint, or service implementation must include or update unit/integration tests in `api/tests/` and be verified using `pnpm test` prior to marking a task complete.
