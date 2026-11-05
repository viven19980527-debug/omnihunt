# OmniHunt 快捷入口（Windows PowerShell）
# 用法:
#   .\run.ps1 "关键词"              普通搜索
#   .\run.ps1 "关键词" -Kinds onion 只看暗网
#   .\run.ps1 -Serve                启动 Web UI (127.0.0.1:7860)
#   .\run.ps1 -Serve -Port 8080
#   .\run.ps1 "关键词" -Offline     离线 fixture 演示
param(
    [Parameter(Position = 0)][string]$Query = "",
    [string]$Kinds = "",
    [int]$Limit = 40,
    [switch]$Serve,
    [int]$Port = 7860,
    [switch]$Offline,
    [switch]$Patterns,
    [string]$Json = ""
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$env:PYTHONPATH = $root
$python = "python"

if ($Serve) {
    $args = @("-m", "omnihunt", "serve", "--port", "$Port")
    if ($Offline) { $args += "--offline" }
    & $python @args
    return
}

if (-not $Query) {
    Write-Host "用法: .\run.ps1 `"关键词`" [-Kinds web,onion,adult,torrent] [-Limit 40] [-Patterns] [-Json out.json] [-Offline]"
    Write-Host "      .\run.ps1 -Serve [-Port 7860] [-Offline]"
    exit 1
}

$args = @("-m", "omnihunt", "search", $Query, "--limit", "$Limit")
if ($Kinds) { $args += @("--kinds", $Kinds) }
if ($Offline) { $args += "--offline" }
if ($Patterns) { $args += "--patterns" }
if ($Json) { $args += @("--json", $Json) }
& $python @args
