param(
    [switch]$GitHubOutput
)

$ErrorActionPreference = 'Stop'

function Find-AdobeDesktopExe {
    param(
        [Parameter(Mandatory = $true)][string]$ProcessName,
        [Parameter(Mandatory = $true)][string]$ExeName,
        [Parameter(Mandatory = $true)][string[]]$Patterns
    )

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

$photoshop = Find-AdobeDesktopExe -ProcessName 'Photoshop' -ExeName 'Photoshop.exe' -Patterns @(
    '{DRIVE}\Program Files\Adobe\Adobe Photoshop *\Photoshop.exe',
    '{DRIVE}\Adobe\Adobe Photoshop *\Photoshop.exe',
    '{DRIVE}\Adobe Photoshop *\Photoshop.exe'
)
$illustrator = Find-AdobeDesktopExe -ProcessName 'Illustrator' -ExeName 'Illustrator.exe' -Patterns @(
    '{DRIVE}\Program Files\Adobe\Adobe Illustrator *\Support Files\Contents\Windows\Illustrator.exe',
    '{DRIVE}\Adobe\Adobe Illustrator *\Support Files\Contents\Windows\Illustrator.exe',
    '{DRIVE}\Adobe Illustrator *\Support Files\Contents\Windows\Illustrator.exe'
)
$xdCurrent = @(Get-AppxPackage -ErrorAction SilentlyContinue | Where-Object { $_.Name -match 'Adobe.*XD|XD.*Adobe' })
$xdAll = @()
try {
    $xdAll = @(Get-AppxPackage -AllUsers -ErrorAction Stop | Where-Object { $_.Name -match 'Adobe.*XD|XD.*Adobe' })
} catch {
    Write-Warning "Get-AppxPackage -AllUsers unavailable for this account: $($_.Exception.Message)"
}
$xdFound = ($xdCurrent.Count + $xdAll.Count) -gt 0

Write-Host "Photoshop=$photoshop"
Write-Host "Illustrator=$illustrator"
@($xdCurrent + $xdAll) | Sort-Object PackageFullName -Unique | ForEach-Object {
    Write-Host "AdobeXD=$($_.Name) $($_.Version) $($_.InstallLocation)"
}

if ($GitHubOutput) {
    if ([string]::IsNullOrWhiteSpace($env:GITHUB_OUTPUT)) {
        throw '-GitHubOutput requires GITHUB_OUTPUT.'
    }
    "photoshop=$photoshop" | Out-File -FilePath $env:GITHUB_OUTPUT -Append -Encoding utf8
    "illustrator=$illustrator" | Out-File -FilePath $env:GITHUB_OUTPUT -Append -Encoding utf8
    "photoshop_found=$(([bool]$photoshop).ToString().ToLowerInvariant())" | Out-File -FilePath $env:GITHUB_OUTPUT -Append -Encoding utf8
    "illustrator_found=$(([bool]$illustrator).ToString().ToLowerInvariant())" | Out-File -FilePath $env:GITHUB_OUTPUT -Append -Encoding utf8
    "xd_found=$($xdFound.ToString().ToLowerInvariant())" | Out-File -FilePath $env:GITHUB_OUTPUT -Append -Encoding utf8
}

[pscustomobject]@{
    Photoshop = $photoshop
    Illustrator = $illustrator
    XdFound = $xdFound
}
