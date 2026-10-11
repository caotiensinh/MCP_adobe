param([string]$SourceRunId="38136531800")
$ErrorActionPreference='Stop'
if($env:COMPUTERNAME -ne 'MRCAO'){throw 'XD_SAVE_CLICK_WRONG_MACHINE'}
if([System.Diagnostics.Process]::GetCurrentProcess().SessionId -ne 1){throw 'XD_SAVE_CLICK_NOT_INTERACTIVE_SESSION'}
if($SourceRunId -notmatch '^[0-9]{8,20}$'){throw 'XD_SAVE_CLICK_INVALID_SOURCE_RUN'}
$directory=Join-Path $env:USERPROFILE 'Documents\MCPAdobe'
$target=Join-Path $directory ("MCP_Mode1_Panda_XD_"+$SourceRunId+".xd")
if(-not (Test-Path -LiteralPath $directory -PathType Container)){throw 'XD_SAVE_CLICK_TARGET_DIRECTORY_MISSING'}
if(Test-Path -LiteralPath $target){throw 'XD_SAVE_CLICK_TARGET_EXISTS_DO_NOT_OVERWRITE'}
Add-Type -AssemblyName UIAutomationClient
Add-Type -AssemblyName UIAutomationTypes
Add-Type -AssemblyName System.Windows.Forms
Add-Type @'
using System;
using System.Text;
using System.Runtime.InteropServices;
public static class XdNativeRealMouse {
  [DllImport("user32.dll")] public static extern bool IsWindow(IntPtr hwnd);
  [DllImport("user32.dll")] public static extern uint GetWindowThreadProcessId(IntPtr hwnd,out uint pid);
  [DllImport("user32.dll",CharSet=CharSet.Unicode)] public static extern int GetClassName(IntPtr hwnd,StringBuilder value,int size);
  [DllImport("user32.dll",CharSet=CharSet.Unicode)] public static extern int GetWindowText(IntPtr hwnd,StringBuilder value,int size);
  [DllImport("user32.dll",CharSet=CharSet.Unicode)] public static extern IntPtr SendMessage(IntPtr hwnd,uint msg,IntPtr wParam,string text);
  [DllImport("user32.dll",CharSet=CharSet.Unicode)] public static extern IntPtr SendMessage(IntPtr hwnd,uint msg,IntPtr wParam,StringBuilder text);
  [DllImport("user32.dll")] public static extern IntPtr GetForegroundWindow();
  [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr hwnd);
  [DllImport("user32.dll")] public static extern bool ShowWindow(IntPtr hwnd,int mode);
  [DllImport("user32.dll")] public static extern bool SetCursorPos(int x,int y);
  [DllImport("user32.dll")] public static extern bool GetCursorPos(out PointStruct pos);
  [DllImport("user32.dll")] public static extern void mouse_event(uint flags,uint dx,uint dy,uint data,UIntPtr extra);
  [StructLayout(LayoutKind.Sequential)] public struct PointStruct {public int X;public int Y;}
}
'@
function WindowClass([IntPtr]$h){
  $b=New-Object System.Text.StringBuilder 128
  [void][XdNativeRealMouse]::GetClassName($h,$b,128)
  return $b.ToString()
}
function WindowText([IntPtr]$h){
  $b=New-Object System.Text.StringBuilder 512
  [void][XdNativeRealMouse]::GetWindowText($h,$b,512)
  return $b.ToString()
}
function FocusPid {
  $h=[XdNativeRealMouse]::GetForegroundWindow()
  $owner=[uint32]0
  if($h -ne [IntPtr]::Zero){[void][XdNativeRealMouse]::GetWindowThreadProcessId($h,[ref]$owner)}
  return [int]$owner
}
$desktop=[System.Windows.Automation.AutomationElement]::RootElement
$top=$desktop.FindAll([System.Windows.Automation.TreeScope]::Children,
                       [System.Windows.Automation.Condition]::TrueCondition)
$docs=@()
foreach($e in $top){
  if([string]$e.Current.Name -match '^Untitled.*Adobe XD$' -and
     [string]$e.Current.ClassName -eq 'ApplicationFrameWindow'){$docs+=,$e}
}
if($docs.Count -ne 1){throw "XD_SAVE_CLICK_DOCUMENT_NOT_UNIQUE count=$($docs.Count)"}
$doc=$docs[0]
$docPid=[int]$doc.Current.ProcessId
$docHwnd=[IntPtr]$doc.Current.NativeWindowHandle
$elements=$doc.FindAll([System.Windows.Automation.TreeScope]::Descendants,
                        [System.Windows.Automation.Condition]::TrueCondition)
