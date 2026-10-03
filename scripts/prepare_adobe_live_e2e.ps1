param(
    [string]$RunnerRoot = 'D:\actions-runner-adobe',
    [switch]$SkipXdPlugin,
    [switch]$NoLaunchXd
)

$ErrorActionPreference = 'Stop'

function Test-Administrator {
    $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = New-Object Security.Principal.WindowsPrincipal($identity)
    return $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

if (-not [Environment]::UserInteractive) {
    throw 'Run this script from the logged-in MRCAO desktop session, not from a GitHub Actions service job.'
}
if (-not (Test-Administrator)) {
    throw 'Open Windows PowerShell with Run as administrator, then run this script again.'
}

$repoRoot = Split-Path -Parent $PSScriptRoot
$installXd = Join-Path $PSScriptRoot 'install_xd_plugin.ps1'
$startRunner = Join-Path $PSScriptRoot 'start_adobe_runner_interactive.ps1'

Write-Host '=== MCP_adobe live E2E preparation ==='
Write-Host "User=$([Security.Principal.WindowsIdentity]::GetCurrent().Name)"
Write-Host "Session=$env:SESSIONNAME"
Write-Host "RepoRoot=$repoRoot"
Write-Host "RunnerRoot=$RunnerRoot"

function Find-AdobeExe {
    param([string[]]$Patterns)
    $fixedDrives = @(Get-CimInstance Win32_LogicalDisk -Filter 'DriveType=3' | ForEach-Object { $_.DeviceID })
    foreach ($drive in $fixedDrives) {
        foreach ($pattern in $Patterns) {
            $expanded = $pattern.Replace('{DRIVE}', $drive)
            $hit = Get-ChildItem -Path $expanded -File -ErrorAction SilentlyContinue | Select-Object -First 1
            if ($hit) { return $hit.FullName }
        }
    }
    return $null
}

$photoshop = Find-AdobeExe @(
    '{DRIVE}\Program Files\Adobe\Adobe Photoshop *\Photoshop.exe',
    '{DRIVE}\Adobe\Adobe Photoshop *\Photoshop.exe',
    '{DRIVE}\Adobe Photoshop *\Photoshop.exe'
)
$illustrator = Find-AdobeExe @(
    '{DRIVE}\Program Files\Adobe\Adobe Illustrator *\Support Files\Contents\Windows\Illustrator.exe',
    '{DRIVE}\Adobe\Adobe Illustrator *\Support Files\Contents\Windows\Illustrator.exe',
    '{DRIVE}\Adobe Illustrator *\Support Files\Contents\Windows\Illustrator.exe'
)
$xdPackage = Get-AppxPackage -Name 'Adobe.XD' -ErrorAction SilentlyContinue | Select-Object -First 1

Write-Host "Photoshop=$photoshop"
Write-Host "Illustrator=$illustrator"
if ($xdPackage) {
    Write-Host "AdobeXD=$($xdPackage.Name) $($xdPackage.Version) $($xdPackage.InstallLocation)"
} else {
    Write-Warning 'Adobe XD package is not visible to this logged-in account.'
}

if (-not $photoshop) { Write-Warning 'Photoshop.exe was not found by standard Adobe path patterns.' }
if (-not $illustrator) { Write-Warning 'Illustrator.exe was not found by standard Adobe path patterns.' }

if (-not $SkipXdPlugin) {
    if (-not (Test-Path $installXd)) { throw "Missing helper: $installXd" }
    & $installXd
}

if (-not (Test-Path $startRunner)) { throw "Missing helper: $startRunner" }
& $startRunner -RunnerRoot $RunnerRoot -StopService

if (-not $NoLaunchXd -and $xdPackage) {
    $xdRunning = Get-Process -Name 'XD' -ErrorAction SilentlyContinue
    if (-not $xdRunning) {
        try {
            $manifest = Get-AppxPackageManifest -Package $xdPackage.PackageFullName
            $app = @($manifest.Package.Applications.Application)[0]
            if (-not $app.Id) { throw 'Adobe XD AppX application ID is empty.' }
            $appUserModelId = "$($xdPackage.PackageFamilyName)!$($app.Id)"
            Start-Process explorer.exe -ArgumentList "shell:AppsFolder\$appUserModelId"
            Write-Host "Adobe XD launch requested: $appUserModelId"
        } catch {
            Write-Warning "Could not launch Adobe XD automatically: $($_.Exception.Message)"
        }
    } else {
        Write-Host 'Adobe XD is already running.'
    }
}

Write-Host ''
Write-Host 'PASS: preparation completed.'
Write-Host 'Keep the new GitHub runner console open.'
Write-Host 'In Adobe XD:'
Write-Host '  1. Open or create a test document.'
Write-Host '  2. If XD was already open, use Plugins > Development > Reload Plugins (Ctrl+Shift+R).'
Write-Host '  3. Open Plugins > MCP Adobe Bridge and keep the panel visible.'
Write-Host 'Then the live workflow can test Photoshop, Illustrator, and XD from the interactive desktop session.'
