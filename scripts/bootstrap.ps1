# 一键准备环境：建 venv + 装依赖 + 自检
# 用法：
#   .\scripts\bootstrap.ps1
#   .\scripts\bootstrap.ps1 -Python "D:\python313\python.exe"
param(
    [string]$Python = "",
    [string]$Mirror = "https://pypi.tuna.tsinghua.edu.cn/simple"
)
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

function Find-Python {
    foreach ($c in @($script:Python, "D:\python313\python.exe", "python", "py")) {
        if (-not $c) { continue }
        try {
            $v = & $c -c "import sys;print(sys.version_info[0]*100+sys.version_info[1])" 2>$null
            if ($v -and [int]$v -ge 310) { return $c }
        } catch { }
    }
    throw "未找到 Python >= 3.10，请用 -Python 指定解释器路径"
}

$py = Find-Python
Write-Host "使用解释器: $py" -ForegroundColor Green

# 中文路径会让 pip 解包失败：临时目录指到 ASCII 路径
$tmp = Join-Path $root ".tmp"
New-Item -ItemType Directory -Force $tmp | Out-Null
$env:TEMP = $tmp
$env:TMP = $tmp

$venv = Join-Path $root ".venv-ui"
if (-not (Test-Path (Join-Path $venv "Scripts\python.exe"))) {
    Write-Host "创建虚拟环境 .venv-ui ..."
    & $py -m venv $venv
}
$vpy = Join-Path $venv "Scripts\python.exe"

Write-Host "安装依赖（镜像: $Mirror）..."
& $vpy -m pip install --no-cache-dir -i $Mirror -r (Join-Path $root "requirements.txt")

Write-Host "`n自检：" -ForegroundColor Green
& $vpy -c "import pandas,numpy,openpyxl,networkx,streamlit,plotly,openai;print('依赖 OK')"
& $vpy (Join-Path $root "ui\selftest.py")