$pickers=@()
foreach($e in $elements){
  if([string]$e.Current.Name -eq 'Save As' -and
     [string]$e.Current.ControlType.ProgrammaticName -eq 'ControlType.Window'){$pickers+=,$e}
}
if($pickers.Count -ne 1){throw "XD_SAVE_CLICK_PICKER_NOT_UNIQUE count=$($pickers.Count)"}
$picker=$pickers[0]
$pickerHwnd=[IntPtr]$picker.Current.NativeWindowHandle
$pickerPid=[int]$picker.Current.ProcessId
$pickerProc=Get-Process -Id $pickerPid -ErrorAction SilentlyContinue
if(-not $pickerProc -or $pickerProc.ProcessName -ne 'PickerHost' -or $pickerProc.SessionId -ne 1){
  throw "XD_SAVE_CLICK_NOT_A_REAL_PICKERHOST pid=$pickerPid"
}
$controls=$picker.FindAll([System.Windows.Automation.TreeScope]::Descendants,
                           [System.Windows.Automation.Condition]::TrueCondition)
$hosts=@();$saveButtons=@()
foreach($e in $controls){
  $id=[string]$e.Current.AutomationId
  $name=[string]$e.Current.Name
  if($id -eq 'FileNameControlHost'){$hosts+=,$e}
  if($id -eq '1' -and $name -eq 'Save'){$saveButtons+=,$e}
}
if($hosts.Count -ne 1 -or $saveButtons.Count -ne 1){
  throw "XD_SAVE_CLICK_CONTROLS_UNVERIFIED hosts=$($hosts.Count) saveButtons=$($saveButtons.Count)"
}
$fieldControls=$hosts[0].FindAll([System.Windows.Automation.TreeScope]::Descendants,
                                 [System.Windows.Automation.Condition]::TrueCondition)
