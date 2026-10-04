param(
    [string]$Repository = 'caotiensinh/MCP_adobe',
    [string]$Workflow = 'adobe-windows-e2e.yml',
    [string]$Ref = 'main',
    [switch]$NoXdLive,
    [switch]$XdWrite,
    [switch]$PreflightOnly
)

$ErrorActionPreference = 'Stop'

if ($XdWrite -and $NoXdLive) {
    throw '-XdWrite requires XD live E2E. Remove -NoXdLive.'
}

function Resolve-GitHubCli {
    if (-not [string]::IsNullOrWhiteSpace($env:MCP_ADOBE_GH_PATH)) {
        if (Test-Path -LiteralPath $env:MCP_ADOBE_GH_PATH -PathType Leaf) {
            return (Resolve-Path -LiteralPath $env:MCP_ADOBE_GH_PATH).Path
        }
    }

    $command = Get-Command gh -CommandType Application -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($command) {
        return $command.Source
    }

    $candidates = @()
    if (-not [string]::IsNullOrWhiteSpace($env:ProgramFiles)) {
        $candidates += (Join-Path $env:ProgramFiles 'GitHub CLI\gh.exe')
    }
    if (-not [string]::IsNullOrWhiteSpace(${env:ProgramFiles(x86)})) {
        $candidates += (Join-Path ${env:ProgramFiles(x86)} 'GitHub CLI\gh.exe')
    }
    if (-not [string]::IsNullOrWhiteSpace($env:LOCALAPPDATA)) {
        $candidates += (Join-Path $env:LOCALAPPDATA 'Microsoft\WinGet\Links\gh.exe')
    }

    foreach ($candidate in $candidates) {
        if (Test-Path -LiteralPath $candidate -PathType Leaf) {
            return (Resolve-Path -LiteralPath $candidate).Path
        }
    }

    return $null
}

function Install-GitHubCli {
    $winget = Get-Command winget -CommandType Application -ErrorAction SilentlyContinue | Select-Object -First 1
    if (-not $winget) {
        throw 'GitHub CLI (gh) is missing and winget was not found. Install GitHub CLI, then rerun this command.'
    }

    Write-Host 'GitHub CLI was not found. Installing GitHub CLI with winget...'
    & $winget.Source install --id GitHub.cli --exact --source winget --accept-source-agreements --accept-package-agreements
    if ($LASTEXITCODE -ne 0) {
        throw "GitHub CLI installation failed with exit code $LASTEXITCODE."
    }

    $installed = Resolve-GitHubCli
    if (-not $installed) {
        throw 'GitHub CLI installation completed but gh.exe still could not be located. Open a new PowerShell window and rerun the command.'
    }

    Write-Host "PASS: GitHub CLI installed: $installed"
    return $installed
}

$ghPath = Resolve-GitHubCli
if (-not $ghPath) {
    if ($env:MCP_ADOBE_NO_AUTO_INSTALL_GH -eq '1') {
        throw 'GitHub CLI (gh) was not found and automatic installation is disabled by MCP_ADOBE_NO_AUTO_INSTALL_GH=1.'
    }
    $ghPath = Install-GitHubCli
}

Write-Host "GitHub CLI=$ghPath"

& $ghPath auth status --hostname github.com
if ($LASTEXITCODE -ne 0) {
    if ($env:MCP_ADOBE_NO_AUTO_AUTH_GH -eq '1') {
        throw 'GitHub CLI is not authenticated for github.com and automatic web authentication is disabled by MCP_ADOBE_NO_AUTO_AUTH_GH=1.'
    }

    Write-Host 'GitHub CLI is not authenticated. Starting GitHub web login...'
    & $ghPath auth login --hostname github.com --git-protocol https --web
    if ($LASTEXITCODE -ne 0) {
        throw "GitHub CLI authentication failed with exit code $LASTEXITCODE."
    }

    & $ghPath auth status --hostname github.com
    if ($LASTEXITCODE -ne 0) {
        throw 'GitHub CLI authentication did not become ready after login.'
    }
}

if ($PreflightOnly) {
    Write-Host 'PASS: GitHub CLI live-E2E dispatch preflight.'
    return
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

& $ghPath @arguments
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
