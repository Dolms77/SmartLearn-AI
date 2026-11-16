# Run pipeline 01..06 in order, then verify artifacts.
# Usage:
#   .\scripts\run_all.ps1              # 01,02,03,06 (+05 if pyvis installed); skips 04
#   .\scripts\run_all.ps1 -WithRag     # also run 04 (needs requirements-rag.txt)
#   .\scripts\run_all.ps1 -WithUI      # launch UI when done
# NOTE: keep this file ASCII-only (no BOM); Chinese text breaks Windows PowerShell 5.1 parsing.
param(
    [switch]$WithRag,
    [switch]$WithUI
)
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$vpy = Join-Path $root ".venv-ui\Scripts\python.exe"
# Locate the script folder without typing non-ASCII names (keeps this file ASCII-only).
$src = (Get-ChildItem $root -Directory |
        Where-Object { Test-Path (Join-Path $_.FullName "01_data_loader.py") } |
        Select-Object -First 1).FullName
if (-not $src) { throw "script folder (01_data_loader.py) not found under $root" }

if (-not (Test-Path $vpy)) { throw "venv not found. Run scripts\bootstrap.ps1 first." }

# SS_DATA / SS_OUT are optional overrides. When unset, each script resolves paths
# relative to its own folder (..\output and ..\CSV data folder), so moving the whole
# project to another disk needs no edit.
if ($env:SS_OUT) { New-Item -ItemType Directory -Force $env:SS_OUT | Out-Null }
"OUTPUT = " + $(if ($env:SS_OUT) { $env:SS_OUT } else { "output/ (default, resolved by scripts)" })
"DATA   = " + $(if ($env:SS_DATA) { $env:SS_DATA } else { "default CSV folder (resolved by 01)" })
""

$steps = @(
    @{ n = "01_data_loader";     f = "01_data_loader.py" },
    @{ n = "02_bkt_model";       f = "02_bkt_model.py" },
    @{ n = "03_error_diagnosis"; f = "03_error_diagnosis.py" },
    @{ n = "04_rag_knowledge";   f = "04_rag_knowledge.py"; optional = $true },
    @{ n = "05_knowledge_graph"; f = "05_knowledge_graph.py"; optional = $true },
    @{ n = "06_dashboard";       f = "06_dashboard.py" }
)

foreach ($s in $steps) {
    if ($s.n -eq "04_rag_knowledge" -and -not $WithRag) {
        Write-Host "SKIP 04_rag_knowledge (use -WithRag to enable)" -ForegroundColor DarkGray
        continue
    }
    $t0 = Get-Date
    Write-Host "=== $($s.n) ===" -ForegroundColor Cyan
    $code = 0
    & $vpy (Join-Path $src $s.f)
    $code = $LASTEXITCODE
    if ($code -ne 0) {
        if ($s.optional) {
            Write-Host "  WARN $($s.n) failed (optional, continue). Missing deps? see requirements-rag.txt / pyvis." -ForegroundColor Yellow
            continue
        }
        throw "$($s.n) failed with exit code $code"
    }
    "  elapsed {0:n1}s" -f ((Get-Date) - $t0).TotalSeconds
}

Write-Host "`nVerify artifacts ..." -ForegroundColor Green
& $vpy (Join-Path $PSScriptRoot "verify.py")
if ($LASTEXITCODE -ne 0) { throw "artifact verification failed" }

if ($WithUI) {
    Write-Host "`nLaunch UI ..." -ForegroundColor Green
    & (Join-Path $root "ui\run.bat")
}
