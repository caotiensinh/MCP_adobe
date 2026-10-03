param(
    [string]$DevelopFolder,
    [string]$PluginId,
    [switch]$NoReloadHint
)

$ErrorActionPreference = 'Stop'

$repoRoot = Split-Path -Parent $PSScriptRoot
$source = Join-Path $repoRoot 'adobe-xd-plugin'
if (-not (Test-Path (Join-Path $source 'manifest.json'))) {
    throw "Adobe XD plugin manifest not found: $source"
}
if (-not (Test-Path (Join-Path $source 'main.js'))) {
    throw "Adobe XD plugin main.js not found: $source"
}

function Resolve-XdDevelopFolder {
    param([string]$ExplicitPath)

    if ($ExplicitPath) {
        return [System.IO.Path]::GetFullPath((Resolve-Path -LiteralPath $ExplicitPath).Path)
    }

    if (-not $env:LOCALAPPDATA) {
        throw 'LOCALAPPDATA is unavailable. Run this from the logged-in Windows user account that owns the Adobe XD installation.'
    }

    $packagesRoot = Join-Path $env:LOCALAPPDATA 'Packages'
    $candidates = @(
        Get-ChildItem -LiteralPath $packagesRoot -Directory -Filter 'Adobe.CC.XD_*' -ErrorAction SilentlyContinue |
            ForEach-Object { Join-Path $_.FullName 'LocalState\develop' }
    )

    $documented = Join-Path $packagesRoot 'Adobe.CC.XD_adky2gkssdxte\LocalState\develop'
    if ($candidates -notcontains $documented) {
        $candidates = @($documented) + $candidates
    }

    foreach ($candidate in $candidates | Select-Object -Unique) {
        $localState = Split-Path -Parent $candidate
        if (Test-Path $localState) {
            if (-not (Test-Path $candidate)) {
                New-Item -ItemType Directory -Force -Path $candidate | Out-Null
            }
            return [System.IO.Path]::GetFullPath($candidate)
        }
    }

    throw @'
Adobe XD LocalState/develop folder was not found for the current Windows user.
Open Adobe XD and use: Plugins > Development > Show Develop Folder
Then rerun this script with -DevelopFolder "<that folder>".
'@
}

$develop = Resolve-XdDevelopFolder -ExplicitPath $DevelopFolder
$destination = Join-Path $develop 'MCPAdobeBridge'

Write-Host "XD develop folder: $develop"
Write-Host "Installing bridge:   $destination"

if (Test-Path $destination) {
    Remove-Item -LiteralPath $destination -Recurse -Force
}
New-Item -ItemType Directory -Force -Path $destination | Out-Null

Copy-Item -LiteralPath (Join-Path $source 'main.js') -Destination $destination -Force
Copy-Item -LiteralPath (Join-Path $source 'manifest.json') -Destination $destination -Force

$manifestPath = Join-Path $destination 'manifest.json'
$manifest = Get-Content -LiteralPath $manifestPath -Raw | ConvertFrom-Json
if ($PluginId) {
    if ([string]::IsNullOrWhiteSpace($PluginId)) {
        throw 'PluginId cannot be blank.'
    }
    $manifest.id = $PluginId
    $manifest | ConvertTo-Json -Depth 20 | Set-Content -LiteralPath $manifestPath -Encoding UTF8
}

$installedManifest = Get-Content -LiteralPath $manifestPath -Raw | ConvertFrom-Json
if ($installedManifest.manifestVersion -ne 4) {
    throw "Unexpected XD manifestVersion: $($installedManifest.manifestVersion)"
}
if ($installedManifest.host.app -ne 'XD') {
    throw "Unexpected XD manifest host: $($installedManifest.host.app)"
}
if (-not (Test-Path (Join-Path $destination 'main.js'))) {
    throw 'XD bridge install verification failed: main.js missing.'
}

Write-Host "PASS: Adobe XD MCP bridge installed. Plugin ID=$($installedManifest.id)"
if (-not $NoReloadHint) {
    Write-Host 'In Adobe XD: Plugins > Development > Reload Plugins (Windows shortcut: Ctrl+Shift+R).'
    Write-Host 'Then open Plugins > MCP Adobe Bridge and keep the panel open for live MCP access.'
}
