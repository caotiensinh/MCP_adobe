param([string]$NativeRunId=$env:PANDA_XD_NATIVE_RUN_ID)
$ErrorActionPreference='Stop'
if($env:COMPUTERNAME -ne 'MRCAO'){throw 'XD_FRESH_GATEWAY_WRONG_HOST'}
if([System.Diagnostics.Process]::GetCurrentProcess().SessionId -ne 1){throw 'XD_FRESH_GATEWAY_NO_DESKTOP'}
if($NativeRunId -notmatch '^[0-9]{8,20}$'){throw 'XD_FRESH_GATEWAY_INVALID_NATIVE_RUN'}
$native=Join-Path $env:USERPROFILE "Documents\MCPAdobe\MCP_Mode1_Panda_XD_$NativeRunId.xd"
if(-not (Test-Path -LiteralPath $native -PathType Leaf)){throw 'XD_FRESH_NATIVE_DOCUMENT_NOT_SAVED_NO_GATEWAY_MUTATION'}
if((Get-Item -LiteralPath $native).Length -lt 1000){throw 'XD_FRESH_NATIVE_DOCUMENT_INVALID'}
Write-Host "XD_FRESH_PRESAVED_NATIVE_SOURCE=PASS path=$native"
$parent=Join-Path $env:LOCALAPPDATA 'MCPAdobe'
$installed=Join-Path $parent 'gateway'
$prior=Join-Path $parent 'gateway.previous'
if(Test-Path -LiteralPath $prior){
  $binary=Join-Path $prior 'venv\Scripts\mcp-adobe.exe'
  $metadata=Join-Path $prior 'install-metadata.json'
  if(-not (Test-Path -LiteralPath $binary) -or -not (Test-Path -LiteralPath $metadata)){
    throw 'XD_FRESH_EXISTING_BACKUP_INVALID_NO_TOUCH'
  }
  $info=Get-Content -LiteralPath $metadata -Raw | ConvertFrom-Json
  if($info.gateway_port -ne 8787 -or $info.xd_port -ne 8765){
    throw 'XD_FRESH_BACKUP_PORTS_INVALID'
  }
  foreach($proc in @(Get-CimInstance Win32_Process -ErrorAction SilentlyContinue)){
    if(([string]$proc.ExecutablePath).StartsWith($prior,[StringComparison]::OrdinalIgnoreCase)){
      throw "XD_FRESH_BACKUP_HAS_ACTIVE_PROCESS=$($proc.ProcessId)"
    }
    if(([string]$proc.CommandLine).IndexOf($binary,[StringComparison]::OrdinalIgnoreCase) -ge 0){
      throw "XD_FRESH_BACKUP_REFERENCED_BY_PROCESS=$($proc.ProcessId)"
    }
  }
  $archive=Join-Path $parent ("gateway.previous.archived_"+$env:GITHUB_RUN_ID)
  if(Test-Path -LiteralPath $archive){throw 'XD_FRESH_BACKUP_ARCHIVE_ALREADY_EXISTS'}
  Move-Item -LiteralPath $prior -Destination $archive -ErrorAction Stop
  if(-not (Test-Path -LiteralPath (Join-Path $archive 'install-metadata.json'))){throw 'XD_FRESH_ARCHIVE_INCOMPLETE'}
  Write-Host "XD_FRESH_OLD_BACKUP_PRESERVED=PASS path=$archive"
}
$env:Path=(@([Environment]::GetEnvironmentVariable('Path','Machine'),[Environment]::GetEnvironmentVariable('Path','User'),$env:Path)|Where-Object{$_}) -join ';'
foreach($port in @(8787,8765,8081)){
 foreach($listener in @(Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue)){
   $process=Get-CimInstance Win32_Process -Filter "ProcessId=$($listener.OwningProcess)" -ErrorAction SilentlyContinue
   $exe=[string]$process.ExecutablePath
   $command=[string]$process.CommandLine
   Write-Host "XD_FRESH_GATEWAY_LISTENER port=$port pid=$($listener.OwningProcess) exe=$exe cmd=$command"
   if($port -ne 8081 -and -not (
       $exe.StartsWith($installed,[StringComparison]::OrdinalIgnoreCase) -or
       $command.IndexOf((Join-Path $installed 'venv\Scripts\mcp-adobe.exe'),[StringComparison]::OrdinalIgnoreCase) -ge 0)){
       throw "XD_FRESH_FOREIGN_GATEWAY_LISTENER=$port"
   }
 }
}
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/install_local_host.ps1 -SkipStartupRegistration
if($LASTEXITCODE -ne 0){throw 'XD_FRESH_GATEWAY_INSTALL_FAILED_INSPECT_ROLLBACK'}
Write-Host 'XD_FRESH_GATEWAY_VERSIONED_INSTALL=PASS'
