param(
    [string]$Repository = 'caotiensinh/MCP_adobe',
    [string]$Workflow = 'adobe-windows-e2e.yml',
    [string]$Ref = 'main',
    [switch]$NoXdLive,
    [switch]$XdWrite,
    [switch]$PreflightOnly,
    [switch]$BootstrapOnly
)

$ErrorActionPreference = 'Stop'

if ($XdWrite -and $NoXdLive) {
    throw '-XdWrite requires XD live E2E. Remove -NoXdLive.'
}

function Get-PortableGhRoot {
    if (-not [string]::IsNullOrWhiteSpace($env:MCP_ADOBE_GH_PORTABLE_DIR)) {
        return $env:MCP_ADOBE_GH_PORTABLE_DIR
    }

    $base = $env:LOCALAPPDATA
    if ([string]::IsNullOrWhiteSpace($base)) {
        $base = $env:TEMP
    }
    if ([string]::IsNullOrWhiteSpace($base)) {
        $base = $PSScriptRoot
    }
    return (Join-Path $base 'MCPAdobe\tools\gh')
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
    $candidates += (Join-Path (Get-PortableGhRoot) 'gh.exe')

    foreach ($candidate in $candidates) {
        if (Test-Path -LiteralPath $candidate -PathType Leaf) {
            return (Resolve-Path -LiteralPath $candidate).Path
        }
    }

    return $null
}

