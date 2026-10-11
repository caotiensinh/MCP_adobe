param([string]$RunId=$env:GITHUB_RUN_ID)
$ErrorActionPreference='Stop'
if($env:COMPUTERNAME -ne 'MRCAO'){throw 'XD_BOOTSTRAP_WRONG_MACHINE'}
if([System.Diagnostics.Process]::GetCurrentProcess().SessionId -ne 1){throw 'XD_BOOTSTRAP_NOT_INTERACTIVE'}
if($RunId -notmatch '^[0-9]{8,20}$'){throw 'XD_BOOTSTRAP_INVALID_RUN_ID'}
$dir=Join-Path $env:USERPROFILE 'Documents\MCPAdobe'
New-Item -ItemType Directory -Path $dir -Force | Out-Null
$target=Join-Path $dir "MCP_Mode1_Panda_XD_$RunId.xd"
if(Test-Path -LiteralPath $target){throw 'XD_BOOTSTRAP_TARGET_EXISTS_NO_OVERWRITE'}
Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName UIAutomationClient
Add-Type -AssemblyName UIAutomationTypes
Add-Type @'
using System;
using System.Runtime.InteropServices;
public static class XdBootstrapNative {
  [DllImport("user32.dll")] public static extern bool ShowWindow(IntPtr h,int n);
  [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr h);
  [DllImport("user32.dll")] public static extern IntPtr GetForegroundWindow();
  [DllImport("user32.dll")] public static extern uint GetWindowThreadProcessId(IntPtr h,out uint pid);
}
'@
function Find-XdWindow {
  @(Get-Process -ErrorAction SilentlyContinue | Where-Object {
    ($_.ProcessName -match '^(XD|AdobeXD)$' -or $_.MainWindowTitle -match 'Adobe XD') -and
    $_.MainWindowHandle -ne 0 -and $_.SessionId -eq 1
  } | Select-Object -First 1)[0]
}
function Foreground-Pid {
  $owner=[uint32]0;$h=[XdBootstrapNative]::GetForegroundWindow()
  if($h -ne [IntPtr]::Zero){[void][XdBootstrapNative]::GetWindowThreadProcessId($h,[ref]$owner)}
  return [int]$owner
}
function Focus-Xd($xd){
  [void][XdBootstrapNative]::ShowWindow($xd.MainWindowHandle,9)
  [void][XdBootstrapNative]::SetForegroundWindow($xd.MainWindowHandle)
  Start-Sleep -Milliseconds 350
  if((Foreground-Pid) -ne $xd.Id){
    $sh=New-Object -ComObject WScript.Shell
    [void]$sh.AppActivate([int]$xd.Id)
    Start-Sleep -Milliseconds 550
  }
  if((Foreground-Pid) -ne $xd.Id){throw 'XD_BOOTSTRAP_FOREGROUND_PID_NOT_VERIFIED'}
}
$xd=Find-XdWindow
if(-not $xd){
  $xdProcesses=@(Get-Process -Name XD -ErrorAction SilentlyContinue)
  if($xdProcesses.Count -gt 0){throw 'XD_BOOTSTRAP_EXISTING_XD_PROCESS_WITHOUT_DOCUMENT_REFUSE_RELAUNCH'}
  $app=Get-StartApps -ErrorAction SilentlyContinue | Where-Object {$_.Name -eq 'Adobe XD'} | Select-Object -First 1
  if(-not $app){throw 'XD_BOOTSTRAP_ADOBE_XD_NOT_REGISTERED'}
  Write-Host "XD_BOOTSTRAP_START_REAL_ADOBE_XD_ONCE appid=$($app.AppID)"
  Start-Process explorer.exe ("shell:AppsFolder\"+$app.AppID)
  $deadline=(Get-Date).AddSeconds(80)
  while((Get-Date) -lt $deadline){
    Start-Sleep -Seconds 2
    $xd=Find-XdWindow
    if($xd){break}
  }
  if(-not $xd){throw 'XD_BOOTSTRAP_APP_FAILED_TO_OPEN'}
}
Write-Host "XD_BOOTSTRAP_INITIAL_WINDOW=$($xd.MainWindowTitle) pid=$($xd.Id)"
if($xd.MainWindowTitle -ne 'Adobe XD'){
  throw 'XD_BOOTSTRAP_UNEXPECTED_EXISTING_DOCUMENT_REFUSE_NEW'
}
Focus-Xd $xd
$root=[System.Windows.Automation.AutomationElement]::FromHandle($xd.MainWindowHandle)
$cond=New-Object System.Windows.Automation.PropertyCondition(
  [System.Windows.Automation.AutomationElement]::AutomationIdProperty,'sidebar-work--create')
$button=$null
$deadline=(Get-Date).AddSeconds(55)
while((Get-Date) -lt $deadline){
  $xd=Find-XdWindow
  if(-not $xd -or $xd.MainWindowTitle -ne 'Adobe XD'){
    throw 'XD_BOOTSTRAP_HOME_WINDOW_CHANGED_BEFORE_CREATE'
  }
  $root=[System.Windows.Automation.AutomationElement]::FromHandle($xd.MainWindowHandle)
  $button=$root.FindFirst([System.Windows.Automation.TreeScope]::Descendants,$cond)
  if($button){break}
  Start-Sleep -Milliseconds 1200
}
if(-not $button){
  $all=$root.FindAll([System.Windows.Automation.TreeScope]::Descendants,
                     [System.Windows.Automation.Condition]::TrueCondition)
  for($i=0;$i -lt [Math]::Min(100,$all.Count);$i++){
    $e=$all.Item($i)
    $name=[string]$e.Current.Name;$id=[string]$e.Current.AutomationId
    if($name -or $id){Write-Host "XD_BOOTSTRAP_HOME_UI name=$name id=$id"}
  }
  throw 'XD_BOOTSTRAP_HOME_CREATE_CONTROL_MISSING_AFTER_55S'
}
Write-Host 'XD_BOOTSTRAP_HOME_CREATE_CONTROL_READBACK=PASS'
try{
  $invoke=$button.GetCurrentPattern([System.Windows.Automation.InvokePattern]::Pattern)
  $invoke.Invoke()
}catch{
  $legacy=$button.GetCurrentPattern([System.Windows.Automation.LegacyIAccessiblePattern]::Pattern)
  $legacy.DoDefaultAction()
}
Write-Host 'XD_BOOTSTRAP_CREATE_DOCUMENT_REQUESTED=PASS'
$deadline=(Get-Date).AddSeconds(45)
do{
  Start-Sleep -Seconds 2
  $xd=Find-XdWindow
}until(($xd -and $xd.MainWindowTitle -match '^Untitled.*Adobe XD$') -or (Get-Date)-gt $deadline)
if(-not $xd -or $xd.MainWindowTitle -notmatch '^Untitled.*Adobe XD$'){throw 'XD_BOOTSTRAP_NEW_DOCUMENT_NOT_VERIFIED'}
Write-Host "XD_BOOTSTRAP_NEW_DOCUMENT=PASS title=$($xd.MainWindowTitle)"
Focus-Xd $xd
$xdRoot=[System.Windows.Automation.AutomationElement]::FromHandle($xd.MainWindowHandle)
$fileCond=New-Object System.Windows.Automation.PropertyCondition(
  [System.Windows.Automation.AutomationElement]::AutomationIdProperty,'AppMenu_File')
$fileMenu=$xdRoot.FindFirst([System.Windows.Automation.TreeScope]::Descendants,$fileCond)
if(-not $fileMenu){throw 'XD_STAGED_FILE_MENU_MISSING'}
$fileMenu.GetCurrentPattern([System.Windows.Automation.ExpandCollapsePattern]::Pattern).Expand()
Write-Host 'XD_STAGED_FILE_MENU_EXPANDED=PASS'
Start-Sleep -Milliseconds 500
$saveAsCond=New-Object System.Windows.Automation.PropertyCondition(
  [System.Windows.Automation.AutomationElement]::AutomationIdProperty,'AppMenu_SaveAs')
$saveAs=$xdRoot.FindFirst([System.Windows.Automation.TreeScope]::Descendants,$saveAsCond)
if(-not $saveAs -or $saveAs.Current.Name -ne 'Save As...'){
  throw 'XD_STAGED_SAVE_AS_ENTRY_NOT_VERIFIED'
}
$saveAs.GetCurrentPattern([System.Windows.Automation.InvokePattern]::Pattern).Invoke()
Write-Host 'XD_STAGED_SAVE_AS_MENU_CLICKED_ONCE'
$deadline=(Get-Date).AddSeconds(35)
$dialog=$null
while((Get-Date) -lt $deadline){
  Start-Sleep -Milliseconds 600
  $elements=$xdRoot.FindAll([System.Windows.Automation.TreeScope]::Descendants,
                            [System.Windows.Automation.Condition]::TrueCondition)
  foreach($element in $elements){
    if([string]$element.Current.Name -eq 'Save As' -and
       [string]$element.Current.ControlType.ProgrammaticName -eq 'ControlType.Window'){
      $dialog=$element;break
    }
  }
  if($dialog){break}
}
if(-not $dialog){throw 'XD_STAGED_NATIVE_PICKER_DID_NOT_OPEN'}
$controls=$dialog.FindAll([System.Windows.Automation.TreeScope]::Descendants,
                           [System.Windows.Automation.Condition]::TrueCondition)
$hostCount=0;$saveCount=0
foreach($control in $controls){
  if($control.Current.AutomationId -eq 'FileNameControlHost'){$hostCount++}
  if($control.Current.AutomationId -eq '1' -and $control.Current.Name -eq 'Save'){$saveCount++}
}
if($hostCount -ne 1 -or $saveCount -ne 1){throw 'XD_STAGED_PICKER_CONTROLS_NOT_UNIQUE'}
Write-Host "XD_STAGED_SAVE_DIALOG_READY=PASS run=$RunId appPid=$($xd.Id) pickerHwnd=$($dialog.Current.NativeWindowHandle) filenameHosts=$hostCount buttons=$saveCount"
Write-Host 'XD_STAGED_NATIVE_FILE=NOT_YET_SAVED'
