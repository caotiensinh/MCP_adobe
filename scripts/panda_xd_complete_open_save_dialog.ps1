param([string]$RunId='38132321143')
$ErrorActionPreference='Stop'
if($env:COMPUTERNAME -ne 'MRCAO'){throw 'XD_PICKER_WRONG_HOST'}
if([System.Diagnostics.Process]::GetCurrentProcess().SessionId -ne 1){throw 'XD_PICKER_WRONG_SESSION'}
if($RunId -notmatch '^[0-9]{8,20}$'){throw 'XD_PICKER_INVALID_RUN'}
$target=Join-Path $env:USERPROFILE "Documents\MCPAdobe\MCP_Mode1_Panda_XD_$RunId.xd"
if(Test-Path -LiteralPath $target){throw 'XD_PICKER_FILE_ALREADY_EXISTS_REFUSE_OVERWRITE'}
Add-Type -AssemblyName UIAutomationClient
Add-Type -AssemblyName UIAutomationTypes
Add-Type -AssemblyName System.Windows.Forms
Add-Type @'
using System;
using System.Runtime.InteropServices;
public static class XdSavePickerFocus {
  [DllImport("user32.dll")] public static extern bool SetCursorPos(int x,int y);
  [DllImport("user32.dll")] public static extern void mouse_event(uint flags,uint dx,uint dy,uint data,UIntPtr extra);
  [DllImport("user32.dll")] public static extern bool GetCursorPos(out WinPoint point);
  [StructLayout(LayoutKind.Sequential)] public struct WinPoint { public int X; public int Y; }
  [DllImport("user32.dll")] public static extern bool ShowWindow(IntPtr h,int cmd);
  [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr h);
  [DllImport("user32.dll")] public static extern IntPtr GetForegroundWindow();
  [DllImport("user32.dll")] public static extern uint GetWindowThreadProcessId(IntPtr h,out uint pid);
}
'@
function Assert-XdForeground([System.Diagnostics.Process]$TargetProcess){
  $focusWindow=[XdSavePickerFocus]::GetForegroundWindow()
  $owner=[uint32]0
  if($focusWindow -ne [IntPtr]::Zero){[void][XdSavePickerFocus]::GetWindowThreadProcessId($focusWindow,[ref]$owner)}
  if([int]$owner -ne $TargetProcess.Id){
    [void][XdSavePickerFocus]::ShowWindow($TargetProcess.MainWindowHandle,9)
    [void][XdSavePickerFocus]::SetForegroundWindow($TargetProcess.MainWindowHandle)
    Start-Sleep -Milliseconds 200
    $shell=New-Object -ComObject WScript.Shell
    [void]$shell.AppActivate([int]$TargetProcess.Id)
    Start-Sleep -Milliseconds 350
    $focusWindow=[XdSavePickerFocus]::GetForegroundWindow()
    $owner=[uint32]0
    if($focusWindow -ne [IntPtr]::Zero){[void][XdSavePickerFocus]::GetWindowThreadProcessId($focusWindow,[ref]$owner)}
  }
  if([int]$owner -ne $TargetProcess.Id){throw "XD_PICKER_FOREGROUND_NOT_XD_ACTUAL_$owner"}
  Write-Host "XD_PICKER_FOREGROUND_PID_VERIFIED=PASS pid=$owner"
}
$windows=@(Get-Process -ErrorAction SilentlyContinue | Where-Object {
  $_.SessionId -eq 1 -and $_.MainWindowHandle -ne 0 -and
  $_.MainWindowTitle -match '^Untitled.*Adobe XD$'
})
if($windows.Count -ne 1){throw "XD_PICKER_XD_WINDOW_COUNT_INVALID=$($windows.Count)"}
$xd=$windows[0]
$app=[System.Windows.Automation.AutomationElement]::FromHandle($xd.MainWindowHandle)
$desc=$app.FindAll([System.Windows.Automation.TreeScope]::Descendants,
                   [System.Windows.Automation.Condition]::TrueCondition)
$dialog=$null
$dialogs=@()
foreach($item in $desc){
  $nm=[string]$item.Current.Name
  $tp=[string]$item.Current.ControlType.ProgrammaticName
  if($nm -eq 'Save As' -and $tp -eq 'ControlType.Window'){
    $dialogs+=,$item
  }
}
if($dialogs.Count -ne 1){throw "XD_PICKER_OPEN_SAVE_AS_NESTED_DIALOG_NOT_UNIQUE=$($dialogs.Count)"}
$dialog=$dialogs[0]
Write-Host "XD_PICKER_NESTED_DIALOG=PASS app=$($xd.MainWindowTitle) name=$($dialog.Current.Name)"
$fileHost=$dialog.FindFirst([System.Windows.Automation.TreeScope]::Descendants,
  (New-Object System.Windows.Automation.PropertyCondition(
    [System.Windows.Automation.AutomationElement]::AutomationIdProperty,'FileNameControlHost')))
