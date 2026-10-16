$ErrorActionPreference='Stop'
if($env:COMPUTERNAME -ne 'MRCAO'){throw 'XD_UIA_CONNECT_WRONG_HOST'}
if([System.Diagnostics.Process]::GetCurrentProcess().SessionId -ne 1){throw 'XD_UIA_CONNECT_WRONG_SESSION'}
$src=Join-Path $env:USERPROFILE 'Documents\MCPAdobe\MCP_Mode1_Panda_XD_38136531800.xd'
$sha='3A10E1510ABC41ECCD4485D6F852EA6CED7ACC2CF50109E7C1BD123353589ED1'
if(-not(Test-Path -LiteralPath $src -PathType Leaf) -or (Get-FileHash -LiteralPath $src -Algorithm SHA256).Hash -ne $sha){throw 'XD_UIA_CONNECT_NATIVE_SHA_CHANGED'}
# Multiple installed self-hosted runner services do not by themselves
# imply competing GUI owners. The workflow desktop concurrency group and
# exact Adobe document/process/queue checks are the actual safety gates.
$workers=@(Get-CimInstance Win32_Process -Filter "Name='Runner.Worker.exe'" -ErrorAction SilentlyContinue)
Write-Host "XD_UIA_CONNECT_RUNNER_WORKERS_OBSERVED=$($workers.Count) informational-only"
$live=@(Get-NetTCPConnection -LocalPort 8765 -State Established -ErrorAction SilentlyContinue)
if($live.Count -gt 0){
  Write-Host "XD_UIA_CONNECT_ALREADY_ESTABLISHED=PASS count=$($live.Count) no-duplicate-connect"
  exit 0
}
Add-Type -AssemblyName UIAutomationClient
Add-Type -AssemblyName UIAutomationTypes
$root=[System.Windows.Automation.AutomationElement]::RootElement
$windows=$root.FindAll([System.Windows.Automation.TreeScope]::Children,[System.Windows.Automation.Condition]::TrueCondition)
$documents=@()
foreach($w in $windows){
  if([string]$w.Current.Name -match '^MCP_Mode1_Panda_XD_38136531800.*Adobe XD$' -and
     [string]$w.Current.ClassName -eq 'ApplicationFrameWindow'){$documents+=,$w}
}
if($documents.Count -ne 1){throw "XD_UIA_CONNECT_DOCUMENT_AMBIGUOUS count=$($documents.Count)"}
$document=$documents[0]
$condition=New-Object System.Windows.Automation.PropertyCondition(
  [System.Windows.Automation.AutomationElement]::AutomationIdProperty,'AppMenuBar_Plugins')
$menu=$document.FindFirst([System.Windows.Automation.TreeScope]::Descendants,$condition)
if(-not $menu -or -not $menu.Current.IsEnabled){throw 'XD_UIA_CONNECT_PLUGINS_MENU_UNAVAILABLE'}
$exp=$menu.GetCurrentPattern([System.Windows.Automation.ExpandCollapsePattern]::Pattern)
if($exp.Current.ExpandCollapseState -ne [System.Windows.Automation.ExpandCollapseState]::Expanded){$exp.Expand()}
Start-Sleep -Milliseconds 180
$items=$document.FindAll([System.Windows.Automation.TreeScope]::Descendants,[System.Windows.Automation.Condition]::TrueCondition)
$parents=@()
foreach($n in $items){
  if([string]$n.Current.Name -ne 'MCP Adobe Bridge' -or
    [string]$n.Current.ControlType.ProgrammaticName -ne 'ControlType.MenuItem'){continue}
  try{[void]$n.GetCurrentPattern([System.Windows.Automation.ExpandCollapsePattern]::Pattern);$parents+=,$n}catch{}
}
if($parents.Count -ne 1){throw "XD_UIA_CONNECT_PLUGIN_MENU_AMBIGUOUS count=$($parents.Count)"}
$submenu=$parents[0].GetCurrentPattern([System.Windows.Automation.ExpandCollapsePattern]::Pattern)
if($submenu.Current.ExpandCollapseState -ne [System.Windows.Automation.ExpandCollapseState]::Expanded){$submenu.Expand()}
Start-Sleep -Milliseconds 180
$all=$document.FindAll([System.Windows.Automation.TreeScope]::Descendants,[System.Windows.Automation.Condition]::TrueCondition)
$matches=@()
foreach($n in $all){
  if([string]$n.Current.Name -eq 'MCP Adobe Connect' -and
     [string]$n.Current.ControlType.ProgrammaticName -eq 'ControlType.MenuItem' -and
     $n.Current.IsEnabled){$matches+=,$n}
}
if($matches.Count -ne 1){throw "XD_UIA_CONNECT_ACTION_AMBIGUOUS count=$($matches.Count)"}
$action=$matches[0].GetCurrentPattern([System.Windows.Automation.InvokePattern]::Pattern)
try{$action.Invoke();Write-Host 'XD_UIA_CONNECT_PLUGIN_COMMAND_INVOKED=ONCE'}catch{
  throw "XD_UIA_CONNECT_ACTION_UNKNOWN_NO_REPLAY $($_.Exception.Message)"
}
$deadline=(Get-Date).AddSeconds(20)
do{
  Start-Sleep -Milliseconds 500
  $connected=@(Get-NetTCPConnection -LocalPort 8765 -State Established -ErrorAction SilentlyContinue)
}until($connected.Count -gt 0 -or (Get-Date) -gt $deadline)
if($connected.Count -eq 0){throw 'XD_UIA_CONNECT_NO_WS_AFTER_ONE_COMMAND'}
Write-Host 'XD_UIA_CONNECT_WS_ESTABLISHED=PASS'
