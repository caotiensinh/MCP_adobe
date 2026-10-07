[CmdletBinding()]
param(
    [string]$PythonVersion = "3.12",
    [string]$UvCommandPath = "",
    [string]$InstallRoot = "",
    [string]$StartupEntry = "",
    [int]$GatewayPort = 8787,
    [int]$IllustratorPort = 8081,
    [int]$XdPort = 8765,
    [switch]$SkipStartupRegistration,
    [switch]$SkipStart
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
if ([string]::IsNullOrWhiteSpace($InstallRoot)) {
    $InstallRoot = Join-Path $env:LOCALAPPDATA "MCPAdobe\gateway"
}
if ([string]::IsNullOrWhiteSpace($StartupEntry)) {
    $StartupEntry = Join-Path $env:APPDATA "Microsoft\Windows\Start Menu\Programs\Startup\MCPAdobeLocalHost.cmd"
}
if ($GatewayPort -eq $IllustratorPort -or $GatewayPort -eq $XdPort -or $IllustratorPort -eq $XdPort) {
    throw "Gateway, Illustrator and XD ports must be distinct"
}

function Resolve-CommandPath([string]$Name) {
    $cmd = Get-Command $Name -ErrorAction SilentlyContinue
    if ($null -eq $cmd) { return $null }
    if ($cmd.Source) { return $cmd.Source }
    return $cmd.Path
}

function Get-Listener([int]$Port) {
    return @(Get-NetTCPConnection -State Listen -LocalPort $Port -ErrorAction SilentlyContinue)
}

function Stop-OwnedProcess([int]$ProcessId, [string]$Reason) {
    $process = Get-CimInstance Win32_Process -Filter "ProcessId=$ProcessId" -ErrorAction SilentlyContinue
    if ($null -eq $process) { return }
    $exe = [string]$process.ExecutablePath
    $cmd = [string]$process.CommandLine
    $ownedGateway = -not [string]::IsNullOrWhiteSpace($exe) -and $exe.StartsWith($InstallRoot, [StringComparison]::OrdinalIgnoreCase)
    $ownedIllustratorBackend = $cmd -match "illustrator_mcp\.server"
    if (-not $ownedGateway -and -not $ownedIllustratorBackend) {
        throw "Refusing to stop unrelated process on MCP Adobe port: PID=$ProcessId EXE=$exe CMD=$cmd"
    }
    Write-Host "local_host_stop PID=$ProcessId reason=$Reason exe=$exe"
    Stop-Process -Id $ProcessId -Force -ErrorAction Stop
}

function Stop-ExistingHost {
    $pidFile = Join-Path $InstallRoot "host-wrapper.pid"
    if (Test-Path -LiteralPath $pidFile) {
        $raw = (Get-Content -LiteralPath $pidFile -Raw -ErrorAction SilentlyContinue).Trim()
        $wrapperPid = 0
        if ([int]::TryParse($raw, [ref]$wrapperPid) -and $wrapperPid -gt 0) {
            $wrapper = Get-Process -Id $wrapperPid -ErrorAction SilentlyContinue
            if ($wrapper) {
                Write-Host "local_host_wrapper_stop PID=$wrapperPid"
                Stop-Process -Id $wrapperPid -Force -ErrorAction SilentlyContinue
            }
        }
    }

    foreach ($port in @($GatewayPort, $IllustratorPort, $XdPort)) {
        foreach ($listener in Get-Listener $port) {
            Stop-OwnedProcess $listener.OwningProcess "port-$port"
        }
    }

    $deadline = (Get-Date).AddSeconds(15)
    do {
        $busy = @()
        foreach ($port in @($GatewayPort, $IllustratorPort, $XdPort)) {
            if ((Get-Listener $port).Count -gt 0) { $busy += $port }
        }
        if ($busy.Count -eq 0) { return }
        Start-Sleep -Milliseconds 500
    } until ((Get-Date) -gt $deadline)
    throw "Existing MCP Adobe host did not release ports: $($busy -join ',')"
}

function Wait-ForPort([int]$Port, [int]$TimeoutSeconds = 90) {
    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    do {
        if ((Get-Listener $Port).Count -gt 0) { return }
        Start-Sleep -Milliseconds 500
    } until ((Get-Date) -gt $deadline)
    throw "Timed out waiting for MCP Adobe port $Port"
}

$uv = $UvCommandPath
if ([string]::IsNullOrWhiteSpace($uv)) { $uv = Resolve-CommandPath "uv" }
if ([string]::IsNullOrWhiteSpace($uv) -or -not (Test-Path -LiteralPath $uv)) {
    throw "uv.exe is required to install the persistent MCP Adobe host"
}

$installParent = Split-Path -Parent $InstallRoot
$backupRoot = "$InstallRoot.previous"
New-Item -ItemType Directory -Path $installParent -Force | Out-Null
if (Test-Path -LiteralPath $backupRoot) {
    throw "Previous persistent-host backup exists: $backupRoot"
}

$oldStartup = $null
if (Test-Path -LiteralPath $StartupEntry) {
    $oldStartup = Get-Content -LiteralPath $StartupEntry -Raw
}

Stop-ExistingHost

$hadPrevious = Test-Path -LiteralPath $InstallRoot
if ($hadPrevious) {
    Move-Item -LiteralPath $InstallRoot -Destination $backupRoot
}

try {
    New-Item -ItemType Directory -Path $InstallRoot -Force | Out-Null
    $venv = Join-Path $InstallRoot "venv"
    & $uv venv --python $PythonVersion $venv
    if ($LASTEXITCODE -ne 0) { throw "persistent host venv creation failed (exit $LASTEXITCODE)" }
    $python = Join-Path $venv "Scripts\python.exe"
    $gateway = Join-Path $venv "Scripts\mcp-adobe.exe"
    & $uv pip install --python $python $RepoRoot
    if ($LASTEXITCODE -ne 0) { throw "persistent host gateway install failed (exit $LASTEXITCODE)" }
    if (-not (Test-Path -LiteralPath $gateway)) { throw "mcp-adobe.exe missing after persistent host install" }
    & $gateway --help | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "persistent host CLI smoke failed" }

    $runner = Join-Path $InstallRoot "run-host.ps1"
    $runnerTemplate = @'
Set-StrictMode -Version Latest
$ErrorActionPreference = "Continue"
$gateway = Join-Path $PSScriptRoot "venv\Scripts\mcp-adobe.exe"
$logDir = Join-Path $PSScriptRoot "logs"
New-Item -ItemType Directory -Path $logDir -Force | Out-Null
$log = Join-Path $logDir "local-host.log"
Set-Content -LiteralPath (Join-Path $PSScriptRoot "host-wrapper.pid") -Value $PID -Encoding ASCII
try {
    while ($true) {
        Add-Content -LiteralPath $log -Value ("[{0}] host start" -f [DateTime]::Now.ToString("o"))
        & $gateway --transport streamable-http --host 127.0.0.1 --port __GATEWAY_PORT__ --path /mcp --prewarm illustrator --prewarm xd *>> $log
        $rc = $LASTEXITCODE
        Add-Content -LiteralPath $log -Value ("[{0}] host exited rc={1}; restart in 3s" -f [DateTime]::Now.ToString("o"), $rc)
        Start-Sleep -Seconds 3
    }
}
finally {
    Remove-Item -LiteralPath (Join-Path $PSScriptRoot "host-wrapper.pid") -Force -ErrorAction SilentlyContinue
}
'@
    $runnerContent = $runnerTemplate.Replace("__GATEWAY_PORT__", [string]$GatewayPort)
    Set-Content -LiteralPath $runner -Value $runnerContent -Encoding UTF8

    $metadata = [ordered]@{
        gateway_port = $GatewayPort
        illustrator_port = $IllustratorPort
        xd_port = $XdPort
        python_version = $PythonVersion
        repo_root = $RepoRoot
        installed_utc = [DateTime]::UtcNow.ToString("o")
    }
    $metadata | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath (Join-Path $InstallRoot "install-metadata.json") -Encoding UTF8

    if (-not $SkipStartupRegistration) {
        New-Item -ItemType Directory -Path (Split-Path -Parent $StartupEntry) -Force | Out-Null
        $startupContent = '@echo off' + [Environment]::NewLine +
            ('start "" /min powershell.exe -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File "' + $runner + '"') +
            [Environment]::NewLine
        Set-Content -LiteralPath $StartupEntry -Value $startupContent -Encoding ASCII
        Write-Host "local_host_startup=$StartupEntry"
    }

    if (-not $SkipStart) {
        $oldTracking = $env:RUNNER_TRACKING_ID
        try {
            Remove-Item Env:RUNNER_TRACKING_ID -ErrorAction SilentlyContinue
            $proc = Start-Process -FilePath "powershell.exe" -ArgumentList @(
                "-NoProfile",
                "-ExecutionPolicy", "Bypass",
                "-WindowStyle", "Hidden",
                "-File", $runner
            ) -WindowStyle Hidden -PassThru
            Write-Host "local_host_wrapper_pid=$($proc.Id)"
        }
        finally {
            if ($null -ne $oldTracking) { $env:RUNNER_TRACKING_ID = $oldTracking }
        }

        Wait-ForPort $GatewayPort
        Wait-ForPort $IllustratorPort
        Wait-ForPort $XdPort
        Write-Host "local_host_gateway_port=PASS:$GatewayPort"
        Write-Host "local_host_illustrator_port=PASS:$IllustratorPort"
        Write-Host "local_host_xd_port=PASS:$XdPort"
    }

    if ($hadPrevious -and (Test-Path -LiteralPath $backupRoot)) {
        Remove-Item -LiteralPath $backupRoot -Recurse -Force
    }
    Write-Host "local_host=PASS"
    Write-Host "local_host_url=http://127.0.0.1:$GatewayPort/mcp"
}
catch {
    Write-Host "local_host=FAIL"
    Write-Host "local_host_error=$($_.Exception.Message)"
    try { Stop-ExistingHost } catch { Write-Host "local_host_cleanup_warning=$($_.Exception.Message)" }
    if (Test-Path -LiteralPath $InstallRoot) {
        Remove-Item -LiteralPath $InstallRoot -Recurse -Force -ErrorAction SilentlyContinue
    }
    if ($hadPrevious -and (Test-Path -LiteralPath $backupRoot)) {
        Move-Item -LiteralPath $backupRoot -Destination $InstallRoot -Force -ErrorAction SilentlyContinue
    }
    if (-not $SkipStartupRegistration) {
        if ($null -ne $oldStartup) {
            Set-Content -LiteralPath $StartupEntry -Value $oldStartup -Encoding ASCII
        } else {
            Remove-Item -LiteralPath $StartupEntry -Force -ErrorAction SilentlyContinue
        }
    }
    throw
}
