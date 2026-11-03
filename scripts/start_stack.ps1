<#
.SYNOPSIS
    narrative-sim 技术栈兼容入口；实际生命周期由统一 CLI 管理。
.EXAMPLE
    pwsh -File scripts\start_stack.ps1 start
    pwsh -File scripts\start_stack.ps1 status
    pwsh -File scripts\start_stack.ps1 restart -DbPath data\projects\linan.db
#>
[CmdletBinding()]
param(
    [ValidateSet('start', 'stop', 'restart', 'status')]
    [string]$Action = 'start',
    [string]$DbPath = ''
)

$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $PSScriptRoot
$Python = Join-Path $Root '.venv\Scripts\python.exe'
if (-not (Test-Path $Python)) { throw "找不到项目 Python，请先运行 uv sync: $Python" }
if ($DbPath) { $env:NARRATIVE_DB = [System.IO.Path]::GetFullPath($DbPath, $Root) }

Push-Location $Root
try {
    & $Python '-m' 'orchestrator.cli' $Action
    exit $LASTEXITCODE
} finally {
    Pop-Location
}
