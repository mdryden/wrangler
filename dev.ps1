param (
    [ValidateSet("all", "api", "web")]
    [string]$Target = "all"
)

$ErrorActionPreference = "Stop"
$ScriptDir = $PSScriptRoot

switch ($Target) {
    "api" {
        Write-Host "Starting API server with uv..." -ForegroundColor Cyan
        & uv run --directory "$ScriptDir\api" python src/main.py
    }
    "web" {
        Write-Host "Starting Web dev server with Vite..." -ForegroundColor Cyan
        & pnpm --filter "./web" dev
    }
    "all" {
        Write-Host "Starting API and Web servers via concurrently..." -ForegroundColor Cyan
        $concurrently = "$ScriptDir\node_modules\.bin\concurrently.ps1"
        if (-not (Test-Path $concurrently)) {
            Write-Error "concurrently is not installed. Run 'pnpm install' first."
            exit 1
        }
        & $concurrently -k -n "api,web" -c "blue,green" `
            "uv run --directory `"$ScriptDir\api`" python src/main.py" `
            "pnpm --filter ./web dev"
    }
}
