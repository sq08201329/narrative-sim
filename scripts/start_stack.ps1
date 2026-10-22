<#
.SYNOPSIS
    一键起停 narrative-sim 技术栈：嵌入服务 + 调研服务 + 叙事服务。

.DESCRIPTION
    固定顺序，顺序不反：
      1) embeddinggemma-2（嵌入服务，127.0.0.1:9379/v1）—— 先起，/v1/models 可用
      2) gptr-mcp（调研服务，127.0.0.1:8000/mcp）—— 次起，/health 通过
      3) narrative-sim（叙事服务，127.0.0.1:8300/mcp）—— 最后起

    停的顺序相反：先停叙事，再停调研，最后停嵌入。

    约定（踩过的坑都写死在这里）：
      - narrative-sim 必须显式带 NARRATIVE_DB，默认 data\yanyu.db（真库）；
        默认的 data\narrative_sim.db 是测试库，裸起会掉进去。
      - DEEPSEEK_API_KEY 从 narrative-sim\.env 读取，只注入子进程环境，绝不打印。
      - gptr-mcp 目录没有 .env，全靠启动环境变量。
      - 嵌入服务靠 litert-lm serve；模型 eg2-text-270m.litertlm 未导入时先导入。
      - 三个服务都用 Start-Process 起独立进程，shell 关了它们还在。
      - 已在线则跳过，可反复执行（幂等）。

.PARAMETER Action
    start（默认）| stop | restart | status

.PARAMETER DbPath
    覆盖数据库路径，默认 data\yanyu.db

.EXAMPLE
    pwsh -File scripts\start_stack.ps1 status
    pwsh -File scripts\start_stack.ps1 start
    pwsh -File scripts\start_stack.ps1 restart
#>
[CmdletBinding()]
param(
    [ValidateSet('start', 'stop', 'restart', 'status')]
    [string]$Action = 'start',

    [string]$DbPath = ''
)

$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

$Root            = Split-Path -Parent $PSScriptRoot
$GptrRoot        = 'D:\kimicode_repos\projects\my-gpt-research\gptr-mcp'
$EmbedRoot       = 'D:\gh_projects\embeddinggemma-2'
$EmbedPort       = 9379
$EmbedModel      = 'eg2-text-270m.litertlm'
$GptrPort        = 8000
$NarrativePort   = 8300
$NarrativePython = Join-Path $Root '.venv\Scripts\python.exe'
$GptrPython      = Join-Path $GptrRoot '.venv\Scripts\python.exe'
$GptrLogDir      = Join-Path $GptrRoot 'logs'
$EmbedLogDir     = Join-Path $EmbedRoot 'logs'

if (-not $DbPath) {
    $envDb = $env:NARRATIVE_DB
    $DbPath = if ($envDb) { $envDb } else { Join-Path $Root 'data\projects\linan.db' }
}

# ---------- 基础设施 ----------

function Get-ListenerPid([int]$Port) {
    $c = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue |
         Select-Object -First 1
    if ($c) { return [int]$c.OwningProcess }
    return $null
}

function Test-Http([string]$Url) {
    try {
        $r = Invoke-WebRequest -Uri $Url -TimeoutSec 5 -UseBasicParsing
        return ($r.StatusCode -eq 200)
    } catch { return $false }
}

function Wait-Http([string]$Url, [int]$Seconds = 40) {
    for ($i = 0; $i -lt $Seconds; $i++) {
        if (Test-Http $Url) { return $true }
        Start-Sleep -Seconds 1
    }
    return $false
}

function Get-DeepSeekKey {
    $envFile = Join-Path $Root '.env'
    if (-not (Test-Path $envFile)) { throw "找不到 $envFile" }
    $line = Get-Content $envFile |
            Where-Object { $_ -match '^\s*DEEPSEEK_API_KEY\s*=' } |
            Select-Object -First 1
    if (-not $line) { throw '.env 里没有 DEEPSEEK_API_KEY' }
    $key = ($line -split '=', 2)[1].Trim().Trim('"').Trim("'")
    if (-not $key) { throw 'DEEPSEEK_API_KEY 是空值' }
    return $key
}

# ---------- 1) 嵌入服务 ----------

function Get-EmbedStatus {
    $pid0 = Get-ListenerPid $EmbedPort
    [pscustomobject]@{
        Name   = 'embedding'
        Port   = $EmbedPort
        Pid    = $pid0
        Online = [bool]($pid0 -and (Test-Http "http://127.0.0.1:$EmbedPort/v1/models"))
    }
}