if(-not $fileHost){throw 'XD_PICKER_FILENAME_CONTROL_HOST_MISSING'}
$allEdits=$fileHost.FindAll([System.Windows.Automation.TreeScope]::Descendants,
    (New-Object System.Windows.Automation.PropertyCondition(
     [System.Windows.Automation.AutomationElement]::ControlTypeProperty,
     [System.Windows.Automation.ControlType]::Edit)))
Write-Host "XD_PICKER_FILENAME_HOST_EDITS=$($allEdits.Count)"
if($allEdits.Count -eq 0){
  $everything=$dialog.FindAll([System.Windows.Automation.TreeScope]::Descendants,
        [System.Windows.Automation.Condition]::TrueCondition)
  for($i=0;$i -lt [Math]::Min($everything.Count,180);$i++){
    $el=$everything.Item($i)
    $name=[string]$el.Current.Name
    $id=[string]$el.Current.AutomationId
    $typ=[string]$el.Current.ControlType.ProgrammaticName
    Write-Host "XD_PICKER_DIALOG_UI ordinal=$i name=$name id=$id type=$typ"
  }
}
$edit=$null
if($allEdits.Count -eq 1){$edit=$allEdits.Item(0)}
if(-not $edit){
  $desc=$dialog.FindAll([System.Windows.Automation.TreeScope]::Descendants,
               [System.Windows.Automation.Condition]::TrueCondition)
  $pick=@()
  foreach($candidate in $desc){
    if(([string]$candidate.Current.AutomationId) -eq '1001' -and
       ([string]$candidate.Current.Name) -match '\.xd$'){
      $pick+=,$candidate
    }
  }
  if($pick.Count -eq 1){$edit=$pick[0]}
}
if(-not $edit){throw 'XD_PICKER_FILENAME_INPUT_AMBIGUOUS'}
Write-Host "XD_PICKER_FILENAME_INPUT_FOUND name=$($edit.Current.Name) id=$($edit.Current.AutomationId) type=$($edit.Current.ControlType.ProgrammaticName)"
$pathSet=$false
try{
  $value=$edit.GetCurrentPattern([System.Windows.Automation.ValuePattern]::Pattern)
  $value.SetValue($target)
  $pathSet=$true
  Write-Host 'XD_PICKER_PATH_SET_METHOD=VALUE'
}catch{
  try{
    $legacy=$edit.GetCurrentPattern([System.Windows.Automation.LegacyIAccessiblePattern]::Pattern)
    $legacy.SetValue($target)
    $pathSet=$true
    Write-Host 'XD_PICKER_PATH_SET_METHOD=LEGACY'
  }catch{
    Write-Host "XD_PICKER_VALUE_PATTERN_UNAVAILABLE=$($_.Exception.Message)"
  }
}
if(-not $pathSet){
  # Windows common-file-dialog exposes the filename COMBO as Pane id=1001,
  # not as Edit/Value. Enter only after strict XD process + focus verification.
  Assert-XdForeground $xd
  try {
    $edit.SetFocus()
    Write-Host 'XD_PICKER_INPUT_SETFOCUS=PASS'
  }catch{
    Write-Host "XD_PICKER_INPUT_SETFOCUS_UNSUPPORTED=$($_.Exception.Message)"
    $bounds=$edit.Current.BoundingRectangle
    $dialogBounds=$dialog.Current.BoundingRectangle
    $px=[int][Math]::Floor($bounds.Left+$bounds.Width/2)
    $py=[int][Math]::Floor($bounds.Top+$bounds.Height/2)
    if($bounds.Width -lt 20 -or $bounds.Height -lt 10 -or
       $px -lt $dialogBounds.Left -or $px -gt $dialogBounds.Right -or
       $py -lt $dialogBounds.Top -or $py -gt $dialogBounds.Bottom){
       throw 'XD_PICKER_INPUT_CLICK_OUTSIDE_MEASURED_DIALOG'
    }
    Assert-XdForeground $xd
    if(-not [XdSavePickerFocus]::SetCursorPos($px,$py)){
      throw 'XD_PICKER_CURSOR_MOVE_FAILED'
    }
    [XdSavePickerFocus]::mouse_event([uint32]0x0002,[uint32]0,[uint32]0,[uint32]0,[UIntPtr]::Zero)
    [XdSavePickerFocus]::mouse_event([uint32]0x0004,[uint32]0,[uint32]0,[uint32]0,[UIntPtr]::Zero)
    Write-Host "XD_PICKER_INPUT_CLICKED_ONCE=PASS x=$px y=$py"
  }
  Start-Sleep -Milliseconds 220
  $focused=[System.Windows.Automation.AutomationElement]::FocusedElement
  $focusedId=[string]$focused.Current.AutomationId
  $focusedName=[string]$focused.Current.Name
  Write-Host "XD_PICKER_FILENAME_FOCUSED id=$focusedId name=$focusedName"
  if($focusedId -ne '1001' -and $focusedName -notmatch '^Untitled.*\\.xd$'){
    throw 'XD_PICKER_FILENAME_FOCUS_NOT_VERIFIED_NO_INPUT'
  }
  Assert-XdForeground $xd
  [System.Windows.Forms.SendKeys]::SendWait('^a')
  [System.Windows.Forms.SendKeys]::SendWait($target)
  Start-Sleep -Milliseconds 220
  $updated=[string]$edit.Current.Name
  $focused=[System.Windows.Automation.AutomationElement]::FocusedElement
  $focusName=[string]$focused.Current.Name
  Write-Host "XD_PICKER_FILENAME_AFTER_INPUT element=$updated focused=$focusName"
  if($updated -ne $target -and $focusName -ne $target){
    throw 'XD_PICKER_FILENAME_VALUE_NOT_READBACK_CONFIRMED_NO_SAVE'
  }
  $pathSet=$true
  Write-Host 'XD_PICKER_PATH_SET_METHOD=VERIFIED_UIA_FOCUS_SENDKEYS'
}
Write-Host "XD_PICKER_PATH_SET=PASS target=$target"
$saveCandidates=$dialog.FindAll([System.Windows.Automation.TreeScope]::Descendants,
     (New-Object System.Windows.Automation.PropertyCondition(
       [System.Windows.Automation.AutomationElement]::AutomationIdProperty,'1')))
