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
    if (-not (Test-Path $packagesRoot)) {
        throw "Windows app Packages directory was not found: $packagesRoot"
    }

    $candidates = New-Object System.Collections.Generic.List[string]

    # Prefer the actual package family registered for the logged-in user. Current
    # XD releases can use Adobe.XD_<publisherId>; older releases used Adobe.CC.XD_*.
    $registeredXdPackages = @(
        Get-AppxPackage -ErrorAction SilentlyContinue |
            Where-Object { $_.Name -match 'Adobe.*XD|XD.*Adobe' }
    )
    foreach ($package in $registeredXdPackages) {
        if (-not [string]::IsNullOrWhiteSpace($package.PackageFamilyName)) {
            $candidates.Add(
                (Join-Path $packagesRoot "$($package.PackageFamilyName)\LocalState\develop")
            )
        }
    }

    # Also inspect existing package sandboxes so local/internal installs work even
    # when Get-AppxPackage metadata is unavailable to the current PowerShell host.
    foreach ($pattern in @('Adobe.XD_*', 'Adobe.CC.XD_*')) {
        Get-ChildItem -LiteralPath $packagesRoot -Directory -Filter $pattern -ErrorAction SilentlyContinue |
            ForEach-Object {
                $candidates.Add((Join-Path $_.FullName 'LocalState\develop'))
            }
    }

    # Keep the documented legacy package path as the last compatibility fallback.
    $candidates.Add(
        (Join-Path $packagesRoot 'Adobe.CC.XD_adky2gkssdxte\LocalState\develop')
    )

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
Open Adobe XD once so its LocalState sandbox is created, then rerun this script.
If needed, use: Plugins > Development > Show Develop Folder
and rerun with -DevelopFolder "<that folder>".
'@
}

$develop = Resolve-XdDevelopFolder -ExplicitPath $DevelopFolder
$destination = Join-Path $develop 'MCPAdobeBridge'

# Remove only stale MCP Adobe XD copies created by earlier loader experiments.
# Leaving these beside the develop plugin causes two XD bridge instances to
# race for ws://127.0.0.1:8765 (observed v3 -> v2 -> v3 within one live run).
if($env:APPDATA){
    $externalRoot=Join-Path $env:APPDATA 'Adobe\UXP\Plugins\External'
    foreach($staleId in @('MCPADB01','com.mcpadobe.xd.bridge')){
        $stalePath=Join-Path $externalRoot $staleId
        if(Test-Path -LiteralPath $stalePath){
            Remove-Item -LiteralPath $stalePath -Recurse -Force
            Write-Host "XD_STALE_EXTERNAL_REMOVED=PASS ID=$staleId PATH=$stalePath"
        }
    }
}

Write-Host "XD develop folder: $develop"
Write-Host "Installing bridge:   $destination"

if (Test-Path $destination) {
    Remove-Item -LiteralPath $destination -Recurse -Force
}
New-Item -ItemType Directory -Force -Path $destination | Out-Null

Copy-Item -LiteralPath (Join-Path $source 'main.js') -Destination $destination -Force
Copy-Item -LiteralPath (Join-Path $source 'manifest.json') -Destination $destination -Force
$debugSource=Join-Path $source 'debug.json'
if(Test-Path -LiteralPath $debugSource){
    Copy-Item -LiteralPath $debugSource -Destination $destination -Force
}

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
if ($installedManifest.host.app -ne 'XD') {
    throw "Unexpected XD manifest host: $($installedManifest.host.app)"
}
if($installedManifest.manifestVersion -ne 4){
    throw "XD manifestVersion must be 4, got $($installedManifest.manifestVersion)"
}
$entries=@($installedManifest.entrypoints)
if($entries.Count -lt 3){
    throw 'XD manifest is missing required v4 entrypoints.'
}
$connect=@($entries | Where-Object {$_.id -eq 'mcpAdobeConnect'}) | Select-Object -First 1
$apply=@($entries | Where-Object {$_.id -eq 'mcpAdobeApply'}) | Select-Object -First 1
$panel=@($entries | Where-Object {$_.id -eq 'mcpAdobeBridge'}) | Select-Object -First 1
if(-not $connect -or $connect.type -ne 'command'){ throw 'XD connect command entry point missing.' }
if(-not $apply -or $apply.type -ne 'command'){ throw 'XD apply command entry point missing.' }
if(-not $panel -or $panel.type -ne 'panel'){ throw 'XD bridge panel entry point missing.' }
if (-not (Test-Path (Join-Path $destination 'main.js'))) {
    throw 'XD bridge install verification failed: main.js missing.'
}

Write-Host "PASS: Adobe XD MCP bridge installed. Plugin ID=$($installedManifest.id)"
if (-not $NoReloadHint) {
    Write-Host 'In Adobe XD: Plugins > Development > Reload Plugins (Windows shortcut: Ctrl+Shift+R).'
    Write-Host 'Then open Plugins > MCP Adobe Bridge and keep the panel open for live MCP access.'
}
