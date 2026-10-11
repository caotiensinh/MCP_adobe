param()
$ErrorActionPreference='Stop'
if($env:COMPUTERNAME -ne 'MRCAO'){throw 'XD_NATIVE_RESTORE_WRONG_HOST'}
if([System.Diagnostics.Process]::GetCurrentProcess().SessionId -ne 1){throw 'XD_NATIVE_RESTORE_WRONG_SESSION'}
$source=Join-Path $env:USERPROFILE 'Documents\MCPAdobe\MCP_Mode1_Panda_XD_38136531800.xd'
$sha='598F79071CF7DBFC426F9FEF50144CF94225D2E7BB384C89E2E4FE1D67FDAD29'
if(-not (Test-Path -LiteralPath $source -PathType Leaf)){throw 'XD_NATIVE_RESTORE_SOURCE_MISSING'}
if((Get-FileHash -LiteralPath $source -Algorithm SHA256).Hash -ne $sha){throw 'XD_NATIVE_RESTORE_SOURCE_SHA_CHANGED'}
$xd=@(Get-Process -Name XD -ErrorAction SilentlyContinue | Where-Object {$_.SessionId -eq 1})
$pickers=@(Get-Process -Name PickerHost -ErrorAction SilentlyContinue | Where-Object {$_.SessionId -eq 1})
$connected=@(Get-NetTCPConnection -LocalPort 8765 -State Established -ErrorAction SilentlyContinue)
if($xd.Count -gt 0 -or $pickers.Count -gt 0 -or $connected.Count -gt 0){
  throw "XD_NATIVE_RESTORE_EXISTING_HOST_UNSAFE xd=$($xd.Count) picker=$($pickers.Count) bridge=$($connected.Count)"
}
Add-Type -AssemblyName UIAutomationClient
Add-Type -AssemblyName UIAutomationTypes
$root=[System.Windows.Automation.AutomationElement]::RootElement
$top=$root.FindAll([System.Windows.Automation.TreeScope]::Children,[System.Windows.Automation.Condition]::TrueCondition)
foreach($w in $top){
  if([string]$w.Current.Name -match 'Adobe XD|Save As'){
    throw "XD_NATIVE_RESTORE_WINDOW_EXISTS=$($w.Current.Name)"
  }
}
Write-Host "XD_NATIVE_RESTORE_GUARD=PASS sha256=$sha"
Start-Process -FilePath $source -ErrorAction Stop
Write-Host 'XD_NATIVE_RESTORE_OPEN_FILE_REQUESTED_ONCE=PASS'
$deadline=(Get-Date).AddSeconds(90)
$found=$null
while((Get-Date) -lt $deadline){
  Start-Sleep -Seconds 2
  $documents=@(Get-Process -ErrorAction SilentlyContinue | Where-Object {
    $_.SessionId -eq 1 -and $_.MainWindowHandle -ne 0 -and
    $_.MainWindowTitle -match '^MCP_Mode1_Panda_XD_38136531800.*Adobe XD$'
  })
  if($documents.Count -gt 1){throw 'XD_NATIVE_RESTORE_DUPLICATE_WINDOWS'}
  if($documents.Count -eq 1){$found=$documents[0];break}
}
if(-not $found){
  foreach($proc in @(Get-Process -Name XD -ErrorAction SilentlyContinue)){
    Write-Host "XD_NATIVE_RESTORE_PROCESS_DIAG pid=$($proc.Id) session=$($proc.SessionId) hwnd=$($proc.MainWindowHandle) title=$($proc.MainWindowTitle)"
  }
  throw 'XD_NATIVE_RESTORE_DOCUMENT_WINDOW_NOT_VISIBLE_NO_SECOND_LAUNCH'
}
Write-Host "XD_NATIVE_RESTORE_REAL_DOCUMENT=PASS pid=$($found.Id) title=$($found.MainWindowTitle)"
$established=@(Get-NetTCPConnection -State Established -LocalPort 8765 -ErrorAction SilentlyContinue)
if($established.Count -eq 0){
  Add-Type -AssemblyName System.Windows.Forms
  Add-Type @'
using System;
using System.Runtime.InteropServices;
public static class XdRestoredGui {
 [DllImport("user32.dll")] public static extern bool ShowWindow(IntPtr h,int state);
 [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr h);
 [DllImport("user32.dll")] public static extern IntPtr GetForegroundWindow();
 [DllImport("user32.dll")] public static extern uint GetWindowThreadProcessId(IntPtr h,out uint pid);
}
'@
  [void][XdRestoredGui]::ShowWindow($found.MainWindowHandle,9)
  [void][XdRestoredGui]::SetForegroundWindow($found.MainWindowHandle)
  Start-Sleep -Milliseconds 400
  function Foreground-Pid {
    $hwnd=[XdRestoredGui]::GetForegroundWindow()
    $pidValue=[uint32]0
    if($hwnd -ne [IntPtr]::Zero){[void][XdRestoredGui]::GetWindowThreadProcessId($hwnd,[ref]$pidValue)}
    return [int]$pidValue
  }
  if((Foreground-Pid) -ne $found.Id){
    $shell=New-Object -ComObject WScript.Shell
    [void]$shell.AppActivate([int]$found.Id)
    Start-Sleep -Milliseconds 500
  }
  if((Foreground-Pid) -ne $found.Id){throw 'XD_NATIVE_RESTORE_NOT_FOREGROUND_NO_CONNECT'}
  [System.Windows.Forms.SendKeys]::SendWait('^%+9')
  Write-Host 'XD_NATIVE_RESTORE_UXP_CONNECT_SHORTCUT_SENT_ONCE=PASS'
}
$deadline=(Get-Date).AddSeconds(30)
$ok=$false
while((Get-Date) -lt $deadline){
  Start-Sleep -Seconds 2
  if(@(Get-NetTCPConnection -LocalPort 8765 -State Established -ErrorAction SilentlyContinue).Count -gt 0){
    $ok=$true;break
  }
}
if(-not $ok){throw 'XD_NATIVE_RESTORE_BRIDGE_NOT_CONNECTED_STOP'}
Write-Host 'XD_NATIVE_RESTORE_REAL_UXP_TCP=PASS'
