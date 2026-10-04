param(
    [string]$Repository = 'caotiensinh/MCP_adobe',
    [string]$Workflow = 'adobe-windows-e2e.yml',
    [string]$Ref = 'main',
    [switch]$NoXdLive,
    [switch]$XdWrite
)

$ErrorActionPreference = 'Stop'

if ($XdWrite -and $NoXdLive) {
    throw '-XdWrite requires XD live E2E. Remove -NoXdLive.'
}

$gh = Get-Command gh -CommandType Application -ErrorAction SilentlyContinue | Select-Object -First 1
if (-not $gh) {
    throw 'GitHub CLI (gh) was not found in PATH. Install gh and authenticate with `gh auth login` before dispatching live E2E.'
}

& $gh.Source auth status --hostname github.com
if ($LASTEXITCODE -ne 0) {
    throw 'GitHub CLI is not authenticated for github.com. Run `gh auth login`, then retry.'
}

$xdLiveValue = (-not $NoXdLive).ToString().ToLowerInvariant()
$xdWriteValue = $XdWrite.IsPresent.ToString().ToLowerInvariant()

$arguments = @(
    'workflow', 'run', $Workflow,
    '--repo', $Repository,
    '--ref', $Ref,
    '-f', 'run_adobe_live=true',
    '-f', "xd_live=$xdLiveValue",
    '-f', "xd_write=$xdWriteValue"
)

Write-Host 'Dispatching Adobe live E2E:'
Write-Host "  repository=$Repository"
Write-Host "  workflow=$Workflow"
Write-Host "  ref=$Ref"
Write-Host '  run_adobe_live=true'
Write-Host "  xd_live=$xdLiveValue"
Write-Host "  xd_write=$xdWriteValue"

& $gh.Source @arguments
if ($LASTEXITCODE -ne 0) {
    throw "GitHub workflow dispatch failed with exit code $LASTEXITCODE."
}

Write-Host ''
Write-Host 'PASS: Adobe live E2E workflow dispatched.'
Write-Host "Actions: https://github.com/$Repository/actions/workflows/$Workflow"
if (-not $NoXdLive) {
    Write-Host 'Before the XD step runs, keep Adobe XD open and the Plugins > MCP Adobe Bridge panel visible.'
}
if ($XdWrite) {
    Write-Host 'XD write verification still requires you to click Apply pending in the MCP Adobe Bridge panel.'
}
