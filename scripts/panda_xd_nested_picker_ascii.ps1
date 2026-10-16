param([string]$RunId='38132321143')
$ErrorActionPreference='Stop'
if($env:COMPUTERNAME -ne 'MRCAO'){throw 'XD_NESTED_PICKER_WRONG_HOST'}
if([System.Diagnostics.Process]::GetCurrentProcess().SessionId -ne 1){throw 'XD_NESTED_PICKER_WRONG_SESSION'}
if($RunId -notmatch '^[0-9]{8,20}$'){throw 'XD_NESTED_PICKER_INVALID_RUN_ID'}
$path=Join-Path $env:USERPROFILE "Documents\MCPAdobe\MCP_Mode1_Panda_XD_$RunId.xd"
if(Test-Path -LiteralPath $path){throw 'XD_NESTED_PICKER_OUTPUT_ALREADY_EXISTS'}
Add-Type -AssemblyName UIAutomationClient
Add-Type -AssemblyName UIAutomationTypes
$apps=@(Get-Process -ErrorAction SilentlyContinue | Where-Object {
  $_.MainWindowHandle -ne 0 -and $_.SessionId -eq 1 -and
  $_.MainWindowTitle -match '^Untitled.*Adobe XD$'
})
if($apps.Count -ne 1){throw "XD_NESTED_PICKER_ACTIVE_TEST_DOCUMENT_COUNT=$($apps.Count)"}
$xd=$apps[0]
$main=[System.Windows.Automation.AutomationElement]::FromHandle($xd.MainWindowHandle)
$all=$main.FindAll([System.Windows.Automation.TreeScope]::Descendants,
                 [System.Windows.Automation.Condition]::TrueCondition)
$dialogs=@()
foreach($element in $all){
  if(([string]$element.Current.Name) -eq 'Save As' -and
     $element.Current.ControlType -eq [System.Windows.Automation.ControlType]::Window){
    $dialogs+=,$element
  }
}
if($dialogs.Count -ne 1){throw "XD_NESTED_PICKER_DIALOG_COUNT=$($dialogs.Count)"}
$dlg=$dialogs[0]
Write-Host "XD_NESTED_PICKER_DIALOG=PASS appPid=$($xd.Id) title=$($xd.MainWindowTitle)"
$hostFilter=New-Object System.Windows.Automation.PropertyCondition(
  [System.Windows.Automation.AutomationElement]::AutomationIdProperty,
  'FileNameControlHost'
)
$host=$dlg.FindFirst([System.Windows.Automation.TreeScope]::Descendants,$hostFilter)
if(-not $host){throw 'XD_NESTED_PICKER_FILENAME_HOST_ABSENT'}
$editFilter=New-Object System.Windows.Automation.PropertyCondition(
 [System.Windows.Automation.AutomationElement]::ControlTypeProperty,
 [System.Windows.Automation.ControlType]::Edit
)
$edits=$host.FindAll([System.Windows.Automation.TreeScope]::Descendants,$editFilter)
Write-Host "XD_NESTED_PICKER_FILENAME_EDITS=$($edits.Count)"
foreach($editItem in $edits){
 Write-Host "XD_NESTED_PICKER_EDIT name=$($editItem.Current.Name) id=$($editItem.Current.AutomationId)"
}
if($edits.Count -ne 1){throw 'XD_NESTED_PICKER_FILENAME_INPUT_NOT_UNIQUE_NO_WRITE'}
$edit=$edits.Item(0)
$v=$edit.GetCurrentPattern([System.Windows.Automation.ValuePattern]::Pattern)
$v.SetValue($path)
if(([string]$v.Current.Value) -ne $path){throw 'XD_NESTED_PICKER_FILEPATH_READBACK_MISMATCH'}
Write-Host "XD_NESTED_PICKER_FILEPATH_READBACK=PASS target=$path"
$saveId=New-Object System.Windows.Automation.PropertyCondition(
 [System.Windows.Automation.AutomationElement]::AutomationIdProperty,'1'
)
$buttonCandidates=$dlg.FindAll([System.Windows.Automation.TreeScope]::Descendants,$saveId)
$eligible=@()
foreach($b in $buttonCandidates){
 Write-Host "XD_NESTED_PICKER_SAVE_CANDIDATE name=$($b.Current.Name) type=$($b.Current.ControlType.ProgrammaticName)"
 if(([string]$b.Current.Name) -match '^Save'){$eligible+=,$b}
}
if($eligible.Count -ne 1){throw "XD_NESTED_PICKER_SAVE_CONTROL_NOT_UNIQUE count=$($eligible.Count)"}
$button=$eligible[0]
$didClick=$false
try{
  $invoke=$button.GetCurrentPattern([System.Windows.Automation.InvokePattern]::Pattern)
}catch{
  $invoke=$null
}
if($invoke){
  $invoke.Invoke()
  $didClick=$true
  Write-Host 'XD_NESTED_PICKER_SAVE_INVOKE=PASS method=UIA_Invoke'
}else{
  try{$legacy=$button.GetCurrentPattern([System.Windows.Automation.LegacyIAccessiblePattern]::Pattern)}
  catch{$legacy=$null}
  if($legacy){
    $legacy.DoDefaultAction()
    $didClick=$true
    Write-Host 'XD_NESTED_PICKER_SAVE_INVOKE=PASS method=Legacy_Default'
  }
}
if(-not $didClick){throw 'XD_NESTED_PICKER_SAVE_BUTTON_PATTERN_NOT_SUPPORTED_NO_CLICK'}
$deadline=(Get-Date).AddSeconds(35)
do{Start-Sleep -Milliseconds 600}until((Test-Path -LiteralPath $path) -or (Get-Date)-gt $deadline)
if(-not (Test-Path -LiteralPath $path)){throw 'XD_NESTED_PICKER_SAVE_ACCEPTED_FILE_NOT_OBSERVED'}
$info=Get-Item -LiteralPath $path
if($info.Length -lt 1000){throw "XD_NESTED_PICKER_NATIVE_FILE_TOO_SMALL bytes=$($info.Length)"}
$hash=(Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash
Write-Host "XD_NESTED_PICKER_NATIVE_XD_PASS=PASS path=$path bytes=$($info.Length) sha256=$hash"
