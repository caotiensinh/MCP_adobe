param(
  [Parameter(Mandatory=$true)]
  [ValidateSet('Connect','Undo')]
  [string]$Action
)
$ErrorActionPreference='Stop'
if($env:COMPUTERNAME -ne 'MRCAO' -or [Diagnostics.Process]::GetCurrentProcess().SessionId -ne 1){
  throw 'MODE2_UNDO_WRONG_WINDOWS_DESKTOP'
}
$root=Join-Path $env:USERPROFILE 'Documents\MCPAdobe'
$baseline='3A10E1510ABC41ECCD4485D6F852EA6CED7ACC2CF50109E7C1BD123353589ED1'
$saved='1E15162107A64E3D7D4CAF8C12B88FE24B64488DA9788854E6D300DDBAE88C2F'
foreach($rel in @('MCP_Mode1_Panda_XD_38136531800.xd','mode2-isolated\Panda_Mode2_Editable_Experiment.xd')){
  if((Get-FileHash -LiteralPath (Join-Path $root $rel) -Algorithm SHA256).Hash -ne $baseline){
    throw 'MODE2_UNDO_PROTECTED_PANDA_CHANGED'
  }
}
$native=Join-Path $root 'mode2-disposable-native\Mode2_Undo_E2E_38584984023.xd'
if((Get-FileHash -LiteralPath $native -Algorithm SHA256).Hash -ne $saved){
  throw 'MODE2_UNDO_DISPOSABLE_SAVED_DISK_CHANGED'
}
if(@(Get-Process -Name Illustrator,Photoshop,PickerHost -ErrorAction SilentlyContinue).Count -gt 0){
  throw 'MODE2_UNDO_OTHER_ADOBE_APP_OR_MODAL'
}
Add-Type -AssemblyName UIAutomationClient
Add-Type -AssemblyName UIAutomationTypes
Add-Type -TypeDefinition 'using System; using System.Runtime.InteropServices; public static class Mode2FillUndoForeground { [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr h); }'
$scope=[System.Windows.Automation.TreeScope]::Children
$desc=[System.Windows.Automation.TreeScope]::Descendants
$cond=[System.Windows.Automation.Condition]::TrueCondition
$aid=[System.Windows.Automation.AutomationElement]::AutomationIdProperty
function XDWindow {
  $all=[System.Windows.Automation.AutomationElement]::RootElement.FindAll($scope,$cond)
  $xd=@($all|Where-Object {[string]$_.Current.Name -match 'Adobe XD$'})
  $test=@($xd|Where-Object {[string]$_.Current.Name -match '^Mode2_Undo_E2E_38584984023.*Adobe XD$'})
  if($xd.Count -ne 1 -or $test.Count -ne 1){throw 'MODE2_UNDO_FOREIGN_OR_AMBIGUOUS_WINDOW'}
  return $test[0]
}
$win=XDWindow
$wp=$win.GetCurrentPattern([System.Windows.Automation.WindowPattern]::Pattern)
if($wp.Current.WindowVisualState -eq [System.Windows.Automation.WindowVisualState]::Minimized){
  $wp.SetWindowVisualState([System.Windows.Automation.WindowVisualState]::Normal)
}
try{$win.SetFocus()}catch{}
[void][Mode2FillUndoForeground]::SetForegroundWindow([IntPtr]$win.Current.NativeWindowHandle)
Start-Sleep -Milliseconds 500
if($Action -eq 'Connect'){
  if(@(Get-NetTCPConnection -LocalPort 8766 -State Listen -ErrorAction SilentlyContinue).Count -ne 1){
    throw 'MODE2_UNDO_EXPERIMENTAL_BRIDGE_LISTENER_NOT_UNIQUE'
  }
  $plugins=$win.FindFirst($desc,(New-Object System.Windows.Automation.PropertyCondition($aid,'AppMenuBar_Plugins')))
  if(-not $plugins){throw 'MODE2_UNDO_PLUGIN_MENU_MISSING'}
  $px=$plugins.GetCurrentPattern([System.Windows.Automation.ExpandCollapsePattern]::Pattern)
  if($px.Current.ExpandCollapseState -ne [System.Windows.Automation.ExpandCollapseState]::Expanded){$px.Expand()}
  Start-Sleep -Milliseconds 230
  $nodes=$win.FindAll($desc,$cond)
  $exp=@($nodes|Where-Object{
    [string]$_.Current.Name -eq 'MCP Adobe Mode 2 Experimental' -and
    [string]$_.Current.ControlType.ProgrammaticName -eq 'ControlType.MenuItem'
  })
  if($exp.Count -ne 1){throw 'MODE2_UNDO_EXPERIMENTAL_MENU_NOT_UNIQUE'}
  $ep=$exp[0].GetCurrentPattern([System.Windows.Automation.ExpandCollapsePattern]::Pattern)
  if($ep.Current.ExpandCollapseState -ne [System.Windows.Automation.ExpandCollapseState]::Expanded){$ep.Expand()}
  Start-Sleep -Milliseconds 230
  $items=$win.FindAll($desc,$cond)
  $connect=@($items|Where-Object{
    [string]$_.Current.Name -eq 'MCP Adobe Mode 2 Connect' -and
    [string]$_.Current.ControlType.ProgrammaticName -eq 'ControlType.MenuItem' -and $_.Current.IsEnabled
  })
  if($connect.Count -ne 1){throw 'MODE2_UNDO_CONNECT_NOT_EXACT'}
  $connect[0].GetCurrentPattern([System.Windows.Automation.InvokePattern]::Pattern).Invoke()
  Write-Host 'MODE2_UNDO_EXPERIMENTAL_CONNECT_INVOKED_ONCE'
  return
}
$receipt=Join-Path $root 'mode2-disposable-native\mode2_exact_guid_fill_mutation_receipt.json'
$undoReceipt=Join-Path $root 'mode2-disposable-native\mode2_exact_guid_fill_undo_receipt.json'
$marker=Join-Path $root 'mode2-disposable-native\Mode2_GUID_Fill_Undo_Once.marker'
if(!(Test-Path -LiteralPath $undoReceipt) -or (Test-Path -LiteralPath $marker)){
  throw 'MODE2_UNDO_INTENT_MISSING_OR_ALREADY_ATTEMPTED'
}
$r=Get-Content -LiteralPath $receipt -Raw -Encoding UTF8|ConvertFrom-Json
$u=Get-Content -LiteralPath $undoReceipt -Raw -Encoding UTF8|ConvertFrom-Json
if($r.state -ne 'applied_verified' -or $u.state -ne 'intent' -or
  $r.operation_id -ne $u.operation_id -or
  $r.node_id -ne '9989e92f-7c9b-4721-9cdc-b5b5ea33cdf2' -or
  $u.node_id -ne $r.node_id -or $r.fill_requested -ne '#A1B2C3' -or $r.fill_before -ne '#445566'){
  throw 'MODE2_UNDO_RECEIPTS_NOT_MATCHING_EXACT_FILL_OPERATION'
}
$file=$win.FindFirst($desc,(New-Object System.Windows.Automation.PropertyCondition($aid,'AppMenu_File')))
if(-not $file){throw 'MODE2_UNDO_FILE_MENU_MISSING'}
$fx=$file.GetCurrentPattern([System.Windows.Automation.ExpandCollapsePattern]::Pattern)
if($fx.Current.ExpandCollapseState -ne [System.Windows.Automation.ExpandCollapseState]::Expanded){$fx.Expand()}
Start-Sleep -Milliseconds 240
$saves=@($win.FindAll($desc,$cond)|Where-Object{
  [string]$_.Current.AutomationId -eq 'AppMenu_Save' -and
  [string]$_.Current.ControlType.ProgrammaticName -eq 'ControlType.MenuItem'
})
$fx.Collapse()
if($saves.Count -ne 1 -or -not $saves[0].Current.IsEnabled){
  throw 'MODE2_UNDO_DOCUMENT_NOT_DIRTY_AFTER_EXACT_FILL'
}
$edit=$win.FindFirst($desc,(New-Object System.Windows.Automation.PropertyCondition($aid,'AppMenu_Edit')))
if(-not $edit){throw 'MODE2_UNDO_EDIT_MENU_MISSING'}
$xp=$edit.GetCurrentPattern([System.Windows.Automation.ExpandCollapsePattern]::Pattern)
if($xp.Current.ExpandCollapseState -ne [System.Windows.Automation.ExpandCollapseState]::Expanded){$xp.Expand()}
Start-Sleep -Milliseconds 250
$items=$win.FindAll($desc,$cond)
$undos=@($items|Where-Object{
  [string]$_.Current.AutomationId -eq 'edit.undo' -and
  [string]$_.Current.ControlType.ProgrammaticName -eq 'ControlType.MenuItem' -and $_.Current.IsEnabled
})
if($undos.Count -ne 1){throw "MODE2_NATIVE_UNDO_NOT_UNIQUE_COUNT=$($undos.Count)"}
"run=$env:GITHUB_RUN_ID op=$($r.operation_id) at=$([DateTime]::UtcNow.ToString('o'))"|
  Set-Content -LiteralPath $marker -Encoding ASCII -NoNewline
$undos[0].GetCurrentPattern([System.Windows.Automation.InvokePattern]::Pattern).Invoke()
Write-Host 'MODE2_EXACT_NATIVE_UNDO_MENU_INVOKED_ONCE'
