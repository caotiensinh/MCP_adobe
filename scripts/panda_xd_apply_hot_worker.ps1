# Persistent, single-owner UIAutomation worker for one verified XD Apply at a time.
# The Python caller must first prove an exact queued operation and then check its
# operation-specific receipt. An ambiguous Invoke is NEVER retried here.
$ErrorActionPreference='Stop'
if($env:COMPUTERNAME -ne 'MRCAO'){throw 'XD_HOT_WRONG_HOST'}
if([System.Diagnostics.Process]::GetCurrentProcess().SessionId -ne 1){throw 'XD_HOT_WRONG_SESSION'}
$sourceRun=[string]$env:PANDA_XD_SOURCE_RUN_ID
if($sourceRun -notmatch '^[0-9]{8,20}$'){throw 'XD_HOT_SOURCE_RUN_NOT_SPECIFIED'}
Add-Type -AssemblyName UIAutomationClient
Add-Type -AssemblyName UIAutomationTypes
Write-Output 'XD_HOT_READY'
[Console]::Out.Flush()
while($true){
    $line=[Console]::ReadLine()
    if($null -eq $line -or $line -eq 'STOP'){break}
    if($line -eq 'PING'){
        Write-Output 'XD_HOT_PONG'
        [Console]::Out.Flush()
        continue
    }
    if($line -ne 'APPLY'){
        Write-Output 'XD_HOT_ERROR:UNSUPPORTED_COMMAND'
        [Console]::Out.Flush()
        break
    }
    try{
        $root=[System.Windows.Automation.AutomationElement]::RootElement
        $windows=$root.FindAll([System.Windows.Automation.TreeScope]::Children,[System.Windows.Automation.Condition]::TrueCondition)
        $documents=@()
        foreach($w in $windows){
            if([string]$w.Current.Name -match "^MCP_Mode1_Panda_XD_$($sourceRun).*Adobe XD$" -and
               [string]$w.Current.ClassName -eq 'ApplicationFrameWindow'){$documents+=,$w}
        }
        if($documents.Count -ne 1){throw "DOCUMENT_NOT_UNIQUE count=$($documents.Count)"}
        $document=$documents[0]
        $condition=New-Object System.Windows.Automation.PropertyCondition(
          [System.Windows.Automation.AutomationElement]::AutomationIdProperty,'AppMenuBar_Plugins')
        $menu=$document.FindFirst([System.Windows.Automation.TreeScope]::Descendants,$condition)
        if(-not $menu -or -not $menu.Current.IsEnabled){throw 'PLUGINS_MENU_UNAVAILABLE'}
        $expand=$menu.GetCurrentPattern([System.Windows.Automation.ExpandCollapsePattern]::Pattern)
        if($expand.Current.ExpandCollapseState -ne [System.Windows.Automation.ExpandCollapseState]::Expanded){$expand.Expand()}
        Start-Sleep -Milliseconds 120
        $items=$document.FindAll([System.Windows.Automation.TreeScope]::Descendants,[System.Windows.Automation.Condition]::TrueCondition)
        $parents=@()
        foreach($n in $items){
            if([string]$n.Current.Name -ne 'MCP Adobe Bridge' -or
               [string]$n.Current.ControlType.ProgrammaticName -ne 'ControlType.MenuItem'){continue}
            try{
                [void]$n.GetCurrentPattern([System.Windows.Automation.ExpandCollapsePattern]::Pattern)
                $parents+=,$n
            }catch{}
        }
        if($parents.Count -ne 1){throw "BRIDGE_MENU_AMBIGUOUS count=$($parents.Count)"}
        $sub=$parents[0].GetCurrentPattern([System.Windows.Automation.ExpandCollapsePattern]::Pattern)
        if($sub.Current.ExpandCollapseState -ne [System.Windows.Automation.ExpandCollapseState]::Expanded){$sub.Expand()}
        Start-Sleep -Milliseconds 120
        $all=$document.FindAll([System.Windows.Automation.TreeScope]::Descendants,[System.Windows.Automation.Condition]::TrueCondition)
        $actions=@()
        foreach($n in $all){
            if([string]$n.Current.Name -eq 'MCP Adobe Apply' -and
              [string]$n.Current.ControlType.ProgrammaticName -eq 'ControlType.MenuItem' -and
              $n.Current.IsEnabled){$actions+=,$n}
        }
        if($actions.Count -ne 1){throw "APPLY_MENU_AMBIGUOUS count=$($actions.Count)"}
        $invoke=$actions[0].GetCurrentPattern([System.Windows.Automation.InvokePattern]::Pattern)
        $invoke.Invoke()
        Write-Output 'XD_HOT_APPLIED:ONCE'
        [Console]::Out.Flush()
    }catch{
        # A UIA exception can happen AFTER Invoke; the caller must inspect the
        # operation receipt and scenegraph, not send another request.
        $message=([string]$_.Exception.Message -replace '[\r\n\t]',' ')
        Write-Output "XD_HOT_UNKNOWN:$($message.Substring(0,[Math]::Min(300,$message.Length)))"
        [Console]::Out.Flush()
        break
    }
}
