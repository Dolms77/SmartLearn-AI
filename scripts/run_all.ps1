# Run pipeline 01..09 in order, then verify artifacts.
# Usage:
#   .\scripts\run_all.ps1                         # use the repository .venv-ui
#   .\scripts\run_all.ps1 -Python (Get-Command python).Source
#   .\scripts\run_all.ps1 -WithRag                # also run 04 (needs requirements-rag.txt)
#   .\scripts\run_all.ps1 -WithUI                 # launch UI when done
# NOTE: keep this file ASCII-only (no BOM); Chinese text breaks Windows PowerShell 5.1 parsing.
param(
    [switch]$WithRag,
    [switch]$WithUI,
    [string]$Python = ""
)
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
if ($Python) {
    $pythonCommand = Get-Command $Python -ErrorAction SilentlyContinue
    if (-not $pythonCommand) { throw "Python interpreter not found: $Python" }
    $vpy = $pythonCommand.Source
} else {
    $vpy = Join-Path $root ".venv-ui\Scripts\python.exe"
}
# Locate the script folder without typing non-ASCII names (keeps this file ASCII-only).
$src = (Get-ChildItem $root -Directory |
        Where-Object { Test-Path (Join-Path $_.FullName "01_data_loader.py") } |
        Select-Object -First 1).FullName
if (-not $src) { throw "script folder (01_data_loader.py) not found under $root" }

if (-not (Test-Path $vpy)) { throw "Python interpreter not found. Run scripts\bootstrap.ps1 or pass -Python." }

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
    @{ n = "06_dashboard";       f = "06_dashboard.py" },
    @{ n = "07_multi_agent";     f = "07_multi_agent.py" },
    @{ n = "08_task3_generator"; f = "08_task3_generator.py"; args = @("--all-students") },
    @{ n = "09_task1_knowledge_structure"; f = "09_task1_knowledge_structure.py" }
)

foreach ($s in $steps) {
    if ($s.n -eq "04_rag_knowledge" -and -not $WithRag) {
        Write-Host "SKIP 04_rag_knowledge (use -WithRag to enable)" -ForegroundColor DarkGray
        continue
    }
    $t0 = Get-Date
    Write-Host "=== $($s.n) ===" -ForegroundColor Cyan
    $code = 0
    $stepArgs = @()
    if ($s.ContainsKey("args")) { $stepArgs = $s.args }
    & $vpy (Join-Path $src $s.f) @stepArgs
    $code = $LASTEXITCODE
    if ($code -ne 0) {
        if ($s.optional) {
            Write-Host "  WARN $($s.n) failed (optional, continue). See requirements-rag.txt / requirements-scripts.txt." -ForegroundColor Yellow
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