$fields=@()
foreach($e in $fieldControls){
  $h=[IntPtr]$e.Current.NativeWindowHandle
  if([string]$e.Current.AutomationId -eq '1001' -and
     $h -ne [IntPtr]::Zero -and (WindowClass $h) -eq 'Edit'){$fields+=,$e}
}
if($fields.Count -ne 1){throw "XD_SAVE_CLICK_FILENAME_EDIT_UNVERIFIED count=$($fields.Count)"}
$fieldHwnd=[IntPtr]$fields[0].Current.NativeWindowHandle
$button=$saveButtons[0]
$buttonHwnd=[IntPtr]$button.Current.NativeWindowHandle
foreach($item in @(@('picker',$pickerHwnd),@('edit',$fieldHwnd),@('button',$buttonHwnd))){
  $name=[string]$item[0]
  $h=[IntPtr]$item[1]
  if(-not [XdNativeRealMouse]::IsWindow($h)){throw "XD_SAVE_CLICK_INVALID_HWND_$name"}
  $owner=[uint32]0
  [void][XdNativeRealMouse]::GetWindowThreadProcessId($h,[ref]$owner)
  if([int]$owner -ne $pickerPid){throw "XD_SAVE_CLICK_WRONG_HWND_OWNER_$name"}
}
if((WindowClass $buttonHwnd) -ne 'Button' -or (WindowText $buttonHwnd) -notmatch 'Save'){
  throw 'XD_SAVE_CLICK_BUTTON_CLASS_OR_LABEL_INVALID'
}
Write-Host "XD_SAVE_CLICK_GUARD=PASS document=$($doc.Current.Name) docPid=$docPid pickerPid=$pickerPid pickerHwnd=$pickerHwnd field=$fieldHwnd saveButton=$buttonHwnd"
# Cross-process GetWindowText returns blank. WM_GETTEXT is marshalled.
$buf=New-Object System.Text.StringBuilder 2048
[void][XdNativeRealMouse]::SendMessage($fieldHwnd,[uint32]13,[IntPtr]2048,$buf)
$oldText=$buf.ToString()
Write-Host "XD_SAVE_CLICK_FILENAME_BEFORE=$oldText"
if($oldText -ne $target){
  if($oldText -notmatch '^Untitled(?:-1)?\.xd$'){
    throw 'XD_SAVE_CLICK_PREVIOUS_UNKNOWN_FILENAME_VALUE_NO_REPLAY'
  }
  # Exactly one filename write. If interrupted, next execution will only
  # reconcile WM_GETTEXT, never overwrite a non-default unknown filename.
  $writeResult=[XdNativeRealMouse]::SendMessage($fieldHwnd,[uint32]12,[IntPtr]::Zero,$target)
  Write-Host "XD_SAVE_CLICK_FILENAME_WRITE_RESULT=$writeResult"
  if($writeResult -eq [IntPtr]::Zero){throw 'XD_SAVE_CLICK_FILENAME_WRITE_FAILED'}
}
$buf=New-Object System.Text.StringBuilder 2048
[void][XdNativeRealMouse]::SendMessage($fieldHwnd,[uint32]13,[IntPtr]2048,$buf)
if($buf.ToString() -ne $target){
  throw "XD_SAVE_CLICK_FILENAME_READBACK_FAILED actual=$($buf.ToString())"
}
Write-Host "XD_SAVE_CLICK_FILENAME_VERIFIED=PASS value=$($buf.ToString())"
$bounds=$button.Current.BoundingRectangle
$dialogBounds=$picker.Current.BoundingRectangle
$cx=[int][Math]::Floor($bounds.Left+$bounds.Width/2)
$cy=[int][Math]::Floor($bounds.Top+$bounds.Height/2)
if($bounds.Width -lt 20 -or $bounds.Height -lt 14 -or
   $cx -lt $dialogBounds.Left -or $cx -gt $dialogBounds.Right -or
   $cy -lt $dialogBounds.Top -or $cy -gt $dialogBounds.Bottom){
  throw "XD_SAVE_CLICK_BUTTON_NOT_INSIDE_PICKER coords=$cx,$cy"
}
Write-Host "XD_SAVE_CLICK_BUTTON_BOUNDS=PASS center=$cx,$cy"
[void][XdNativeRealMouse]::ShowWindow($docHwnd,9)
[void][XdNativeRealMouse]::SetForegroundWindow($docHwnd)
Start-Sleep -Milliseconds 350
$fg=FocusPid
if($fg -ne $docPid -and $fg -ne $pickerPid){
  $shell=New-Object -ComObject WScript.Shell
  [void]$shell.AppActivate([int]$docPid)
  Start-Sleep -Milliseconds 450
  $fg=FocusPid
}
Write-Host "XD_SAVE_CLICK_FOREGROUND_CHECK pid=$fg expectedXd=$docPid expectedPicker=$pickerPid"
if($fg -ne $docPid -and $fg -ne $pickerPid){
  throw 'XD_SAVE_CLICK_FOREGROUND_NOT_OWNED_NO_CLICK'
}
if(Test-Path -LiteralPath $target){throw 'XD_SAVE_CLICK_TARGET_APPEARED_BEFORE_CLICK_NO_OVERWRITE'}
if(-not [XdNativeRealMouse]::SetCursorPos($cx,$cy)){throw 'XD_SAVE_CLICK_POINTER_MOVE_FAILED'}
$point=New-Object 'XdNativeRealMouse+PointStruct'
[void][XdNativeRealMouse]::GetCursorPos([ref]$point)
if([Math]::Abs($point.X-$cx)>2 -or [Math]::Abs($point.Y-$cy)>2){
  throw 'XD_SAVE_CLICK_POINTER_LOCATION_MISMATCH'
}
[XdNativeRealMouse]::mouse_event([uint32]2,[uint32]0,[uint32]0,[uint32]0,[UIntPtr]::Zero)
[XdNativeRealMouse]::mouse_event([uint32]4,[uint32]0,[uint32]0,[uint32]0,[UIntPtr]::Zero)
Write-Host "XD_SAVE_CLICK_NATIVE_MOUSE_SENT_ONCE center=$cx,$cy"
$deadline=(Get-Date).AddSeconds(35)
while((Get-Date) -lt $deadline -and -not (Test-Path -LiteralPath $target)){
  Start-Sleep -Milliseconds 650
}
if(-not (Test-Path -LiteralPath $target)){
  Write-Host 'XD_SAVE_CLICK_FILE_STATUS=UNKNOWN_NO_REPEAT'
  throw 'XD_SAVE_CLICK_NATIVE_FILE_NOT_OBSERVED'
}
$file=Get-Item -LiteralPath $target
if($file.Length -lt 1000){throw 'XD_SAVE_CLICK_FILE_TOO_SMALL'}
$hash=(Get-FileHash -LiteralPath $target -Algorithm SHA256).Hash
Write-Host "XD_SAVE_CLICK_NATIVE_XD_FILE=PASS path=$target bytes=$($file.Length) sha256=$hash"
