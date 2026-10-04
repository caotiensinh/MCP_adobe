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
    param(
        [Parameter(Mandatory = $true)][string]$ProcessName,
        [Parameter(Mandatory = $true)][string]$ExeName,
        [Parameter(Mandatory = $true)][string[]]$Patterns
    )

    # Prefer the executable path of a live desktop process. This is the strongest
    # evidence that the logged-in user can actually see and run the application.
    $running = Get-Process -Name $ProcessName -ErrorAction SilentlyContinue |
        Where-Object { $_.Path -and (Test-Path -LiteralPath $_.Path -PathType Leaf) } |
        Select-Object -First 1
    if ($running) {
        Write-Host "$ProcessName discovery=running-process path=$($running.Path)"
        return $running.Path
    }

    $fixedDrives = @(Get-CimInstance Win32_LogicalDisk -Filter 'DriveType=3' | ForEach-Object { $_.DeviceID })
    foreach ($drive in $fixedDrives) {
        foreach ($pattern in $Patterns) {
            $expanded = $pattern.Replace('{DRIVE}', $drive)
            $hit = Get-ChildItem -Path $expanded -File -ErrorAction SilentlyContinue | Select-Object -First 1
            if ($hit) {
                Write-Host "$ProcessName discovery=standard-pattern path=$($hit.FullName)"
                return $hit.FullName
            }
        }
    }

    # Portable/custom Adobe installs often have no uninstall/App Paths entries,
    # but their Start Menu shortcuts still carry the authoritative executable target.
    try {
        $shell = New-Object -ComObject WScript.Shell
        $shortcutRoots = @(
            (Join-Path $env:ProgramData 'Microsoft\Windows\Start Menu\Programs'),
            (Join-Path $env:APPDATA 'Microsoft\Windows\Start Menu\Programs')
        )
        foreach ($root in $shortcutRoots) {
            if (-not (Test-Path -LiteralPath $root)) { continue }
            $shortcuts = Get-ChildItem -LiteralPath $root -Recurse -Filter '*.lnk' -File -ErrorAction SilentlyContinue |
                Where-Object { $_.Name -match [Regex]::Escape($ProcessName) }
            foreach ($shortcut in $shortcuts) {
                $target = $shell.CreateShortcut($shortcut.FullName).TargetPath
                if ($target -and (Split-Path -Leaf $target) -ieq $ExeName -and (Test-Path -LiteralPath $target -PathType Leaf)) {
                    Write-Host "$ProcessName discovery=start-menu-shortcut path=$target shortcut=$($shortcut.FullName)"
                    return $target
                }
            }
        }
    } catch {
        Write-Warning "$ProcessName Start Menu discovery failed: $($_.Exception.Message)"
    }

    return $null
}

function Start-XdPackageIfNeeded {
    param($Package)

    if (-not $Package) { return }
    $xdRunning = Get-Process -Name 'XD' -ErrorAction SilentlyContinue
    if ($xdRunning) {
        Write-Host 'Adobe XD is already running.'
        return
    }

    try {
        $manifest = Get-AppxPackageManifest -Package $Package.PackageFullName
        $app = @($manifest.Package.Applications.Application)[0]
        if (-not $app.Id) { throw 'Adobe XD AppX application ID is empty.' }
        $appUserModelId = "$($Package.PackageFamilyName)!$($app.Id)"
        Start-Process explorer.exe -ArgumentList "shell:AppsFolder\$appUserModelId"
        Write-Host "Adobe XD launch requested: $appUserModelId"

        if ($env:LOCALAPPDATA -and $Package.PackageFamilyName) {
            $localState = Join-Path $env:LOCALAPPDATA "Packages\$($Package.PackageFamilyName)\LocalState"
            $deadline = [DateTime]::UtcNow.AddSeconds(20)
            while (-not (Test-Path $localState) -and [DateTime]::UtcNow -lt $deadline) {
                Start-Sleep -Milliseconds 500
            }
            if (Test-Path $localState) {
                Write-Host "Adobe XD LocalState ready: $localState"
            } else {
                Write-Warning "Adobe XD launched but LocalState was not observed within 20 seconds: $localState"
            }
        }
    } catch {
        Write-Warning "Could not launch Adobe XD automatically: $($_.Exception.Message)"
    }
}

$photoshop = Find-AdobeExe -ProcessName 'Photoshop' -ExeName 'Photoshop.exe' -Patterns @(
    '{DRIVE}\Program Files\Adobe\Adobe Photoshop *\Photoshop.exe',
    '{DRIVE}\Adobe\Adobe Photoshop *\Photoshop.exe',
    '{DRIVE}\Adobe Photoshop *\Photoshop.exe'
)
$illustrator = Find-AdobeExe -ProcessName 'Illustrator' -ExeName 'Illustrator.exe' -Patterns @(
    '{DRIVE}\Program Files\Adobe\Adobe Illustrator *\Support Files\Contents\Windows\Illustrator.exe',
    '{DRIVE}\Adobe\Adobe Illustrator *\Support Files\Contents\Windows\Illustrator.exe',
    '{DRIVE}\Adobe Illustrator *\Support Files\Contents\Windows\Illustrator.exe'
)
$xdPackage = @(
    Get-AppxPackage -ErrorAction SilentlyContinue |
        Where-Object { $_.Name -match 'Adobe.*XD|XD.*Adobe' }
)[0]

Write-Host "Photoshop=$photoshop"
Write-Host "Illustrator=$illustrator"
if ($xdPackage) {
    Write-Host "AdobeXD=$($xdPackage.Name) $($xdPackage.Version) $($xdPackage.InstallLocation)"
    Write-Host "AdobeXDFamily=$($xdPackage.PackageFamilyName)"
} else {
    Write-Warning 'Adobe XD package is not visible to this logged-in account.'
}

if (-not $photoshop) { Write-Warning 'Photoshop.exe was not found by process, standard paths, or Start Menu shortcuts.' }
if (-not $illustrator) { Write-Warning 'Illustrator.exe was not found by process, standard paths, or Start Menu shortcuts.' }

if (-not $NoLaunchXd -and $xdPackage) {
    Start-XdPackageIfNeeded -Package $xdPackage
}

if (-not $SkipXdPlugin) {
    if (-not (Test-Path $installXd)) { throw "Missing helper: $installXd" }
    & $installXd
}

if (-not (Test-Path $startRunner)) { throw "Missing helper: $startRunner" }
& $startRunner -RunnerRoot $RunnerRoot -StopService

Write-Host ''
Write-Host 'PASS: preparation completed.'
Write-Host 'Keep the new GitHub runner console open.'
Write-Host 'In Adobe XD:'
Write-Host '  1. Open or create a test document.'
Write-Host '  2. If XD was already open, use Plugins > Development > Reload Plugins (Ctrl+Shift+R).'
Write-Host '  3. Open Plugins > MCP Adobe Bridge and keep the panel visible.'
Write-Host 'Then the live workflow can test Photoshop, Illustrator, and XD from the interactive desktop session.'
