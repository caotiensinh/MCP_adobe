param([string]$RunId = "38132321143")
$ErrorActionPreference = 'Stop'
if($env:COMPUTERNAME -ne 'MRCAO'){throw 'XD_NATIVE_SAVE_WRONG_HOST'}
if([System.Diagnostics.Process]::GetCurrentProcess().SessionId -ne 1){throw 'XD_NATIVE_SAVE_WRONG_SESSION'}
if($RunId -notmatch '^[0-9]{8,20}$'){throw 'XD_NATIVE_SAVE_BAD_RUN_ID'}
$root = Join-Path $env:USERPROFILE 'Documents\MCPAdobe'
$target = Join-Path $root ("MCP_Mode1_Panda_XD_" + $RunId + ".xd")
if(-not (Test-Path -LiteralPath $root -PathType Container)){throw 'XD_NATIVE_SAVE_DESTINATION_DIR_NOT_PRESENT'}
if(Test-Path -LiteralPath $target){throw 'XD_NATIVE_SAVE_TARGET_EXISTS_NO_OVERWRITE'}
Add-Type -AssemblyName UIAutomationClient
Add-Type -AssemblyName UIAutomationTypes
Add-Type @'
using System;
using System.Text;
using System.Runtime.InteropServices;
public static class PandaXdNative {
  [DllImport("user32.dll",SetLastError=true)] public static extern bool IsWindow(IntPtr hwnd);
  [DllImport("user32.dll")] public static extern uint GetWindowThreadProcessId(IntPtr hwnd,out uint pid);
  [DllImport("user32.dll",CharSet=CharSet.Unicode)] public static extern int GetClassName(IntPtr hwnd,StringBuilder buffer,int capacity);
  [DllImport("user32.dll",CharSet=CharSet.Unicode)] public static extern int GetWindowText(IntPtr hwnd,StringBuilder buffer,int capacity);
  [DllImport("user32.dll")] public static extern IntPtr GetWindow(IntPtr hwnd,uint operation);
  [DllImport("user32.dll",CharSet=CharSet.Unicode)] public static extern IntPtr SendMessage(IntPtr hwnd,uint message,IntPtr wparam,string value);
  [DllImport("user32.dll")] public static extern IntPtr SendMessage(IntPtr hwnd,uint message,IntPtr wparam,IntPtr lparam);
  [DllImport("user32.dll")] public static extern IntPtr GetForegroundWindow();
  [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr hwnd);
  [DllImport("user32.dll")] public static extern bool SetCursorPos(int x,int y);
  [DllImport("user32.dll")] public static extern void mouse_event(uint flags,uint dx,uint dy,uint data,UIntPtr extra);
}
'@
function NativeText([IntPtr]$hwnd){
  $buf=New-Object System.Text.StringBuilder 2048
  [void][PandaXdNative]::GetWindowText($hwnd,$buf,2048)
  return $buf.ToString()
}
function NativeClass([IntPtr]$hwnd){
  $buf=New-Object System.Text.StringBuilder 128
  [void][PandaXdNative]::GetClassName($hwnd,$buf,128)
  return $buf.ToString()
}
function VerifyHandle([IntPtr]$hwnd,[int]$expectedPid,[string]$label){
  if($hwnd -eq [IntPtr]::Zero -or -not [PandaXdNative]::IsWindow($hwnd)){
    throw ("XD_NATIVE_SAVE_MISSING_HANDLE_" + $label)
  }
  $owner=[uint32]0
  [void][PandaXdNative]::GetWindowThreadProcessId($hwnd,[ref]$owner)
  if([int]$owner -ne $expectedPid){
    throw ("XD_NATIVE_SAVE_FOREIGN_HANDLE_" + $label + "_pid_" + $owner)
  }
  Write-Host "XD_NATIVE_HANDLE_VERIFIED label=$label hwnd=$hwnd class=$(NativeClass $hwnd) text=$(NativeText $hwnd)"
}
# Search real UI Automation desktop hierarchy, not a possibly stale process MainWindowTitle.
$desktop=[System.Windows.Automation.AutomationElement]::RootElement
$top=$desktop.FindAll([System.Windows.Automation.TreeScope]::Children,[System.Windows.Automation.Condition]::TrueCondition)
$xdWindows=@()
foreach($window in $top){
  $title=[string]$window.Current.Name
  if($title -match '^Untitled.*Adobe XD$' -and [string]$window.Current.ClassName -eq 'ApplicationFrameWindow'){
    $xdWindows+=,$window
  }
}
if($xdWindows.Count -ne 1){throw "XD_NATIVE_SAVE_DOCUMENT_WINDOW_COUNT=$($xdWindows.Count)"}
$xdWindow=$xdWindows[0]
$xdPid=[int]$xdWindow.Current.ProcessId
if($xdPid -le 0){throw 'XD_NATIVE_SAVE_PID_UNKNOWN'}
$inside=$xdWindow.FindAll([System.Windows.Automation.TreeScope]::Descendants,
                           [System.Windows.Automation.Condition]::TrueCondition)
