# One-shot Adobe XD development-plugin reload on the user's isolated test document.
# No native document editing, service restart, existing plugin replacement, or blind retry.
$ErrorActionPreference='Stop'
if($env:COMPUTERNAME -ne 'MRCAO' -or [Diagnostics.Process]::GetCurrentProcess().SessionId -ne 1){throw 'MODE2_WRONG_HOST'}
$root=Join-Path $env:USERPROFILE 'Documents\MCPAdobe'
$expected='3A10E1510ABC41ECCD4485D6F852EA6CED7ACC2CF50109E7C1BD123353589ED1'
$native=@(
  (Join-Path $root 'MCP_Mode1_Panda_XD_38136531800.xd'),
  (Join-Path $root 'mode2-isolated\Panda_Mode2_Editable_Experiment.xd'),
  (Join-Path $root 'mode2-disposable-native\Mode2_Undo_E2E_38584984023.xd')
)
foreach($p in $native){if((Get-FileHash -LiteralPath $p -Algorithm SHA256).Hash -ne $expected){throw 'MODE2_NATIVE_HASH_PRECONDITION_FAILED'}}
$marker=Join-Path $root 'mode2-disposable-native\Mode2_Experimental_Reload_Once.marker'
if(Test-Path -LiteralPath $marker){throw 'MODE2_RELOAD_PREVIOUSLY_REQUESTED_NO_REPLAY'}
if(@(Get-Process -Name Illustrator,Photoshop,PickerHost -ErrorAction SilentlyContinue).Count -gt 0){throw 'MODE2_FOREIGN_APP_OR_MODAL'}
if(@(Get-NetTCPConnection -LocalPort 8766 -State Listen -ErrorAction SilentlyContinue).Count -ne 1){throw 'MODE2_8766_LISTENER_NOT_READY'}
if(@(Get-NetTCPConnection -LocalPort 8765 -State Established -ErrorAction SilentlyContinue).Count -lt 1){throw 'MODE2_PRODUCTION_BRIDGE_DISCONNECTED'}
Add-Type -AssemblyName UIAutomationClient
Add-Type -AssemblyName UIAutomationTypes
$rootUI=[System.Windows.Automation.AutomationElement]::RootElement
$desc=[System.Windows.Automation.TreeScope]::Descendants
$allCond=[System.Windows.Automation.Condition]::TrueCondition
$top=$rootUI.FindAll([System.Windows.Automation.TreeScope]::Children,$allCond)
$xd=@($top|Where-Object {[string]$_.Current.Name -match 'Adobe XD$'})
$test=@($xd|Where-Object {[string]$_.Current.Name -match '^Mode2_Undo_E2E_38584984023.*Adobe XD$'})
if($xd.Count -ne 1 -or $test.Count -ne 1){throw 'MODE2_NOT_SOLE_DISPOSABLE_WINDOW'}
$id=[System.Windows.Automation.AutomationElement]::AutomationIdProperty
function Find-Menu([string]$name){
  $match=$test[0].FindFirst($desc,(New-Object System.Windows.Automation.PropertyCondition($id,$name)))
  if(-not $match){throw "MODE2_MENU_ID_NOT_FOUND_$name"}
  return $match
}
# A clean document must not offer active Save.
$file=Find-Menu 'AppMenu_File'
$fx=$file.GetCurrentPattern([System.Windows.Automation.ExpandCollapsePattern]::Pattern)
$fx.Expand();Start-Sleep -Milliseconds 240
$items=$test[0].FindAll($desc,$allCond)
$activeSave=@($items|Where-Object {[string]$_.Current.Name -eq 'Save' -and $_.Current.IsEnabled})
$fx.Collapse()
Write-Host "MODE2_ACTIVE_SAVE_COUNT=$($activeSave.Count)"
if($activeSave.Count -ne 0){throw 'MODE2_UNSAVED_DOCUMENT_NO_RELOAD'}
$plugins=Find-Menu 'AppMenuBar_Plugins'
$px=$plugins.GetCurrentPattern([System.Windows.Automation.ExpandCollapsePattern]::Pattern)
$px.Expand();Start-Sleep -Milliseconds 220
$dev=Find-Menu 'PluginsMenu_Development'
$dx=$dev.GetCurrentPattern([System.Windows.Automation.ExpandCollapsePattern]::Pattern)
$dx.Expand();Start-Sleep -Milliseconds 220
$items=$test[0].FindAll($desc,$allCond)
$reload=@($items|Where-Object {
 [string]$_.Current.AutomationId -eq 'PluginsMenu_Development_Reload' -and
 [string]$_.Current.Name -eq 'Reload Plugins (Legacy)' -and $_.Current.IsEnabled
})
Write-Host "MODE2_RELOAD_EXACT_CONTROL_COUNT=$($reload.Count)"
if($reload.Count -ne 1){throw 'MODE2_RELOAD_CONTROL_NOT_UNIQUE'}
# Write before invocation so an uncertain result cannot be replayed.
"run=$env:GITHUB_RUN_ID requested=$([DateTime]::UtcNow.ToString('o'))" |
  Set-Content -LiteralPath $marker -Encoding ASCII -NoNewline
$reload[0].GetCurrentPattern([System.Windows.Automation.InvokePattern]::Pattern).Invoke()
Write-Host 'MODE2_RELOAD_UIA_INVOKED_ONCE'
foreach($p in $native){if((Get-FileHash -LiteralPath $p -Algorithm SHA256).Hash -ne $expected){throw 'MODE2_NATIVE_CHANGED_AFTER_RELOAD'}}
Write-Host 'MODE2_PROTECTED_NATIVE_AFTER_RELOAD=PASS'
