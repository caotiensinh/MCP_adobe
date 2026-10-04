param(
    [string]$RunnerRoot = 'D:\actions-runner-adobe',
    [switch]$StopService
)

$ErrorActionPreference = 'Stop'

if (-not [Environment]::UserInteractive) {
    throw 'Run this script from the logged-in Windows desktop session, not from a GitHub Actions service job.'
}

$runCmd = Join-Path $RunnerRoot 'run.cmd'
if (-not (Test-Path $runCmd)) {
    throw "Runner run.cmd not found: $runCmd"
}

Write-Host "RunnerRoot=$RunnerRoot"
Write-Host "User=$([System.Security.Principal.WindowsIdentity]::GetCurrent().Name)"
Write-Host "Session=$env:SESSIONNAME"

$escapedRoot = [Regex]::Escape($RunnerRoot)
$services = @(Get-CimInstance Win32_Service | Where-Object {
    $_.Name -like 'actions.runner.*' -and $_.PathName -match $escapedRoot
})

if ($services.Count -gt 0) {
    foreach ($svc in $services) {
        Write-Host "RunnerService=$($svc.Name) State=$($svc.State) StartName=$($svc.StartName)"
    }

    if (-not $StopService) {
        throw 'The repository-scoped runner is still installed as a Windows service. Re-run this script from an elevated PowerShell with -StopService to stop/disable only that runner service before starting run.cmd interactively.'
    }

    foreach ($svc in $services) {
        $service = Get-Service -Name $svc.Name
        if ($service.Status -ne 'Stopped') {
            Stop-Service -Name $svc.Name -Force
            $service.WaitForStatus('Stopped', [TimeSpan]::FromSeconds(20))
        }
        Set-Service -Name $svc.Name -StartupType Disabled
        Write-Host "Disabled service $($svc.Name) to avoid two listeners using the same runner registration."
    }
}

$existingListener = @(Get-CimInstance Win32_Process -Filter "Name='Runner.Listener.exe'" | Where-Object {
    $_.ExecutablePath -and $_.ExecutablePath -match $escapedRoot
})
if ($existingListener.Count -gt 0) {
    throw "A Runner.Listener from $RunnerRoot is still running. Stop it before starting the interactive listener."
}

function Repair-InteractiveWorkspaceOwnership {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Root
    )

    $workRoot = Join-Path $Root '_work\MCP_adobe'
    if (-not (Test-Path -LiteralPath $workRoot)) {
        Write-Host "Workspace ownership repair skipped; path does not exist yet: $workRoot"
        return
    }

    $identity = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
    $icacls = Join-Path $env:SystemRoot 'System32\icacls.exe'
    if (-not (Test-Path -LiteralPath $icacls -PathType Leaf)) {
        throw "icacls.exe not found: $icacls"
    }

    Write-Host "Repairing interactive runner workspace ownership: $workRoot"
    Write-Host "Workspace owner/grantee=$identity"

    & $icacls $workRoot '/setowner' $identity '/T' '/C' '/Q'
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to transfer runner workspace ownership to $identity. icacls exit code=$LASTEXITCODE"
    }

    & $icacls $workRoot '/grant:r' "${identity}:(OI)(CI)F" '/T' '/C' '/Q'
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to grant runner workspace permissions to $identity. icacls exit code=$LASTEXITCODE"
    }

    $repoWorktree = Join-Path $workRoot 'MCP_adobe'
    if (Test-Path -LiteralPath $repoWorktree) {
        $git = Get-Command git -CommandType Application -ErrorAction SilentlyContinue | Select-Object -First 1
        if ($git) {
            & $git.Source config --global --add safe.directory ($repoWorktree -replace '\\', '/')
            if ($LASTEXITCODE -ne 0) {
                throw "Failed to add Git safe.directory for interactive workspace. git exit code=$LASTEXITCODE"
            }
            Write-Host "Git safe.directory added for interactive user: $repoWorktree"
        } else {
            Write-Warning 'git.exe is not currently available in PATH; ownership repair completed and checkout may still proceed if the runner toolchain supplies Git.'
        }
    }

    Write-Host 'PASS: interactive runner workspace ownership repaired.'
}

Repair-InteractiveWorkspaceOwnership -Root $RunnerRoot

Write-Host 'Starting GitHub Actions runner in the logged-in desktop session...'
Start-Process -FilePath 'cmd.exe' -ArgumentList '/k', "`"$runCmd`"" -WorkingDirectory $RunnerRoot
Write-Host 'Interactive runner console launched. Keep that window open while Adobe E2E jobs run.'
