param()
$ErrorActionPreference='Stop'
if($env:COMPUTERNAME -ne 'MRCAO'){throw 'XD_SAVE_STAGE_WRONG_HOST'}
if([System.Diagnostics.Process]::GetCurrentProcess().SessionId -ne 1){throw 'XD_SAVE_STAGE_WRONG_SESSION'}
Add-Type -AssemblyName UIAutomationClient
Add-Type -AssemblyName UIAutomationTypes
$root=[System.Windows.Automation.AutomationElement]::RootElement
$top=$root.FindAll([System.Windows.Automation.TreeScope]::Children,
                    [System.Windows.Automation.Condition]::TrueCondition)
$docs=@()
foreach($e in $top){
  if([string]$e.Current.Name -match '^Untitled.*Adobe XD$' -and
     [string]$e.Current.ClassName -eq 'ApplicationFrameWindow'){$docs+=,$e}
}
if($docs.Count -ne 1){throw "XD_SAVE_STAGE_DOCUMENT_WINDOW_COUNT=$($docs.Count)"}
$document=$docs[0]
Write-Host "XD_SAVE_STAGE_LIVE_DOCUMENT=PASS title=$($document.Current.Name) pid=$($document.Current.ProcessId)"
$all=$document.FindAll([System.Windows.Automation.TreeScope]::Descendants,
                       [System.Windows.Automation.Condition]::TrueCondition)
$existingPicker=@()
foreach($e in $all){
  if([string]$e.Current.Name -eq 'Save As' -and
     [string]$e.Current.ControlType.ProgrammaticName -eq 'ControlType.Window'){$existingPicker+=,$e}
}
if($existingPicker.Count -gt 0){
  Write-Host "XD_SAVE_STAGE_EXISTING_PICKER=PASS count=$($existingPicker.Count) no_new_Save_command"
  exit 0
}
$cond=New-Object System.Windows.Automation.PropertyCondition(
  [System.Windows.Automation.AutomationElement]::AutomationIdProperty,'AppMenu_File')
$fileMenu=$document.FindFirst([System.Windows.Automation.TreeScope]::Descendants,$cond)
if(-not $fileMenu){throw 'XD_SAVE_STAGE_FILE_MENU_ABSENT'}
Write-Host "XD_SAVE_STAGE_FILE_MENU=FOUND enabled=$($fileMenu.Current.IsEnabled)"
try{
  $exp=$fileMenu.GetCurrentPattern([System.Windows.Automation.ExpandCollapsePattern]::Pattern)
  if($exp.Current.ExpandCollapseState -ne [System.Windows.Automation.ExpandCollapseState]::Expanded){
    $exp.Expand()
  }
}catch{
  throw "XD_SAVE_STAGE_CANNOT_OPEN_MENU=$($_.Exception.Message)"
}
Start-Sleep -Milliseconds 350
$saveIdCond=New-Object System.Windows.Automation.PropertyCondition(
  [System.Windows.Automation.AutomationElement]::AutomationIdProperty,'AppMenu_Save')
$saveAsIdCond=New-Object System.Windows.Automation.PropertyCondition(
  [System.Windows.Automation.AutomationElement]::AutomationIdProperty,'AppMenu_SaveAs')
$save=$document.FindFirst([System.Windows.Automation.TreeScope]::Descendants,$saveIdCond)
$saveAs=$document.FindFirst([System.Windows.Automation.TreeScope]::Descendants,$saveAsIdCond)
if($save){Write-Host "XD_SAVE_STAGE_SAVE_MENU name=$($save.Current.Name) enabled=$($save.Current.IsEnabled) type=$($save.Current.ControlType.ProgrammaticName)"}
if($saveAs){Write-Host "XD_SAVE_STAGE_SAVEAS_MENU name=$($saveAs.Current.Name) enabled=$($saveAs.Current.IsEnabled) type=$($saveAs.Current.ControlType.ProgrammaticName)"}
$choice=$null
if($save -and $save.Current.IsEnabled){$choice=$save}
elseif($saveAs -and $saveAs.Current.IsEnabled){$choice=$saveAs}
if(-not $choice){throw 'XD_SAVE_STAGE_SAVE_AND_SAVEAS_BOTH_DISABLED_NO_MUTATION'}
$choiceName=[string]$choice.Current.Name
Write-Host "XD_SAVE_STAGE_ONE_COMMAND_SELECTED=$choiceName"
try{
  $invoke=$choice.GetCurrentPattern([System.Windows.Automation.InvokePattern]::Pattern)
  $invoke.Invoke()
}catch{
  throw "XD_SAVE_STAGE_NATIVE_MENU_ACTION_UNCERTAIN_NO_REPLAY=$($_.Exception.Message)"
}
Write-Host "XD_SAVE_STAGE_NATIVE_MENU_COMMAND_ISSUED=PASS label=$choiceName"
$deadline=(Get-Date).AddSeconds(28)
while((Get-Date) -lt $deadline){
  Start-Sleep -Milliseconds 650
  $elements=$document.FindAll([System.Windows.Automation.TreeScope]::Descendants,
    [System.Windows.Automation.Condition]::TrueCondition)
  foreach($e in $elements){
    $name=[string]$e.Current.Name
    $type=[string]$e.Current.ControlType.ProgrammaticName
    if($name -eq 'Save As' -and $type -eq 'ControlType.Window'){
      Write-Host "XD_SAVE_STAGE_NATIVE_PICKER_OPEN=PASS hwnd=$($e.Current.NativeWindowHandle) pid=$($e.Current.ProcessId)"
      exit 0
    }
    if($name -match 'Save to|Cloud document|Local document'){
      Write-Host "XD_SAVE_STAGE_ALTERNATE_SAVE_UI=FOUND name=$name type=$type"
    }
  }
}
throw 'XD_SAVE_STAGE_PICKER_NOT_OBSERVED_DO_NOT_RESEND_SAVE'
