# One explicit UXP Apply through UIA, on the exact persisted red XD document only.
# Caller must prove exactly one queued operation immediately before invoking.
$ErrorActionPreference='Stop'
if($env:COMPUTERNAME -ne 'MRCAO' -or [Diagnostics.Process]::GetCurrentProcess().SessionId -ne 1){
  throw 'XD_RED_BG_GUI_WRONG_HOST_OR_SESSION'
}
$root=Join-Path $env:USERPROFILE 'Documents\MCPAdobe'
$checkpoint=Join-Path $root 'MCP_KFP4_Red_XD_38205166138_first_bg.json'
if(-not(Test-Path -LiteralPath $checkpoint -PathType Leaf)){throw 'XD_RED_BG_GUI_CHECKPOINT_MISSING'}
$data=Get-Content -LiteralPath $checkpoint -Raw -Encoding UTF8|ConvertFrom-Json
if($data.phase -ne 'queued' -or [string]::IsNullOrWhiteSpace([string]$data.operation_id) -or
   $data.document_id -ne '304d4d00-6fba-47c0-b67a-d0e8ecf30254' -or
   $data.artboard_id -ne 'b195fab0-c97f-46be-8139-5d30a6149e37'){
  throw 'XD_RED_BG_GUI_CHECKPOINT_NOT_MATCHING'
}
foreach($pair in @(
  @('MCP_Mode1_Panda_XD_38136531800.xd','3A10E1510ABC41ECCD4485D6F852EA6CED7ACC2CF50109E7C1BD123353589ED1'),
  @('MCP_KFP4_Red_XD_38205166138.xd','58966788CF369885C2395CE217D6E0443ED57BCD7F40BD550B2F3A24C2B5B831'))) {
  if((Get-FileHash -LiteralPath (Join-Path $root $pair[0]) -Algorithm SHA256).Hash -ne $pair[1]){
    throw 'XD_RED_BG_GUI_PROTECTED_NATIVE_CHANGED'
  }
}
$pickers=@(Get-Process -Name PickerHost -ErrorAction SilentlyContinue|Where-Object{$_.SessionId -eq 1})
$connected=@(Get-NetTCPConnection -LocalPort 8765 -State Established -ErrorAction SilentlyContinue)
if($pickers.Count -ne 0 -or $connected.Count -lt 1){throw 'XD_RED_BG_GUI_DIALOG_OR_BRIDGE_NOT_SAFE'}
Add-Type -AssemblyName UIAutomationClient
Add-Type -AssemblyName UIAutomationTypes
$desktop=[System.Windows.Automation.AutomationElement]::RootElement
$windows=$desktop.FindAll([System.Windows.Automation.TreeScope]::Children,[System.Windows.Automation.Condition]::TrueCondition)
$red=@($windows|Where-Object{[string]$_.Current.Name -match '^MCP_KFP4_Red_XD_38205166138.*Adobe XD$' -and
    [string]$_.Current.ClassName -eq 'ApplicationFrameWindow'})
$other=@($windows|Where-Object{[string]$_.Current.Name -match '^MCP_Mode1_Panda_XD_38136531800.*Adobe XD$|^Untitled.*Adobe XD$'})
if($red.Count -ne 1 -or $other.Count -ne 0){throw 'XD_RED_BG_GUI_WRONG_OR_MULTIPLE_DOCUMENTS'}
$children=$red[0].FindAll([System.Windows.Automation.TreeScope]::Children,[System.Windows.Automation.Condition]::TrueCondition)
$core=@($children|Where-Object{[string]$_.Current.ClassName -eq 'Windows.UI.Core.CoreWindow'})
if($core.Count -ne 1){throw 'XD_RED_BG_GUI_CORE_NOT_UNIQUE'}
$cond=New-Object System.Windows.Automation.PropertyCondition(
  [System.Windows.Automation.AutomationElement]::AutomationIdProperty,'AppMenuBar_Plugins')
$pluginMenus=$core[0].FindAll([System.Windows.Automation.TreeScope]::Descendants,$cond)
if($pluginMenus.Count -ne 1 -or -not $pluginMenus[0].Current.IsEnabled){throw 'XD_RED_BG_GUI_PLUGINS_NOT_READY'}
$exp=$pluginMenus[0].GetCurrentPattern([System.Windows.Automation.ExpandCollapsePattern]::Pattern)
if($exp.Current.ExpandCollapseState -ne [System.Windows.Automation.ExpandCollapseState]::Expanded){$exp.Expand()}
Start-Sleep -Milliseconds 170
$items=$red[0].FindAll([System.Windows.Automation.TreeScope]::Descendants,[System.Windows.Automation.Condition]::TrueCondition)
$bridge=@()
foreach($node in $items){
  if([string]$node.Current.Name -ne 'MCP Adobe Bridge' -or $node.Current.ControlType.ProgrammaticName -ne 'ControlType.MenuItem'){continue}
  try{[void]$node.GetCurrentPattern([System.Windows.Automation.ExpandCollapsePattern]::Pattern);$bridge+=,$node}catch{}
}
if($bridge.Count -ne 1){throw 'XD_RED_BG_GUI_BRIDGE_MENU_NOT_UNIQUE'}
$sub=$bridge[0].GetCurrentPattern([System.Windows.Automation.ExpandCollapsePattern]::Pattern)
if($sub.Current.ExpandCollapseState -ne [System.Windows.Automation.ExpandCollapseState]::Expanded){$sub.Expand()}
Start-Sleep -Milliseconds 180
$all=$red[0].FindAll([System.Windows.Automation.TreeScope]::Descendants,[System.Windows.Automation.Condition]::TrueCondition)
$apply=@($all|Where-Object{[string]$_.Current.Name -eq 'MCP Adobe Apply' -and
    $_.Current.ControlType.ProgrammaticName -eq 'ControlType.MenuItem' -and $_.Current.IsEnabled})
if($apply.Count -ne 1){throw 'XD_RED_BG_GUI_APPLY_NOT_UNIQUE'}
if((Get-Content -LiteralPath $checkpoint -Raw -Encoding UTF8|ConvertFrom-Json).phase -ne 'queued'){
  throw 'XD_RED_BG_GUI_CHECKPOINT_CHANGED_PRE_INVOKE'
}
Write-Host "XD_RED_BG_GUI_ONE_APPLY_READY=PASS operation=$($data.operation_id)"
try{
  $invoke=$apply[0].GetCurrentPattern([System.Windows.Automation.InvokePattern]::Pattern)
  $invoke.Invoke()
  Write-Host 'XD_RED_BG_GUI_APPLY_MENU_INVOKED=ONCE_NOT_YET_RECEIPT_VERIFIED'
}catch{
  throw "XD_RED_BG_GUI_APPLY_OUTCOME_UNKNOWN_NO_REPLAY $($_.Exception.GetType().Name)"
}
# Only the Python readback phase may prove applied, never this UIA call.
