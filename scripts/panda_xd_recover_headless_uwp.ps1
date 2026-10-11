param()
$ErrorActionPreference = 'Stop'
if($env:COMPUTERNAME -ne 'MRCAO'){throw 'XD_RECOVERY_WRONG_HOST'}
if([System.Diagnostics.Process]::GetCurrentProcess().SessionId -ne 1){throw 'XD_RECOVERY_WRONG_DESKTOP'}
Add-Type -AssemblyName UIAutomationClient
Add-Type -AssemblyName UIAutomationTypes
$root=[System.Windows.Automation.AutomationElement]::RootElement
function Inspect-Windows {
  $top=$root.FindAll([System.Windows.Automation.TreeScope]::Children,
      [System.Windows.Automation.Condition]::TrueCondition)
  $document=@();$dialogs=@();$home=@()
  foreach($w in $top){
    $name=[string]$w.Current.Name
    if($name -match 'Adobe XD|Save As'){
      Write-Host "XD_RECOVERY_WINDOW title=$name pid=$($w.Current.ProcessId)"
    }
    if($name -match '^Untitled.*Adobe XD$' -or $name -match '\.xd.*Adobe XD$'){$document+=,$w}
    if($name -eq 'Adobe XD'){$home+=,$w}
    if($name -match 'Save As'){$dialogs+=,$w}
    if($name -match 'Adobe XD'){
      $all=$w.FindAll([System.Windows.Automation.TreeScope]::Descendants,
        [System.Windows.Automation.Condition]::TrueCondition)
      foreach($item in $all){
        if([string]$item.Current.Name -eq 'Save As' -and
          [string]$item.Current.ControlType.ProgrammaticName -eq 'ControlType.Window'){
          $dialogs+=,$item
        }
      }
    }
  }
  return @{Document=$document.Count;Dialog=$dialogs.Count;Home=$home.Count}
}
$state=Inspect-Windows
$xd=@(Get-Process -Name XD -ErrorAction SilentlyContinue)
$picker=@(Get-Process -Name PickerHost -ErrorAction SilentlyContinue | Where-Object {$_.SessionId -eq 1})
$bridge=@(Get-NetTCPConnection -LocalPort 8765 -State Established -ErrorAction SilentlyContinue)
Write-Host "XD_RECOVERY_PREFLIGHT doc=$($state.Document) dialog=$($state.Dialog) home=$($state.Home) xd=$($xd.Count) picker=$($picker.Count) bridgeEstab=$($bridge.Count)"
if($state.Document -gt 0 -or $state.Dialog -gt 0 -or $picker.Count -gt 0 -or $bridge.Count -gt 0){
  throw 'XD_RECOVERY_UNSAVED_OR_CONNECTED_POTENTIAL_REFUSE_STOP'
}
if($state.Home -gt 0){
  Write-Host 'XD_RECOVERY_HOME_ALREADY_PRESENT_NO_PROCESS_TERMINATION'
  exit 0
}
if($xd.Count -gt 1){throw "XD_RECOVERY_MULTIPLE_XD_PROCESSES_REFUSE_KILL count=$($xd.Count)"}
if($xd.Count -eq 1){
  $proc=$xd[0]
  $cim=Get-CimInstance Win32_Process -Filter "ProcessId=$($proc.Id)" -ErrorAction Stop
  $exe=[string]$cim.ExecutablePath
  $cmd=[string]$cim.CommandLine
  $trusted=$exe.StartsWith('C:\Program Files\WindowsApps\Adobe.XD_', [StringComparison]::OrdinalIgnoreCase) -and
    $exe.EndsWith('\XD.exe',[StringComparison]::OrdinalIgnoreCase)
  Write-Host "XD_RECOVERY_BACKGROUND_PROCESS pid=$($proc.Id) hwnd=$($proc.MainWindowHandle) responding=$($proc.Responding) executable=$exe command=$cmd"
  if(-not $trusted -or $proc.SessionId -ne 1 -or $proc.MainWindowHandle -ne 0){
    throw 'XD_RECOVERY_PROCESS_OWNERSHIP_OR_HIDDEN_WINDOW_UNCERTAIN'
  }
  if($cmd -notmatch '-ServerName:App\.' -or $cmd -notmatch 'Adobe\.XD|Adobe_XD|App\.AppX'){
    throw 'XD_RECOVERY_NOT_THE_KNOWN_UWP_BACKGROUND_SERVER'
  }
  # The windowless XD app server has no document, picker, or live XD plugin.
  # Stop ONLY this verified orphan XD.exe. Do not affect ApplicationFrameHost,
  # Chrome, Gateway, other Adobe apps, plugins, or user document directories.
  Stop-Process -Id $proc.Id -ErrorAction Stop
  $deadline=(Get-Date).AddSeconds(16)
  while((Get-Process -Id $proc.Id -ErrorAction SilentlyContinue) -and (Get-Date) -lt $deadline){
    Start-Sleep -Milliseconds 500
  }
  if(Get-Process -Id $proc.Id -ErrorAction SilentlyContinue){
    throw 'XD_RECOVERY_ORPHAN_PROCESS_DID_NOT_EXIT_STOP'
  }
  Write-Host "XD_RECOVERY_ORPHAN_ONLY_STOPPED=PASS pid=$($proc.Id)"
}
$app=Get-StartApps -ErrorAction SilentlyContinue |
  Where-Object {$_.Name -eq 'Adobe XD'} | Select-Object -First 1
if(-not $app -or [string]::IsNullOrWhiteSpace([string]$app.AppID)){
  throw 'XD_RECOVERY_APPX_REGISTRATION_ABSENT'
}
Write-Host "XD_RECOVERY_START_APP_ONCE appid=$($app.AppID)"
Start-Process explorer.exe ("shell:AppsFolder\" + $app.AppID)
$deadline=(Get-Date).AddSeconds(85)
$homeFound=$false
while((Get-Date) -lt $deadline){
  Start-Sleep -Seconds 2
  $observed=Inspect-Windows
  if($observed.Home -ge 1 -and $observed.Document -eq 0 -and $observed.Dialog -eq 0){
    $homeFound=$true
    break
  }
  if($observed.Document -gt 0 -or $observed.Dialog -gt 0){
    throw 'XD_RECOVERY_UNEXPECTED_DOCUMENT_OR_DIALOG_DO_NOT_CREATE_NEW'
  }
}
if(-not $homeFound){throw 'XD_RECOVERY_HOME_NOT_OBSERVED_AFTER_CLEAN_UWP_ACTIVATION'}
Write-Host 'XD_RECOVERY_HOME_WINDOW=PASS'