$dialogs=@()
foreach($e in $inside){
  if([string]$e.Current.Name -eq 'Save As' -and
     [string]$e.Current.ControlType.ProgrammaticName -eq 'ControlType.Window'){
    $dialogs+=,$e
  }
}
if($dialogs.Count -ne 1){throw "XD_NATIVE_SAVE_OPEN_DIALOG_COUNT=$($dialogs.Count)"}
$dialog=$dialogs[0]
$children=$dialog.FindAll([System.Windows.Automation.TreeScope]::Descendants,
                           [System.Windows.Automation.Condition]::TrueCondition)
$fields=@();$buttons=@()
foreach($e in $children){
  $id=[string]$e.Current.AutomationId
  $name=[string]$e.Current.Name
  if($id -eq '1001' -and $name -eq 'Untitled-1.xd'){$fields+=,$e}
  if($id -eq '1' -and $name -eq 'Save'){$buttons+=,$e}
}
if($fields.Count -ne 1 -or $buttons.Count -ne 1){
  throw "XD_NATIVE_SAVE_FIELD_OR_BUTTON_NOT_UNIQUE field=$($fields.Count) button=$($buttons.Count)"
}
$field=$fields[0];$button=$buttons[0]
$dialogHwnd=[IntPtr]$dialog.Current.NativeWindowHandle
$editHwnd=[IntPtr]$field.Current.NativeWindowHandle
$buttonHwnd=[IntPtr]$button.Current.NativeWindowHandle
VerifyHandle $dialogHwnd $xdPid 'dialog'
VerifyHandle $editHwnd $xdPid 'filename'
VerifyHandle $buttonHwnd $xdPid 'save'
Write-Host "XD_NATIVE_SAVE_GATE=PASS document=$($xdWindow.Current.Name) pid=$xdPid"
# Descend ONLY from the verified filename control. Never target search box,
# location bar, Chrome or another application.
$pending=New-Object System.Collections.Queue
$pending.Enqueue($editHwnd)
$visited=New-Object 'System.Collections.Generic.HashSet[Int64]'
$edits=@();$allHandles=@()
while($pending.Count -gt 0 -and $visited.Count -lt 70){
  $h=[IntPtr]$pending.Dequeue()
  if($h -eq [IntPtr]::Zero -or -not $visited.Add($h.ToInt64())){continue}
  $class=NativeClass $h
  $current=NativeText $h
  $allHandles+=,[pscustomobject]@{Handle=$h;Class=$class;Text=$current}
  Write-Host "XD_NATIVE_FILENAME_CHILD hwnd=$h class=$class text=$current"
  if($class -match '^Edit$|^RichEdit'){$edits+=,$h}
  $child=[PandaXdNative]::GetWindow($h,[uint32]5)
  while($child -ne [IntPtr]::Zero){
    $pending.Enqueue($child)
    $child=[PandaXdNative]::GetWindow($child,[uint32]2)
  }
}
$candidates=@()
if($edits.Count -eq 1){$candidates+=,$edits[0]}
elseif($edits.Count -gt 1){throw 'XD_NATIVE_SAVE_MULTIPLE_EDIT_HANDLES_REFUSE_INPUT'}
else{
  foreach($h in $allHandles){
    if($h.Handle -eq $editHwnd -and $h.Class -match '^ComboBox$|^ComboBoxEx32$|^Edit$'){
      $candidates+=,$editHwnd
    }
  }
}
if($candidates.Count -ne 1){throw 'XD_NATIVE_SAVE_NO_EDITABLE_NATIVE_HANDLE_NO_INPUT'}
$actualEdit=[IntPtr]$candidates[0]
VerifyHandle $actualEdit $xdPid 'native_edit'
Write-Host "XD_NATIVE_SAVE_MUTATION_START=ONCE path=$target"
$response=[PandaXdNative]::SendMessage($actualEdit,[uint32]12,[IntPtr]::Zero,$target)
Start-Sleep -Milliseconds 300
$readback=NativeText $actualEdit
Write-Host "XD_NATIVE_SAVE_TEXT_READBACK result=$response value=$readback"
if($readback -ne $target){
  throw 'XD_NATIVE_SAVE_TEXT_NOT_CONFIRMED_STOP_BEFORE_SAVE_CLICK'
}
# Only when exact input text was read from the live native control.
$buttonClass=NativeClass $buttonHwnd
if($buttonClass -eq 'Button'){
  [void][PandaXdNative]::SendMessage($buttonHwnd,[uint32]245,[IntPtr]::Zero,[IntPtr]::Zero)
  Write-Host 'XD_NATIVE_SAVE_CLICK=BM_CLICK_ONCE'
}else{
  $foreground=[PandaXdNative]::GetForegroundWindow()
  $owner=[uint32]0
  if($foreground -ne [IntPtr]::Zero){[void][PandaXdNative]::GetWindowThreadProcessId($foreground,[ref]$owner)}
  if([int]$owner -ne $xdPid){
    [void][PandaXdNative]::SetForegroundWindow([IntPtr]$xdWindow.Current.NativeWindowHandle)
    Start-Sleep -Milliseconds 300
    $foreground=[PandaXdNative]::GetForegroundWindow()
    $owner=[uint32]0
    if($foreground -ne [IntPtr]::Zero){[void][PandaXdNative]::GetWindowThreadProcessId($foreground,[ref]$owner)}
  }
  if([int]$owner -ne $xdPid){throw 'XD_NATIVE_SAVE_CANNOT_PROVE_DIALOG_FOREGROUND_NO_CLICK'}
  $rect=$button.Current.BoundingRectangle
  $drect=$dialog.Current.BoundingRectangle
  $cx=[int][Math]::Floor($rect.Left+$rect.Width/2)
  $cy=[int][Math]::Floor($rect.Top+$rect.Height/2)
  if($rect.Width -lt 20 -or $rect.Height -lt 15 -or
     $cx -lt $drect.Left -or $cx -gt $drect.Right -or
     $cy -lt $drect.Top -or $cy -gt $drect.Bottom){
    throw 'XD_NATIVE_SAVE_BUTTON_BOUNDS_NOT_WITHIN_DIALOG'
  }
  if(-not [PandaXdNative]::SetCursorPos($cx,$cy)){throw 'XD_NATIVE_SAVE_CURSOR_FAILED'}
  [PandaXdNative]::mouse_event([uint32]2,[uint32]0,[uint32]0,[uint32]0,[UIntPtr]::Zero)
  [PandaXdNative]::mouse_event([uint32]4,[uint32]0,[uint32]0,[uint32]0,[UIntPtr]::Zero)
  Write-Host "XD_NATIVE_SAVE_CLICK=EXACT_BUTTON_ONCE x=$cx y=$cy"
}
$deadline=(Get-Date).AddSeconds(25)
while(-not (Test-Path -LiteralPath $target) -and (Get-Date) -lt $deadline){
  Start-Sleep -Milliseconds 500
}
if(-not (Test-Path -LiteralPath $target)){
  Write-Host 'XD_NATIVE_SAVE_RESULT=UNKNOWN_NO_REPLAY'
  throw 'XD_NATIVE_SAVE_TARGET_NOT_OBSERVED_AFTER_ONE_CLICK'
}
$file=Get-Item -LiteralPath $target
if($file.Length -lt 1000){throw 'XD_NATIVE_SAVE_FILE_TOO_SMALL'}
$sha=(Get-FileHash -LiteralPath $target -Algorithm SHA256).Hash
Write-Host "XD_NATIVE_SAVE_FILE_VERIFIED=PASS path=$target bytes=$($file.Length) sha256=$sha"
