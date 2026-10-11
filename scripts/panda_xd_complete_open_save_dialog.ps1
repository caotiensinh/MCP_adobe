param([string]$RunId='38132321143')
$ErrorActionPreference='Stop'
if($env:COMPUTERNAME -ne 'MRCAO'){throw 'XD_PICKER_WRONG_HOST'}
if([System.Diagnostics.Process]::GetCurrentProcess().SessionId -ne 1){throw 'XD_PICKER_WRONG_SESSION'}
if($RunId -notmatch '^[0-9]{8,20}$'){throw 'XD_PICKER_INVALID_RUN'}
$target=Join-Path $env:USERPROFILE "Documents\MCPAdobe\MCP_Mode1_Panda_XD_$RunId.xd"
if(Test-Path -LiteralPath $target){throw 'XD_PICKER_FILE_ALREADY_EXISTS_REFUSE_OVERWRITE'}
Add-Type -AssemblyName UIAutomationClient
Add-Type -AssemblyName UIAutomationTypes
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
$edit=$null
if($allEdits.Count -eq 1){$edit=$allEdits.Item(0)}
if(-not $edit){throw 'XD_PICKER_FILENAME_EDIT_NOT_UNIQUE_REFUSE_TYPING'}
$value=$edit.GetCurrentPattern([System.Windows.Automation.ValuePattern]::Pattern)
$value.SetValue($target)
Write-Host "XD_PICKER_PATH_SET=PASS target=$target"
$saveCandidates=$dialog.FindAll([System.Windows.Automation.TreeScope]::Descendants,
     (New-Object System.Windows.Automation.PropertyCondition(
       [System.Windows.Automation.AutomationElement]::AutomationIdProperty,'1')))
$save=$null
foreach($item in $saveCandidates){
  $label=[string]$item.Current.Name
  if($label -match 'Save|保存'){
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
if(-not $clicked){throw 'XD_PICKER_SAVE_CLICK_NOT_SUPPORTED_STOP_NO_REPLAY'}
$deadline=(Get-Date).AddSeconds(35)
while(-not (Test-Path -LiteralPath $target) -and (Get-Date) -lt $deadline){
  Start-Sleep -Milliseconds 650
}
if(-not (Test-Path -LiteralPath $target)){throw 'XD_PICKER_FILE_NOT_CREATED'}
$file=Get-Item -LiteralPath $target
if($file.Length -lt 1000){throw 'XD_PICKER_NATIVE_FILE_TOO_SMALL'}
$hash=(Get-FileHash -LiteralPath $target -Algorithm SHA256).Hash
Write-Host "XD_PICKER_NATIVE_XD_VERIFIED=PASS bytes=$($file.Length) path=$target sha256=$hash"