function Start-Embed {
    $st = Get-EmbedStatus
    if ($st.Online) {
        Write-Host "[embedding] 已在线（pid $($st.Pid)），跳过"
        return $true
    }
    if ($st.Pid) {
        Write-Host "[embedding] 端口 $EmbedPort 被 pid $($st.Pid) 占用但 /v1/models 不通，先停掉重起"
        Stop-Embed | Out-Null
        Start-Sleep -Seconds 2
    }
    $litert = (Get-Command litert-lm -ErrorAction SilentlyContinue)
    if (-not $litert) { throw 'PATH 里找不到 litert-lm' }
    $litertPath = $litert.Source

    $imported = & $litertPath list 2>&1 | Select-String $EmbedModel
    if (-not $imported) {
        Write-Host "[embedding] 模型未导入，先导入 $EmbedModel ..."
        $modelFile = Join-Path $EmbedRoot 'model.litertlm'
        & $litertPath import $modelFile $EmbedModel | Out-Null
        if ($LASTEXITCODE -ne 0) { throw "模型导入失败：$modelFile" }
    }

    New-Item -ItemType Directory -Force -Path $EmbedLogDir | Out-Null
    $outLog = Join-Path $EmbedLogDir 'embedding_server.log'
    $errLog = Join-Path $EmbedLogDir 'embedding_server.err.log'

    Write-Host "[embedding] 启动中（$EmbedModel @ $EmbedPort）..."
    $p = Start-Process -WindowStyle Hidden -FilePath $litertPath `
         -ArgumentList @('serve', '--host', '127.0.0.1', '--port', "$EmbedPort") `
         -WorkingDirectory $EmbedRoot `
         -RedirectStandardOutput $outLog -RedirectStandardError $errLog `
         -PassThru
    Set-Content -Path (Join-Path $EmbedLogDir 'embedding.pid') -Value $p.Id -Encoding ascii

    if (Wait-Http "http://127.0.0.1:$EmbedPort/v1/models" 40) {
        $lp = Get-ListenerPid $EmbedPort
        Write-Host "[embedding] 就绪：http://127.0.0.1:$EmbedPort/v1（pid $lp）"
        return $true
    }
    Write-Host "[embedding] 40s 内 /v1/models 未就绪，看日志：$errLog" -ForegroundColor Red
    return $false
}

function Stop-Embed {
    $pid0 = Get-ListenerPid $EmbedPort
    if (-not $pid0) {
        Remove-Item (Join-Path $EmbedLogDir 'embedding.pid') -ErrorAction SilentlyContinue
        Write-Host '[embedding] 未在运行'
        return
    }
    $proc = Get-CimInstance Win32_Process -Filter "ProcessId=$pid0"
    if (-not $proc -or $proc.CommandLine -notmatch 'litert-lm') {
        Write-Host "[embedding] pid $pid0 命令行不像 litert-lm，拒绝停止" -ForegroundColor Red
        return
    }
    Stop-Process -Id $pid0 -Force
    Remove-Item (Join-Path $EmbedLogDir 'embedding.pid') -ErrorAction SilentlyContinue
    Write-Host "[embedding] 已停止 pid $pid0"
}

# ---------- 2) 调研服务 gptr-mcp ----------

function Get-GptrStatus {
    $pid0 = Get-ListenerPid $GptrPort
    [pscustomobject]@{
        Name   = 'gptr-mcp'
        Port   = $GptrPort
        Pid    = $pid0
        Online = [bool]($pid0 -and (Test-Http "http://127.0.0.1:$GptrPort/health"))
    }
}

