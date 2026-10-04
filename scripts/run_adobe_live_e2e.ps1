param(
    [string]$RunnerRoot = 'D:\actions-runner-adobe',
    [string]$Repository = 'caotiensinh/MCP_adobe',
    [string]$Workflow = 'adobe-windows-e2e.yml',
    [string]$Ref = 'main',
    [switch]$SkipXdPlugin,
    [switch]$NoLaunchXd,
    [switch]$NoXdLive,
    [switch]$XdWrite
)

$ErrorActionPreference = 'Stop'

if ($XdWrite -and $NoXdLive) {
    throw '-XdWrite requires XD live E2E. Remove -NoXdLive.'
}

$prepare = Join-Path $PSScriptRoot 'prepare_adobe_live_e2e.ps1'
$dispatch = Join-Path $PSScriptRoot 'dispatch_adobe_live_e2e.ps1'
if (-not (Test-Path $prepare)) { throw "Missing helper: $prepare" }
if (-not (Test-Path $dispatch)) { throw "Missing helper: $dispatch" }

$dispatchArgs = @{
    Repository = $Repository
    Workflow = $Workflow
    Ref = $Ref
}
if ($NoXdLive) { $dispatchArgs['NoXdLive'] = $true }
if ($XdWrite) { $dispatchArgs['XdWrite'] = $true }

Write-Host '=== MCP Adobe one-command live E2E ==='
Write-Host 'Preflight: verify GitHub CLI authentication before changing the runner service.'
& $dispatch @dispatchArgs -PreflightOnly

Write-Host ''
Write-Host 'Phase 1/2: prepare Adobe apps, XD bridge, and interactive MCP_adobe runner.'

$prepareArgs = @{
    RunnerRoot = $RunnerRoot
}
if ($SkipXdPlugin) { $prepareArgs['SkipXdPlugin'] = $true }
if ($NoLaunchXd) { $prepareArgs['NoLaunchXd'] = $true }
& $prepare @prepareArgs

Write-Host ''
Write-Host 'Phase 2/2: dispatch the guarded workflow_dispatch live E2E run.'
& $dispatch @dispatchArgs

Write-Host ''
Write-Host 'PASS: preparation and workflow dispatch completed.'
Write-Host 'Keep the interactive GitHub runner console open until the workflow finishes.'
if (-not $NoXdLive) {
    Write-Host 'In Adobe XD, reload development plugins if needed and keep Plugins > MCP Adobe Bridge visible.'
}
if ($XdWrite) {
    Write-Host 'When the XD mutation is queued, click Apply pending. Without that explicit approval the XD write must not PASS.'
}
