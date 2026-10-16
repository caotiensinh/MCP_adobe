$ErrorActionPreference='Stop'
if($env:COMPUTERNAME -ne 'MRCAO' -or [Diagnostics.Process]::GetCurrentProcess().SessionId -ne 1){throw 'MODE2_APPLY_WRONG_HOST'}
Add-Type -AssemblyName UIAutomationClient
Add-Type -AssemblyName UIAutomationTypes
$top=[System.Windows.Automation.AutomationElement]::RootElement.FindAll([System.Windows.Automation.TreeScope]::Children,[System.Windows.Automation.Condition]::TrueCondition)
$xd=@($top|Where-Object {[string]$_.Current.Name -match 'Adobe XD$'})
$test=@($xd|Where-Object {[string]$_.Current.Name -match '^Mode2_Undo_E2E_38584984023.*Adobe XD$'})
if($xd.Count -ne 1 -or $test.Count -ne 1){throw 'MODE2_APPLY_NOT_SOLE_TEST_WINDOW'}
$window=$test[0]
$id=[System.Windows.Automation.AutomationElement]::AutomationIdProperty
$menu=$window.FindFirst([System.Windows.Automation.TreeScope]::Descendants,
 (New-Object System.Windows.Automation.PropertyCondition($id,'AppMenuBar_Plugins')))
if(-not $menu -or -not $menu.Current.IsEnabled){throw 'MODE2_APPLY_PLUGINS_MENU_MISSING'}
$mp=$menu.GetCurrentPattern([System.Windows.Automation.ExpandCollapsePattern]::Pattern)
if($mp.Current.ExpandCollapseState -ne [System.Windows.Automation.ExpandCollapseState]::Expanded){$mp.Expand()}
Start-Sleep -Milliseconds 230
$nodes=$window.FindAll([System.Windows.Automation.TreeScope]::Descendants,[System.Windows.Automation.Condition]::TrueCondition)
$subs=@($nodes|Where-Object {[string]$_.Current.Name -eq 'MCP Adobe Bridge' -and [string]$_.Current.ControlType.ProgrammaticName -eq 'ControlType.MenuItem'})
if($subs.Count -ne 1){throw 'MODE2_APPLY_BRIDGE_MENU_NOT_UNIQUE'}
$sp=$subs[0].GetCurrentPattern([System.Windows.Automation.ExpandCollapsePattern]::Pattern)
if($sp.Current.ExpandCollapseState -ne [System.Windows.Automation.ExpandCollapseState]::Expanded){$sp.Expand()}
Start-Sleep -Milliseconds 230
$items=$window.FindAll([System.Windows.Automation.TreeScope]::Descendants,[System.Windows.Automation.Condition]::TrueCondition)
$apply=@($items|Where-Object {[string]$_.Current.Name -eq 'MCP Adobe Apply' -and [string]$_.Current.ControlType.ProgrammaticName -eq 'ControlType.MenuItem' -and $_.Current.IsEnabled})
if($apply.Count -ne 1){throw 'MODE2_APPLY_COMMAND_NOT_UNIQUE'}
$pattern=$apply[0].GetCurrentPattern([System.Windows.Automation.InvokePattern]::Pattern)
$pattern.Invoke()
Write-Host 'MODE2_DISPOSABLE_APPLY_INVOKED_ONCE'