function Install-GitHubCliPortable {
    $portableRoot = Get-PortableGhRoot
    New-Item -ItemType Directory -Force -Path $portableRoot | Out-Null
    $portableGh = Join-Path $portableRoot 'gh.exe'

    $releaseApi = $env:MCP_ADOBE_GH_RELEASE_API_URL
    if ([string]::IsNullOrWhiteSpace($releaseApi)) {
        $releaseApi = 'https://api.github.com/repos/cli/cli/releases/latest'
    }

    Write-Host 'Installing portable GitHub CLI directly from the official GitHub CLI release...'
    Write-Host "  release_api=$releaseApi"
    Write-Host "  destination=$portableGh"

    try {
        [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
        $headers = @{
            'Accept' = 'application/vnd.github+json'
            'User-Agent' = 'MCP-adobe-live-e2e-bootstrap'
            'X-GitHub-Api-Version' = '2022-11-28'
        }
        $release = Invoke-RestMethod -Uri $releaseApi -Headers $headers -Method Get
        $asset = @($release.assets) | Where-Object {
            $_.name -match '^gh_[0-9.]+_windows_amd64\.zip$'
        } | Select-Object -First 1
        if (-not $asset) {
            throw 'Latest GitHub CLI release did not contain a windows_amd64 ZIP asset.'
        }

        $downloadUrl = [string]$asset.browser_download_url
        if ([string]::IsNullOrWhiteSpace($downloadUrl)) {
            throw 'GitHub CLI release asset did not provide browser_download_url.'
        }
        if ($releaseApi -eq 'https://api.github.com/repos/cli/cli/releases/latest' -and
            $downloadUrl -notmatch '^https://github\.com/cli/cli/releases/download/') {
            throw "Refusing unexpected GitHub CLI download URL: $downloadUrl"
        }

        $workRoot = Join-Path ([IO.Path]::GetTempPath()) ("mcp-adobe-gh-" + [guid]::NewGuid().ToString('N'))
        $archive = Join-Path $workRoot 'gh.zip'
        $extract = Join-Path $workRoot 'extract'
        New-Item -ItemType Directory -Force -Path $extract | Out-Null
        try {
            Write-Host "Downloading $($asset.name)..."
            Invoke-WebRequest -Uri $downloadUrl -Headers $headers -OutFile $archive -UseBasicParsing

            $digest = $null
            if ($asset.PSObject.Properties.Name -contains 'digest') {
                $digest = [string]$asset.digest
            }
            if (-not [string]::IsNullOrWhiteSpace($digest) -and $digest -match '^sha256:([0-9a-fA-F]{64})$') {
                $expectedSha256 = $Matches[1].ToLowerInvariant()
                $actualSha256 = (Get-FileHash -LiteralPath $archive -Algorithm SHA256).Hash.ToLowerInvariant()
                if ($actualSha256 -ne $expectedSha256) {
                    throw "GitHub CLI archive SHA-256 mismatch. expected=$expectedSha256 actual=$actualSha256"
                }
                Write-Host "PASS: GitHub CLI archive SHA-256 verified: $actualSha256"
            } else {
                Write-Host 'GitHub release did not expose a SHA-256 digest; relying on the official HTTPS release endpoint.'
            }

            Expand-Archive -LiteralPath $archive -DestinationPath $extract -Force
            $extractedGh = Get-ChildItem -LiteralPath $extract -Filter 'gh.exe' -File -Recurse | Select-Object -First 1
            if (-not $extractedGh) {
                throw 'Downloaded GitHub CLI ZIP did not contain gh.exe.'
            }

            Copy-Item -LiteralPath $extractedGh.FullName -Destination $portableGh -Force
        } finally {
            Remove-Item -LiteralPath $workRoot -Recurse -Force -ErrorAction SilentlyContinue
        }

        if (-not (Test-Path -LiteralPath $portableGh -PathType Leaf)) {
            throw 'Portable GitHub CLI extraction completed but gh.exe was not created.'
        }

        & $portableGh --version
        if ($LASTEXITCODE -ne 0) {
            throw "Portable GitHub CLI failed its version probe with exit code $LASTEXITCODE."
        }
        Write-Host "PASS: Portable GitHub CLI ready: $portableGh"
        return (Resolve-Path -LiteralPath $portableGh).Path
    } catch {
        throw "Portable GitHub CLI bootstrap failed: $($_.Exception.Message)"
    }
}

function Install-GitHubCli {
    $forcePortable = $env:MCP_ADOBE_GH_INSTALL_MODE -eq 'portable'
    $winget = $null
    if (-not $forcePortable) {
        $winget = Get-Command winget -CommandType Application -ErrorAction SilentlyContinue | Select-Object -First 1
    }

    if ($winget) {
        Write-Host 'GitHub CLI was not found. Installing GitHub CLI with winget...'
        & $winget.Source install --id GitHub.cli --exact --source winget --accept-source-agreements --accept-package-agreements
        if ($LASTEXITCODE -eq 0) {
            $installed = Resolve-GitHubCli
            if ($installed) {
                Write-Host "PASS: GitHub CLI installed: $installed"
                return $installed
            }
            Write-Warning 'winget completed but gh.exe could not be located; falling back to portable GitHub CLI.'
        } else {
            Write-Warning "winget GitHub CLI installation failed with exit code $LASTEXITCODE; falling back to portable GitHub CLI."
        }
    } elseif ($forcePortable) {
        Write-Host 'Portable GitHub CLI bootstrap explicitly selected by MCP_ADOBE_GH_INSTALL_MODE=portable.'
    } else {
        Write-Host 'winget was not found. Falling back to portable GitHub CLI bootstrap.'
    }

    return Install-GitHubCliPortable
}

$ghPath = Resolve-GitHubCli
if (-not $ghPath) {
    if ($env:MCP_ADOBE_NO_AUTO_INSTALL_GH -eq '1') {
        throw 'GitHub CLI (gh) was not found and automatic installation is disabled by MCP_ADOBE_NO_AUTO_INSTALL_GH=1.'
    }
    $ghPath = Install-GitHubCli
}

Write-Host "GitHub CLI=$ghPath"

if ($BootstrapOnly) {
    & $ghPath --version
    if ($LASTEXITCODE -ne 0) {
        throw "GitHub CLI bootstrap version probe failed with exit code $LASTEXITCODE."
    }
    Write-Host 'PASS: GitHub CLI bootstrap ready.'
    return
}

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