$save=$null
foreach($item in $saveCandidates){
  $label=[string]$item.Current.Name
  if($label -match 'Save|Save'){
    $save=$item
    break
  }
}
if(-not $save){throw 'XD_PICKER_SAVE_BUTTON_NOT_IDENTIFIED'}
Write-Host "XD_PICKER_SAVE_CONTROL_IDENTIFIED=PASS name=$($save.Current.Name) type=$($save.Current.ControlType.ProgrammaticName)"
$clicked=$false
try{
  $invoke=$save.GetCurrentPattern([System.Windows.Automation.InvokePattern]::Pattern)
  $invoke.Invoke()
  $clicked=$true
  Write-Host 'XD_PICKER_SAVE_INVOKED=PASS method=InvokePattern'
}catch{
  try{
    $legacy=$save.GetCurrentPattern([System.Windows.Automation.LegacyIAccessiblePattern]::Pattern)
    $legacy.DoDefaultAction()
    $clicked=$true
    Write-Host 'XD_PICKER_SAVE_INVOKED=PASS method=LegacyDefault'
  }catch{
    Write-Host "XD_PICKER_NATIVE_SAVE_PATTERN_NOT_SUPPORTED=$($_.Exception.Message)"
  }
}
if(-not $clicked){
  # The Save control is a Win32 Pane, not a UIA Button. Click precisely
  # inside its measured bounding rectangle and never send a second Enter.
  $bounds=$save.Current.BoundingRectangle
  $dialogBounds=$dialog.Current.BoundingRectangle
  $px=[int][Math]::Floor($bounds.Left+$bounds.Width/2)
  $py=[int][Math]::Floor($bounds.Top+$bounds.Height/2)
  if($bounds.Width -lt 12 -or $bounds.Height -lt 10 -or
     $px -lt $dialogBounds.Left -or $px -gt $dialogBounds.Right -or
     $py -lt $dialogBounds.Top -or $py -gt $dialogBounds.Bottom){
    throw 'XD_PICKER_SAVE_CLICK_OUTSIDE_MEASURED_DIALOG'
  }
  Assert-XdForeground $xd
  if(-not [XdSavePickerFocus]::SetCursorPos($px,$py)){throw 'XD_PICKER_SAVE_CURSOR_MOVE_FAILED'}
  [XdSavePickerFocus]::mouse_event([uint32]0x0002,[uint32]0,[uint32]0,[uint32]0,[UIntPtr]::Zero)
  [XdSavePickerFocus]::mouse_event([uint32]0x0004,[uint32]0,[uint32]0,[uint32]0,[UIntPtr]::Zero)
  $clicked=$true
  Write-Host "XD_PICKER_SAVE_UIA_BOUNDING_BOX_CLICKED_ONCE=PASS x=$px y=$py"
}
$deadline=(Get-Date).AddSeconds(35)
while(-not (Test-Path -LiteralPath $target) -and (Get-Date) -lt $deadline){
  Start-Sleep -Milliseconds 650
}
if(-not (Test-Path -LiteralPath $target)){throw 'XD_PICKER_FILE_NOT_CREATED'}
$file=Get-Item -LiteralPath $target
if($file.Length -lt 1000){throw 'XD_PICKER_NATIVE_FILE_TOO_SMALL'}
$hash=(Get-FileHash -LiteralPath $target -Algorithm SHA256).Hash
Write-Host "XD_PICKER_NATIVE_XD_VERIFIED=PASS bytes=$($file.Length) path=$target sha256=$hash"
