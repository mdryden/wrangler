param (
    [string]$TargetDir = "D:\Wrangler",
    [switch]$SkipBuild
)

$ErrorActionPreference = "Stop"
$ScriptDir = $PSScriptRoot

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "     Wrangler Release Packaging         " -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "Target Directory: $TargetDir" -ForegroundColor DarkGray

# 1. Dependency Checks
if (-not (Get-Command "uv" -ErrorAction SilentlyContinue)) {
    Write-Error "'uv' was not found in PATH. Please install uv."
    exit 1
}
if (-not (Get-Command "pnpm" -ErrorAction SilentlyContinue)) {
    Write-Error "'pnpm' was not found in PATH. Please install pnpm."
    exit 1
}

# 2. Compile Frontend SPA
if (-not $SkipBuild) {
    Write-Host "`n[1/4] Compiling frontend assets (Vite)..." -ForegroundColor Yellow
    & pnpm --filter web build
    if ($LASTEXITCODE -ne 0) {
        Write-Error "Frontend compilation failed."
        exit $LASTEXITCODE
    }
} else {
    Write-Host "`n[1/4] Skipping frontend build (-SkipBuild specified)." -ForegroundColor DarkGray
}

$DistPath = Join-Path $ScriptDir "web\dist"
if (-not (Test-Path (Join-Path $DistPath "index.html"))) {
    Write-Error "web/dist/index.html not found. Run without -SkipBuild."
    exit 1
}

# 3. Prepare Target Structure
Write-Host "`n[2/4] Preparing production target directory..." -ForegroundColor Yellow
$TargetApi = Join-Path $TargetDir "api"
$TargetWeb = Join-Path $TargetDir "web"

New-Item -ItemType Directory -Force -Path $TargetApi | Out-Null
New-Item -ItemType Directory -Force -Path $TargetWeb | Out-Null

# 4. Copy Code & Runtime Assets (STRICT: Never touch .env or data/)
Write-Host "`n[3/4] Copying runtime code and compiled assets..." -ForegroundColor Yellow

# Copy Backend Assets
$RoboFlags = @("/MIR", "/FFT", "/Z", "/NP", "/NDL", "/NJS", "/NJH")
& robocopy (Join-Path $ScriptDir "api\src") (Join-Path $TargetApi "src") $RoboFlags | Out-Null
& robocopy (Join-Path $ScriptDir "api\alembic") (Join-Path $TargetApi "alembic") $RoboFlags | Out-Null
& robocopy (Join-Path $ScriptDir "api\scripts") (Join-Path $TargetApi "scripts") $RoboFlags | Out-Null

Copy-Item (Join-Path $ScriptDir "api\alembic.ini") $TargetApi -Force
Copy-Item (Join-Path $ScriptDir "api\pyproject.toml") $TargetApi -Force
Copy-Item (Join-Path $ScriptDir "api\uv.lock") $TargetApi -Force

# Copy Compiled Frontend Assets
& robocopy $DistPath (Join-Path $TargetWeb "dist") $RoboFlags | Out-Null

# Copy Production Launcher
Copy-Item (Join-Path $ScriptDir "prod.ps1") $TargetDir -Force

Write-Host "Code and compiled assets copied successfully." -ForegroundColor Green
Write-Host "Verified: .env and data directories remain untouched." -ForegroundColor DarkGray

# 5. Synchronize Production Virtualenv
Write-Host "`n[4/4] Synchronizing production Python environment..." -ForegroundColor Yellow
& uv sync --directory $TargetApi --no-dev --link-mode copy
if ($LASTEXITCODE -ne 0) {
    Write-Error "Production dependency sync failed."
    exit $LASTEXITCODE
}

Write-Host "`nRelease successfully deployed to $TargetDir!" -ForegroundColor Green
Write-Host "To start Wrangler, run:" -ForegroundColor Cyan
Write-Host "  cd `"$TargetDir`"; .\prod.ps1`n" -ForegroundColor White