function Start-Gptr {
    $st = Get-GptrStatus
    if ($st.Online) {
        Write-Host "[gptr-mcp] 已在线（pid $($st.Pid)），跳过"
        return $true
    }
    if ($st.Pid) {
        Write-Host "[gptr-mcp] 端口 $GptrPort 被 pid $($st.Pid) 占用但健康检查不过，先停掉重起"
        Stop-Gptr | Out-Null
        Start-Sleep -Seconds 2
    }
    if (-not (Test-Path $GptrPython)) { throw "找不到 gptr-mcp 的 python: $GptrPython" }

    $key = Get-DeepSeekKey
    $env:PYTHONUTF8 = '1'
    $env:MCP_TRANSPORT = 'streamable-http'
    $env:RETRIEVER = 'deepseek'
    $env:FAST_LLM = 'deepseek:deepseek-flash'
    $env:SMART_LLM = 'deepseek:deepseek-flash'
    $env:STRATEGIC_LLM = 'deepseek:deepseek-flash'
    $env:DEEPSEEK_API_KEY = $key
    $env:OPENAI_API_KEY = $key
    $env:SMART_TOKEN_LIMIT = '8000'
    $env:STRATEGIC_TOKEN_LIMIT = '8000'

    New-Item -ItemType Directory -Force -Path $GptrLogDir | Out-Null
    $outLog = Join-Path $GptrLogDir 'gptr_server.log'
    $errLog = Join-Path $GptrLogDir 'gptr_server.err.log'

    Write-Host '[gptr-mcp] 启动中（调研服务，DeepSeek 检索腿）...'
    $p = Start-Process -WindowStyle Hidden -FilePath $GptrPython `
         -ArgumentList 'server.py' -WorkingDirectory $GptrRoot `
         -RedirectStandardOutput $outLog -RedirectStandardError $errLog `
         -PassThru
    Set-Content -Path (Join-Path $GptrLogDir 'gptr.pid') -Value $p.Id -Encoding ascii

    if (Wait-Http "http://127.0.0.1:$GptrPort/health" 40) {
        $lp = Get-ListenerPid $GptrPort
        Write-Host "[gptr-mcp] 就绪：http://127.0.0.1:$GptrPort/mcp（pid $lp）"
        return $true
    }
    Write-Host "[gptr-mcp] 40s 内健康检查未通过，看日志：$errLog" -ForegroundColor Red
    return $false
}

function Stop-Gptr {
    $pid0 = Get-ListenerPid $GptrPort
    if (-not $pid0) {
        Remove-Item (Join-Path $GptrLogDir 'gptr.pid') -ErrorAction SilentlyContinue
        Write-Host '[gptr-mcp] 未在运行'
        return
    }
    $proc = Get-CimInstance Win32_Process -Filter "ProcessId=$pid0"
    if (-not $proc -or $proc.CommandLine -notmatch 'server\.py') {
        Write-Host "[gptr-mcp] pid $pid0 命令行不像 server.py，拒绝停止" -ForegroundColor Red
        return
    }
    Stop-Process -Id $pid0 -Force
    Remove-Item (Join-Path $GptrLogDir 'gptr.pid') -ErrorAction SilentlyContinue
    Write-Host "[gptr-mcp] 已停止 pid $pid0"
}

# ---------- 3) 叙事服务 narrative-sim ----------

function Get-NarrativeStatus {
    $pid0 = Get-ListenerPid $NarrativePort
    [pscustomobject]@{
        Name   = 'narrative-sim'
        Port   = $NarrativePort
        Pid    = $pid0
        Online = [bool]$pid0
    }
}

function Invoke-NarrativeService([string]$Cmd) {
    if (-not (Test-Path $NarrativePython)) { throw "找不到 narrative-sim 的 python: $NarrativePython" }
    $env:NARRATIVE_DB = $DbPath
    $env:PYTHONIOENCODING = 'utf-8'
    Push-Location $Root
    try {
        & $NarrativePython 'scripts\mcp_service.py' $Cmd
        return ($LASTEXITCODE -eq 0)
    } finally {
        Pop-Location
    }
}

function Start-Narrative {
    $st = Get-NarrativeStatus
    if ($st.Online) {
        Write-Host "[narrative-sim] 已在线（pid $($st.Pid)），跳过"
        return $true
    }
    Write-Host "[narrative-sim] 启动中（库：$DbPath）..."
    $ok = Invoke-NarrativeService 'start'
    if ($ok -and (Get-ListenerPid $NarrativePort)) {
        Write-Host "[narrative-sim] 就绪：http://127.0.0.1:$NarrativePort/mcp"
        return $true
    }
    Write-Host "[narrative-sim] 启动失败，看日志：$Root\logs\mcp_server.log" -ForegroundColor Red
    return $false
}

# ---------- 入口 ----------

switch ($Action) {
    'status' {
        $e = Get-EmbedStatus
        $g = Get-GptrStatus
        $n = Get-NarrativeStatus
        foreach ($s in @($e, $g, $n)) {
            $state = if ($s.Online) { "在线 pid $($s.Pid)" } else { '离线' }
            Write-Host ("{0,-14} :{1}  {2}" -f $s.Name, $s.Port, $state)
        }
        if ($e.Online -and $g.Online -and $n.Online) { exit 0 } else { exit 1 }
    }
    'start' {
        if (-not (Start-Embed)) {
            Write-Host '嵌入服务没起来，后面的不启动（顺序不反）' -ForegroundColor Red
            exit 1
        }
        if (-not (Start-Gptr)) {
            Write-Host '调研服务没起来，叙事服务不启动（顺序不反）' -ForegroundColor Red
            exit 1
        }
        if (Start-Narrative) { Write-Host '技术栈就绪。' -ForegroundColor Green; exit 0 }
        exit 1
    }
    'stop' {
        Invoke-NarrativeService 'stop' | Out-Null
        Write-Host '[narrative-sim] 已停止'
        Stop-Gptr
        Stop-Embed
        exit 0
    }
    'restart' {
        Invoke-NarrativeService 'stop' | Out-Null
        Write-Host '[narrative-sim] 已停止'
        Stop-Gptr
        Stop-Embed
        Start-Sleep -Seconds 2
        if (-not (Start-Embed)) { Write-Host '嵌入服务没起来，后面的不启动' -ForegroundColor Red; exit 1 }
        if (-not (Start-Gptr)) { Write-Host '调研服务没起来，叙事服务不启动' -ForegroundColor Red; exit 1 }
        if (Start-Narrative) { Write-Host '技术栈就绪。' -ForegroundColor Green; exit 0 }
        exit 1
    }
}
