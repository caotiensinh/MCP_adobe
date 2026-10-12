<#
.SYNOPSIS
  Recover MRCAO's GitHub Actions interactive runner without touching Adobe apps.
.DESCRIPTION
  Default mode diagnoses root, registration, service, listener, network and
  starts run.cmd ONLY if no existing listener or conflicting service exists.
  DiagnoseOnly makes no host changes. Never restarts Adobe, browsers, or MCP.
.EXAMPLE
  powershell -NoProfile -ExecutionPolicy Bypass -File .\recover_mrcao_runner_safe.ps1
.EXAMPLE
  powershell -NoProfile -ExecutionPolicy Bypass -File .\recover_mrcao_runner_safe.ps1 -DiagnoseOnly
#>
[CmdletBinding()]
param(
    [string]$RunnerRoot = 'D:\actions-runner-adobe',
    [switch]$DiagnoseOnly
)
$ErrorActionPreference='Stop'
Set-StrictMode -Version Latest

function Fail([string]$Message) {
    Write-Host "MRCAO_RUNNER_RECOVERY_BLOCKED=$Message"
    throw $Message
}
function Expect([bool]$Condition,[string]$ErrorCode) {
    if(-not $Condition){ Fail $ErrorCode }
}
function Get-RootListener([string]$Root) {
    $prefix=[IO.Path]::GetFullPath($Root).TrimEnd('\')+'\'
    return @(Get-CimInstance Win32_Process -Filter "Name='Runner.Listener.exe'" -ErrorAction Stop |
        Where-Object { $_.ExecutablePath -and $_.ExecutablePath.StartsWith($prefix,[StringComparison]::OrdinalIgnoreCase) })
}
function Get-RootService([string]$Root) {
    $marker=[regex]::Escape([IO.Path]::GetFullPath($Root).TrimEnd('\'))
    return @(Get-CimInstance Win32_Service -ErrorAction Stop |
        Where-Object { $_.Name -like 'actions.runner.*' -and $_.PathName -match $marker })
}
function Parse-RunnerRegistration([string]$Root) {
    $reg=Join-Path $Root '.runner'
    Expect (Test-Path -LiteralPath $reg -PathType Leaf) 'REGISTRATION_NOT_PRESENT'
    $data=Get-Content -LiteralPath $reg -Raw -Encoding UTF8 | ConvertFrom-Json
    Expect ($null -ne $data) 'REGISTRATION_NOT_JSON'
    Expect ($data.agentName -ceq 'windows') 'REGISTERED_AGENT_NOT_WINDOWS'
    $url=[string]$data.gitHubUrl
    if($url.EndsWith('/')){$url=$url.TrimEnd('/')}
    Expect ($url -ieq 'https://github.com/caotiensinh/MCP_adobe') 'REGISTERED_REPOSITORY_MISMATCH'
    Write-Host "MRCAO_RUNNER_REGISTRATION=PASS agent=windows repository=$url"
    return $data
}
function Test-RemoteConnectivity {
    foreach($domain in @('github.com','api.github.com')){
        $test=Test-NetConnection -ComputerName $domain -Port 443 -WarningAction SilentlyContinue
        Write-Host "MRCAO_RUNNER_TLS_CONNECT domain=$domain tcp=$($test.TcpTestSucceeded)"
        Expect ($test.TcpTestSucceeded -eq $true) ("NETWORK_UNREACHABLE_"+$domain)
    }
}
$report=[ordered]@{
    schema='mrcao-interactive-recovery/v1'
    observed_at_utc=[DateTime]::UtcNow.ToString('o')
    host=$env:COMPUTERNAME
    session=[Diagnostics.Process]::GetCurrentProcess().SessionId
    recovery_attempted=$false
    recovery_verified=$false
    result='started'
    runner_root=$RunnerRoot
}
try {
    Expect ($env:GITHUB_ACTIONS -ne 'true') 'CANNOT_RUN_INSIDE_GITHUB_ACTIONS'
    Expect ($env:COMPUTERNAME -eq 'MRCAO') 'WRONG_HOST'
    Expect ([Environment]::UserInteractive) 'NONINTERACTIVE_SESSION'
    Expect ([Diagnostics.Process]::GetCurrentProcess().SessionId -eq 1) 'NOT_ADOBE_SESSION_1'
    $root=[IO.Path]::GetFullPath($RunnerRoot)
    Expect (Test-Path -LiteralPath (Join-Path $root 'run.cmd') -PathType Leaf) 'RUN_CMD_MISSING'
    [void](Parse-RunnerRegistration $root)
    $diag=Join-Path $root '_diag'
    $recentLogs=@()
    if(Test-Path -LiteralPath $diag -PathType Container){
        $recentLogs=@(Get-ChildItem -LiteralPath $diag -Filter 'Runner_*.log' -File -ErrorAction SilentlyContinue |
            Sort-Object LastWriteTimeUtc -Descending | Select-Object -First 3)
    }
    foreach($logFile in $recentLogs){
        Write-Host "MRCAO_RUNNER_DIAG_FILE name=$($logFile.Name) utc=$($logFile.LastWriteTimeUtc.ToString('o')) bytes=$($logFile.Length)"
    }
    $report.last_log_utc=if($recentLogs.Count){$recentLogs[0].LastWriteTimeUtc.ToString('o')}else{$null}
    # Check connectivity even when a listener exists: an unassigned job can
    # result from a live-looking process with broken outbound GitHub traffic.
    Test-RemoteConnectivity
    $listeners=@(Get-RootListener $root)
    $services=@(Get-RootService $root)
    Write-Host "MRCAO_RUNNER_LOCAL_STATE listeners=$($listeners.Count) services=$($services.Count)"
    foreach($listener in $listeners){
        Write-Host "MRCAO_RUNNER_LISTENER pid=$($listener.ProcessId) session=$($listener.SessionId)"
    }
    foreach($service in $services){
        Write-Host "MRCAO_RUNNER_SERVICE name=$($service.Name) state=$($service.State) startMode=$($service.StartMode)"
    }
    $report.listener_count=$listeners.Count
    $report.service_count=$services.Count
    if($listeners.Count -gt 1) { Fail 'MULTIPLE_LISTENERS_NO_AUTOMATIC_MUTATION' }
    if($listeners.Count -eq 1) {
        $report.result='LISTENER_ALREADY_RUNNING'
        Write-Host 'MRCAO_RUNNER_EXISTING_LISTENER=PASS; do not launch a duplicate.'
        if($listeners[0].SessionId -ne 1) { Fail 'LISTENER_NOT_IN_ADOBE_SESSION_1' }
        return
    }
    if($services.Count -gt 0) {
        $report.result='SERVICE_PRESENT_REQUIRES_EXPLICIT_ADMIN_RECONCILIATION'
        if($DiagnoseOnly) {
            Write-Host 'MRCAO_RUNNER_DIAGNOSE_SERVICE_PRESENT=PASS; no service change or duplicate listener.'
            return
        }
        Fail 'RUNNER_SERVICE_PRESENT_NO_AUTOMATIC_STOP_OR_DUPLICATE_LISTENER'
    }
    if($DiagnoseOnly) {
        $report.result='READY_TO_START_NOT_EXECUTED'
        Write-Host 'MRCAO_RUNNER_DIAGNOSE_ONLY=PASS; no process started.'
        return
    }
    $report.recovery_attempted=$true
    # cmd /k keeps the console open so the authenticated interactive runner
    # survives the launcher and maintains Adobe Session 1.
    $cmd='set MCP_ADOBE_INTERACTIVE_RUNNER=1&& call "'+(Join-Path $root 'run.cmd')+'"'
    $launch=Start-Process -FilePath 'cmd.exe' -ArgumentList '/k',$cmd -WorkingDirectory $root -PassThru -ErrorAction Stop
    Write-Host "MRCAO_RUNNER_CONSOLE_LAUNCHED pid=$($launch.Id)"
    $end=(Get-Date).AddSeconds(25)
    $confirmed=@()
    do {
        Start-Sleep -Milliseconds 750
        $confirmed=@(Get-RootListener $root)
        if($confirmed.Count -gt 1) { Fail 'UNEXPECTED_DUPLICATE_LISTENERS_AFTER_LAUNCH' }
        if($confirmed.Count -eq 1) { break }
    }until((Get-Date) -ge $end)
    if($confirmed.Count -ne 1) { Fail 'LISTENER_NOT_DETECTED_AFTER_LAUNCH_NO_RETRY' }
    if($confirmed[0].SessionId -ne 1) { Fail 'NEW_LISTENER_WRONG_SESSION' }
    $report.recovery_verified=$true
    $report.result='LOCAL_LISTENER_RESTORED'
    Write-Host "MRCAO_RUNNER_LOCAL_LISTENER_RESTORED=PASS pid=$($confirmed[0].ProcessId) session=1"
    Write-Host 'MRCAO_RUNNER_GITHUB_ONLINE_NOT_YET_PROVEN; verify queued job assignment separately.'
}
catch {
    $report.result='BLOCKED'
    $report.error_type=$_.Exception.GetType().Name
    $report.error=([string]$_.Exception.Message).Substring(0,[Math]::Min(250,([string]$_.Exception.Message).Length))
    Write-Host "MRCAO_RUNNER_ERROR=$($report.error)"
    throw
}
finally {
    $dest=Join-Path $env:TEMP 'mrcao_adobe_runner_recovery.json'
    try {
        ([pscustomobject]$report | ConvertTo-Json -Depth 5) | Set-Content -LiteralPath $dest -Encoding UTF8
        Write-Host "MRCAO_RUNNER_REPORT=$dest"
    } catch {
        Write-Warning 'Unable to persist diagnostics, see console.'
    }
}
