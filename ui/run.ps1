# Launcher for SmartStudy UI.
# Fixes two Windows issues automatically:
#   1) [WinError 5] Access denied on C:\Users\<name>\.streamlit  -> redirect HOME to .streamlit-home
#   2) first-run "Email:" prompt                                -> pre-write credentials.toml
# Usage:
#   .\run.ps1
#   .\run.ps1 --server.port 8600
# If script execution is blocked, use run.bat instead.
$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot
$py = Join-Path $root ".venv-ui\Scripts\python.exe"

if (-not (Test-Path $py)) {
    Write-Host "venv not found: $py" -ForegroundColor Red
    Write-Host "Run first:" -ForegroundColor Yellow
    Write-Host '  D:\python313\python.exe -m venv .venv-ui'
    Write-Host '  $env:TEMP="D:\tmp-pip"; .venv-ui\Scripts\python.exe -m pip install -r requirements-ui.txt'
    exit 1
}

$homeDir = Join-Path $root ".streamlit-home"
$cfg = Join-Path $homeDir ".streamlit"
New-Item -ItemType Directory -Force $cfg | Out-Null
$cred = Join-Path $cfg "credentials.toml"
if (-not (Test-Path $cred)) {
    $content = "[general]`nemail = `"`"`n"
    [System.IO.File]::WriteAllText($cred, $content, [System.Text.UTF8Encoding]::new($false))
}
$env:USERPROFILE = $homeDir
$env:HOME = $homeDir

$tmp = Join-Path $root ".tmp"
New-Item -ItemType Directory -Force $tmp | Out-Null
$env:TEMP = $tmp
$env:TMP = $tmp

$appPath = Join-Path $PSScriptRoot "app.py"
$all = @("--server.headless=true", "--browser.gatherUsageStats=false") + $args

Write-Host "Starting: http://localhost:8501" -ForegroundColor Green
& $py -m streamlit run $appPath @all
