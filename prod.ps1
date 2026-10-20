param (
    [int]$Port = 8000,
    [string]$HostAddress = "0.0.0.0",
    [switch]$Migrate,
    [switch]$SkipMigration
)

$ErrorActionPreference = "Stop"
$ScriptDir = $PSScriptRoot
$ApiDir = Join-Path $ScriptDir "api"

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "       Wrangler Production Server       " -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan

# 1. Dependency Validation
if (-not (Get-Command "uv" -ErrorAction SilentlyContinue)) {
    Write-Error "'uv' is required to run Wrangler. Please install uv."
    exit 1
}

# 2. Smart Database Migration Check
Write-Host "`n[1/2] Checking database schema status..." -ForegroundColor Yellow
$MigrationStatus = & uv run --directory $ApiDir --link-mode copy python scripts/check_migrations.py
$StatusExit = $LASTEXITCODE

if ($StatusExit -eq 2) {
    # Exit code 2 indicates pending migrations detected
    $ShouldMigrate = $false
    if ($Migrate) {
        $ShouldMigrate = $true
    } elseif (-not $SkipMigration) {
        $response = Read-Host "Pending database migrations detected. Apply them now? [Y/n]"
        if ($response -eq "" -or $response -match "^[yY]") {
            $ShouldMigrate = $true
        }
    }

    if ($ShouldMigrate) {
        Write-Host "Applying database migrations..." -ForegroundColor Cyan
        & uv run --directory $ApiDir --link-mode copy alembic upgrade head
        if ($LASTEXITCODE -ne 0) {
            Write-Error "Database migration failed. Aborting startup."
            exit $LASTEXITCODE
        }
    } else {
        Write-Host "Skipping pending migrations." -ForegroundColor DarkGray
    }
} elseif ($StatusExit -eq 0) {
    Write-Host "Database schema is up to date." -ForegroundColor Green
} else {
    Write-Host "Warning: Could not determine migration status ($MigrationStatus). Continuing." -ForegroundColor DarkYellow
}

# 3. Launch Production Server with Clean Exit Trap
Write-Host "`n[2/2] Launching server on http://${HostAddress}:${Port}" -ForegroundColor Green
Write-Host "Press Ctrl+C to stop server and initiate backup.`n" -ForegroundColor DarkGray

$ServerStartedCleanly = $false

try {
    # Mark as cleanly running once Uvicorn is invoked
    $ServerStartedCleanly = $true
    & uv run --directory $ApiDir --link-mode copy uvicorn main:app --app-dir src --host $HostAddress --port $Port
} finally {
    Write-Host "`nShutting down Wrangler..." -ForegroundColor Yellow
    
    if ($ServerStartedCleanly) {
        Write-Host "Executing clean SQLite snapshot and mirroring receipts..." -ForegroundColor Cyan
        & uv run --directory $ApiDir --link-mode copy python scripts/wal_backup.py
        if ($LASTEXITCODE -eq 0) {
            Write-Host "Backup completed successfully." -ForegroundColor Green
        } else {
            Write-Host "Warning: Backup hook encountered an error." -ForegroundColor DarkYellow
        }
    } else {
        Write-Host "Startup was interrupted or failed. Backup skipped to protect existing snapshot." -ForegroundColor DarkYellow
    }
    
    Write-Host "Wrangler stopped cleanly." -ForegroundColor Green
}
