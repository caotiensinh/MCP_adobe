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
if(-not $xd){throw 'XD_BOOTSTRAP_REAL_APP_NOT_OPEN'}
Write-Host "XD_BOOTSTRAP_INITIAL_WINDOW=$($xd.MainWindowTitle) pid=$($xd.Id)"
if($xd.MainWindowTitle -ne 'Adobe XD'){
  throw 'XD_BOOTSTRAP_UNEXPECTED_EXISTING_DOCUMENT_REFUSE_NEW'
}
Focus-Xd $xd
$root=[System.Windows.Automation.AutomationElement]::FromHandle($xd.MainWindowHandle)
$cond=New-Object System.Windows.Automation.PropertyCondition(
  [System.Windows.Automation.AutomationElement]::AutomationIdProperty,'sidebar-work--create')
$button=$root.FindFirst([System.Windows.Automation.TreeScope]::Descendants,$cond)
if(-not $button){throw 'XD_BOOTSTRAP_HOME_CREATE_CONTROL_MISSING'}
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
# Adobe official XD "Save As Local Document" on Windows.
[System.Windows.Forms.SendKeys]::SendWait('^%+s')
Write-Host 'XD_BOOTSTRAP_SAVE_AS_LOCAL_COMMAND_SENT_ONCE'
$root=[System.Windows.Automation.AutomationElement]::RootElement
$dialog=$null
$deadline=(Get-Date).AddSeconds(30)
do{
  Start-Sleep -Milliseconds 600
  $windows=$root.FindAll([System.Windows.Automation.TreeScope]::Children,
                       [System.Windows.Automation.Condition]::TrueCondition)
  foreach($w in $windows){
    $t=[string]$w.Current.Name
    if($w.Current.ClassName -eq '#32770' -or $t -match 'Save As|Save.*Local'){
      $dialog=$w;break
    }
  }
}until($dialog -or (Get-Date)-gt $deadline)
if(-not $dialog){
  foreach($w in $windows){if($w.Current.Name){Write-Host "XD_BOOTSTRAP_TOP_WINDOW=$($w.Current.Name)"}}
  throw 'XD_BOOTSTRAP_SAVE_AS_LOCAL_DIALOG_MISSING_NO_REPLAY'
}
Write-Host "XD_BOOTSTRAP_NATIVE_SAVE_DIALOG=PASS title=$($dialog.Current.Name)"
$editCondition=New-Object System.Windows.Automation.PropertyCondition(
  [System.Windows.Automation.AutomationElement]::ControlTypeProperty,
  [System.Windows.Automation.ControlType]::Edit)
$edits=$dialog.FindAll([System.Windows.Automation.TreeScope]::Descendants,$editCondition)
$edit=$null
foreach($candidate in $edits){
  $name=[string]$candidate.Current.Name;$id=[string]$candidate.Current.AutomationId
  Write-Host "XD_BOOTSTRAP_EDIT name=$name id=$id"
  if($id -match '^1001$|FileName' -or $name -match 'File name'){$edit=$candidate;break}
}
if(-not $edit){throw 'XD_BOOTSTRAP_FILENAME_EDIT_NOT_FOUND'}
$pattern=$edit.GetCurrentPattern([System.Windows.Automation.ValuePattern]::Pattern)
$pattern.SetValue($target)
$buttonCondition=New-Object System.Windows.Automation.PropertyCondition(
  [System.Windows.Automation.AutomationElement]::ControlTypeProperty,
  [System.Windows.Automation.ControlType]::Button)
$buttons=$dialog.FindAll([System.Windows.Automation.TreeScope]::Descendants,$buttonCondition)
$saveButton=$null
foreach($b in $buttons){
  if(([string]$b.Current.Name) -match '^Save' -or ([string]$b.Current.AutomationId) -eq '1'){$saveButton=$b;break}
}
if(-not $saveButton){throw 'XD_BOOTSTRAP_SAVE_BUTTON_NOT_FOUND'}
$invoke=$saveButton.GetCurrentPattern([System.Windows.Automation.InvokePattern]::Pattern)
$invoke.Invoke()
Write-Host "XD_BOOTSTRAP_NATIVE_SAVE_CLICKED=PASS target=$target"
$deadline=(Get-Date).AddSeconds(35)
do{Start-Sleep -Milliseconds 600}until((Test-Path -LiteralPath $target) -or (Get-Date)-gt $deadline)
if(-not (Test-Path -LiteralPath $target)){throw 'XD_BOOTSTRAP_NATIVE_FILE_NOT_CREATED'}
$f=Get-Item -LiteralPath $target
if($f.Length -lt 1000){throw "XD_BOOTSTRAP_NATIVE_FILE_TOO_SMALL bytes=$($f.Length)"}
$sha=(Get-FileHash -LiteralPath $target -Algorithm SHA256).Hash
Write-Host "XD_BOOTSTRAP_BLANK_NATIVE_DOCUMENT_SAVED=PASS path=$target bytes=$($f.Length) sha256=$sha"
