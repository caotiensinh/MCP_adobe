param([string]$RunId='38132321143')
$ErrorActionPreference='Stop'
if($env:COMPUTERNAME -ne 'MRCAO'){throw 'XD_MENU_SAVE_WRONG_HOST'}
if([System.Diagnostics.Process]::GetCurrentProcess().SessionId -ne 1){throw 'XD_MENU_SAVE_WRONG_SESSION'}
$target=Join-Path $env:USERPROFILE "Documents\MCPAdobe\MCP_Mode1_Panda_XD_$RunId.xd"
if(Test-Path -LiteralPath $target){throw 'XD_MENU_SAVE_TARGET_ALREADY_EXISTS_NO_OVERWRITE'}
Add-Type -AssemblyName UIAutomationClient
Add-Type -AssemblyName UIAutomationTypes
Add-Type -AssemblyName System.Windows.Forms
Add-Type @'
using System;
using System.Runtime.InteropServices;
public static class XdSaveMenuNative {
 [DllImport("user32.dll")] public static extern bool ShowWindow(IntPtr h,int n);
 [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr h);
 [DllImport("user32.dll")] public static extern IntPtr GetForegroundWindow();
 [DllImport("user32.dll")] public static extern uint GetWindowThreadProcessId(IntPtr h,out uint pid);
}
'@
$xd=Get-Process -ErrorAction SilentlyContinue | Where-Object {
 $_.MainWindowHandle -ne 0 -and $_.SessionId -eq 1 -and
 $_.MainWindowTitle -match '^Untitled.*Adobe XD$'
} | Select-Object -First 1
if(-not $xd){throw 'XD_MENU_SAVE_EXISTING_UNSAVED_DOCUMENT_NOT_FOUND'}
Write-Host "XD_MENU_SAVE_REAL_DOCUMENT=PASS pid=$($xd.Id) title=$($xd.MainWindowTitle)"
[void][XdSaveMenuNative]::ShowWindow($xd.MainWindowHandle,9)
[void][XdSaveMenuNative]::SetForegroundWindow($xd.MainWindowHandle)
Start-Sleep -Milliseconds 350
$fg=[XdSaveMenuNative]::GetForegroundWindow()
$owner=[uint32]0
if($fg -ne [IntPtr]::Zero){[void][XdSaveMenuNative]::GetWindowThreadProcessId($fg,[ref]$owner)}
if($owner -ne $xd.Id){
 $shell=New-Object -ComObject WScript.Shell
 [void]$shell.AppActivate([int]$xd.Id)
 Start-Sleep -Milliseconds 550
 $fg=[XdSaveMenuNative]::GetForegroundWindow();$owner=[uint32]0
 if($fg -ne [IntPtr]::Zero){[void][XdSaveMenuNative]::GetWindowThreadProcessId($fg,[ref]$owner)}
}
if($owner -ne $xd.Id){throw "XD_MENU_SAVE_FOREGROUND_WRONG actual=$owner expected=$($xd.Id)"}
$root=[System.Windows.Automation.AutomationElement]::FromHandle($xd.MainWindowHandle)
$fileCondition=New-Object System.Windows.Automation.PropertyCondition(
 [System.Windows.Automation.AutomationElement]::AutomationIdProperty,'AppMenu_File')
