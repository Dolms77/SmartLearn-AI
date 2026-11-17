# Build the single-file Windows executable without touching the current output/.
param(
    [string]$Python = "",
    [string]$DataDir = ""
)
$ErrorActionPreference = "Stop"
$root = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot ".."))

if ($Python) {
    $pythonCommand = Get-Command $Python -ErrorAction SilentlyContinue
    if (-not $pythonCommand) { throw "Python interpreter not found: $Python" }
    $pythonExe = $pythonCommand.Source
} else {
    $pythonExe = Join-Path $root ".venv-ui\Scripts\python.exe"
}
if (-not (Test-Path -LiteralPath $pythonExe)) {
    throw "Python interpreter not found. Install dependencies or pass -Python."
}

$scriptDir = (Get-ChildItem -LiteralPath $root -Directory |
    Where-Object { Test-Path (Join-Path $_.FullName "01_data_loader.py") } |
    Select-Object -First 1).FullName
if (-not $scriptDir) { throw "Script directory containing 01_data_loader.py was not found." }

$env:SMARTLEARN_BUILD_ROOT = $root
& $pythonExe -c "import PyInstaller, networkx; from pyvis.network import Network"
if ($LASTEXITCODE -ne 0) {
    throw "Build dependencies missing. Run: $pythonExe -m pip install -r requirements-build.txt"
}

if ($DataDir) {
    $dataDir = (Resolve-Path -LiteralPath $DataDir -ErrorAction Stop).Path
} else {
    $encodedDataDir = & $pythonExe -c "import base64, os, sys; from pathlib import Path; sys.path.insert(0, os.path.join(os.environ['SMARTLEARN_BUILD_ROOT'], 'scripts')); import exe_runner; print(base64.b64encode(str(exe_runner._default_data_dir(Path(os.environ['SMARTLEARN_BUILD_ROOT']))).encode('utf-8')).decode('ascii'))"
    if ($LASTEXITCODE -ne 0) { throw "Could not locate the default input data directory." }
    $dataDir = [System.Text.Encoding]::UTF8.GetString(
        [System.Convert]::FromBase64String(($encodedDataDir | Select-Object -Last 1).Trim()))
}

$env:SMARTLEARN_DATA_DIR = $dataDir
& $pythonExe -c "import os, sys; from pathlib import Path; sys.path.insert(0, os.path.join(os.environ['SMARTLEARN_BUILD_ROOT'], 'scripts')); import exe_runner; exe_runner._validate_data_dir(Path(os.environ['SMARTLEARN_DATA_DIR']))"
if ($LASTEXITCODE -ne 0) { throw "Input data directory is incomplete." }

$buildId = [guid]::NewGuid().ToString("N")
$buildRoot = Join-Path $root ("build\exe-" + $buildId)
$payloadRoot = Join-Path $buildRoot "payload"
$payloadScripts = Join-Path $payloadRoot "completed_scripts"
$payloadData = Join-Path $payloadRoot "embedded_data"
$payloadVerification = Join-Path $payloadRoot "verification"
$bundleScriptNames = @(
    "01_data_loader.py",
    "02_bkt_model.py",
    "03_error_diagnosis.py",
    "05_knowledge_graph.py",
    "06_dashboard.py",
    "08_task3_generator.py",
    "09_task1_knowledge_structure.py"
)
$stagedDist = Join-Path $buildRoot "dist"
$workPath = Join-Path $buildRoot "work"
$specPath = Join-Path $buildRoot "spec"
$finalDist = Join-Path $root "dist"
$finalExe = Join-Path $finalDist "SmartLearn-AI.exe"
$verifyScript = Join-Path $PSScriptRoot "verify.py"
$entryScript = Join-Path $PSScriptRoot "exe_runner.py"

New-Item -ItemType Directory -Force `
    $payloadScripts, $payloadData, $payloadVerification, $stagedDist, $workPath, $specPath |
    Out-Null
foreach ($name in $bundleScriptNames) {
    $sourceScript = Join-Path $scriptDir $name
    if (-not (Test-Path -LiteralPath $sourceScript -PathType Leaf)) {
        throw "Required pipeline script not found: $name"
    }
    Copy-Item -LiteralPath $sourceScript -Destination $payloadScripts
}
Get-ChildItem -LiteralPath $dataDir -File -Filter "*.csv" | Copy-Item -Destination $payloadData
Copy-Item -LiteralPath $verifyScript -Destination (Join-Path $payloadVerification "verify.py")

$pyinstallerArgs = @(
    "-m", "PyInstaller",
    "--noconfirm",
    "--clean",
    "--onefile",
    "--console",
    "--name", "SmartLearn-AI",
    "--distpath", $stagedDist,
    "--workpath", $workPath,
    "--specpath", $specPath,
    "--add-data", ($payloadScripts + ";completed_scripts"),
    "--add-data", ($payloadData + ";embedded_data"),
    "--add-data", ($payloadVerification + ";verification"),
    "--collect-all", "networkx",
    "--collect-all", "pyvis",
    $entryScript
)

try {
    & $pythonExe @pyinstallerArgs
    if ($LASTEXITCODE -ne 0) { throw "PyInstaller failed with exit code $LASTEXITCODE." }

    $builtExe = Join-Path $stagedDist "SmartLearn-AI.exe"
    if (-not (Test-Path -LiteralPath $builtExe -PathType Leaf)) {
        throw "PyInstaller did not produce the expected executable."
    }

    New-Item -ItemType Directory -Force $finalDist | Out-Null
    $previousExe = $null
    if (Test-Path -LiteralPath $finalExe) {
        $previousExe = $finalExe + ".backup-" + (Get-Date -Format "yyyyMMdd_HHmmss_fff")
        Move-Item -LiteralPath $finalExe -Destination $previousExe
    }
    try {
        Move-Item -LiteralPath $builtExe -Destination $finalExe
    } catch {
        if ($previousExe -and (Test-Path -LiteralPath $previousExe)) {
            Move-Item -LiteralPath $previousExe -Destination $finalExe
        }
        throw
    }

    Remove-Item -LiteralPath $buildRoot -Recurse -Force
    Write-Output "Built: $finalExe"
    Write-Output "The current output/ directory was not modified."
} catch {
    Write-Error "Build failed. Intermediate files were retained at: $buildRoot"
    throw
}