$file=$root.FindFirst([System.Windows.Automation.TreeScope]::Descendants,$fileCondition)
if(-not $file){throw 'XD_MENU_SAVE_FILE_MENU_AUTOMATION_ID_MISSING'}
Write-Host "XD_MENU_FILE_ELEMENT=PASS name=$($file.Current.Name) class=$($file.Current.ClassName)"
try{
 $expand=$file.GetCurrentPattern([System.Windows.Automation.ExpandCollapsePattern]::Pattern)
 $expand.Expand()
 Write-Host 'XD_MENU_FILE_EXPANDED=PASS'
}catch{
 try{
  $invoke=$file.GetCurrentPattern([System.Windows.Automation.InvokePattern]::Pattern)
  $invoke.Invoke()
  Write-Host 'XD_MENU_FILE_INVOKED=PASS'
 }catch{
  throw "XD_MENU_FILE_CANNOT_OPEN=$($_.Exception.Message)"
 }
}
Start-Sleep -Milliseconds 650
$items=@()
$all=$root.FindAll([System.Windows.Automation.TreeScope]::Descendants,[System.Windows.Automation.Condition]::TrueCondition)
for($i=0;$i -lt $all.Count;$i++){
 $e=$all.Item($i)
 $name=[string]$e.Current.Name
 $automationId=[string]$e.Current.AutomationId
 $class=[string]$e.Current.ClassName
 if($name -match 'Save|Local|File' -or $automationId -match 'Save'){
  Write-Host "XD_MENU_DISCOVERED_ENTRY name=$name automationId=$automationId class=$class type=$($e.Current.ControlType.ProgrammaticName)"
  $items+=,$e
 }
}
$local=@($items | Where-Object {
 ([string]$_.Current.Name) -match 'Save As Local Document' -or
 ([string]$_.Current.AutomationId) -match 'SaveAsLocal|SaveLocal'
})
if($local.Count -ne 1){throw "XD_MENU_SAVE_LOCAL_ENTRY_NOT_UNIQUE count=$($local.Count) NO_COMMAND_SENT"}
$entry=$local[0]
try{
 $invoke=$entry.GetCurrentPattern([System.Windows.Automation.InvokePattern]::Pattern)
 $invoke.Invoke()
}catch{
 try{
  $legacy=$entry.GetCurrentPattern([System.Windows.Automation.LegacyIAccessiblePattern]::Pattern)
  $legacy.DoDefaultAction()
 }catch{
  throw "XD_MENU_SAVE_LOCAL_INVOKE_FAILED=$($_.Exception.Message)"
 }
}
Write-Host 'XD_MENU_SAVE_AS_LOCAL_CLICKED=PASS'
$desktop=[System.Windows.Automation.AutomationElement]::RootElement
$dialog=$null
$deadline=(Get-Date).AddSeconds(30)
do{
 Start-Sleep -Milliseconds 600
 $wins=$desktop.FindAll([System.Windows.Automation.TreeScope]::Children,[System.Windows.Automation.Condition]::TrueCondition)
 foreach($w in $wins){
  $name=[string]$w.Current.Name
  $class=[string]$w.Current.ClassName
  if($class -eq '#32770' -or $name -match 'Save As|Save as|Save Local'){
   $dialog=$w;break
  }
 }
}until($dialog -or (Get-Date)-gt $deadline)
if(-not $dialog){
 foreach($w in $wins){
  if($w.Current.Name){Write-Host "XD_MENU_POST_SAVE_WINDOW title=$($w.Current.Name) class=$($w.Current.ClassName)"}
 }
 $tree=$root.FindAll([System.Windows.Automation.TreeScope]::Descendants,[System.Windows.Automation.Condition]::TrueCondition)
 for($i=0;$i -lt $tree.Count;$i++){
  $e=$tree.Item($i);$name=[string]$e.Current.Name;$id=[string]$e.Current.AutomationId
  if($name -match 'Save|Local|Name|Folder|Browse' -or $id -match 'Save|FileName'){
   Write-Host "XD_MENU_POST_SAVE_CONTROL name=$name id=$id type=$($e.Current.ControlType.ProgrammaticName)"
  }
 }
 throw 'XD_MENU_SAVE_DIALOG_MISSING_AFTER_EXPLICIT_FILE_MENU_CLICK'
}
Write-Host "XD_MENU_SAVE_DIALOG_FOUND title=$($dialog.Current.Name) class=$($dialog.Current.ClassName)"
$editCond=New-Object System.Windows.Automation.PropertyCondition(
 [System.Windows.Automation.AutomationElement]::ControlTypeProperty,[System.Windows.Automation.ControlType]::Edit)
$edits=$dialog.FindAll([System.Windows.Automation.TreeScope]::Descendants,$editCond)
$filename=$null
foreach($e in $edits){
 $name=[string]$e.Current.Name;$id=[string]$e.Current.AutomationId
 Write-Host "XD_MENU_SAVE_EDIT name=$name id=$id"
 if($id -match '1001|FileName' -or $name -match 'File name'){$filename=$e;break}
}
if(-not $filename){throw 'XD_MENU_SAVE_FILENAME_INPUT_NOT_FOUND'}
$p=$filename.GetCurrentPattern([System.Windows.Automation.ValuePattern]::Pattern)
$p.SetValue($target)
$btnCond=New-Object System.Windows.Automation.PropertyCondition(
 [System.Windows.Automation.AutomationElement]::ControlTypeProperty,[System.Windows.Automation.ControlType]::Button)
$buttons=$dialog.FindAll([System.Windows.Automation.TreeScope]::Descendants,$btnCond)
$save=$null
foreach($b in $buttons){
 if(([string]$b.Current.Name) -match '^Save' -or ([string]$b.Current.AutomationId) -eq '1'){$save=$b;break}
}
if(-not $save){throw 'XD_MENU_SAVE_BUTTON_NOT_FOUND'}
$invoke=$save.GetCurrentPattern([System.Windows.Automation.InvokePattern]::Pattern)
$invoke.Invoke()
Write-Host "XD_MENU_NATIVE_FILE_WRITE_REQUESTED=PASS path=$target"
$deadline=(Get-Date).AddSeconds(35)
do{Start-Sleep -Milliseconds 700}until((Test-Path -LiteralPath $target) -or (Get-Date)-gt $deadline)
if(-not (Test-Path -LiteralPath $target)){throw 'XD_MENU_NATIVE_FILE_NOT_OBSERVED'}
$file=Get-Item -LiteralPath $target
if($file.Length -lt 1000){throw "XD_MENU_NATIVE_FILE_TOO_SMALL bytes=$($file.Length)"}
$hash=(Get-FileHash -LiteralPath $target -Algorithm SHA256).Hash
Write-Host "XD_MENU_NATIVE_SAVE=PASS path=$target bytes=$($file.Length) sha256=$hash"
