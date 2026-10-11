param(
    [string]$RunId = $env:GITHUB_RUN_ID
)
$ErrorActionPreference='Stop'
if($env:COMPUTERNAME -ne 'MRCAO'){throw 'XD_SAVE_WRONG_HOST'}
if([System.Diagnostics.Process]::GetCurrentProcess().SessionId -ne 1){throw 'XD_SAVE_WRONG_DESKTOP_SESSION'}
if($RunId -notmatch '^[0-9]{8,20}$'){throw 'XD_SAVE_INVALID_RUN_ID'}
$root=Join-Path $env:USERPROFILE 'Documents\MCPAdobe'
$checkpoint=Join-Path $root "MCP_Mode1_Panda_XD_$RunId.json"
$target=Join-Path $root "MCP_Mode1_Panda_XD_$RunId.xd"
if(-not (Test-Path -LiteralPath $checkpoint)){throw 'XD_SAVE_NO_PROVEN_MODE1_SCENEGRAPH_CHECKPOINT'}
if(Test-Path -LiteralPath $target){throw 'XD_SAVE_TARGET_ALREADY_EXISTS_NO_OVERWRITE'}
$data=Get-Content -LiteralPath $checkpoint -Raw | ConvertFrom-Json
$proof=@($data.proven)
if($proof.Count -ne 32){throw "XD_SAVE_NOT_32_APPLIED_OBJECTS count=$($proof.Count)"}
$unique=@($proof | Select-Object -ExpandProperty guid -Unique)
if($unique.Count -ne 32){throw 'XD_SAVE_GUIDS_NOT_UNIQUE'}
foreach($item in $proof){
    if($item.status -ne 'applied'){throw "XD_SAVE_UNAPPLIED_RECEIPT=$($item.ordinal)"}
}
Write-Host "XD_SAVE_SCENEGRAPH_CHECKPOINT_VERIFIED=PASS count=32 path=$checkpoint"
Add-Type -AssemblyName UIAutomationClient
Add-Type -AssemblyName UIAutomationTypes
Add-Type -AssemblyName System.Windows.Forms
Add-Type @'
using System;
using System.Runtime.InteropServices;
public static class XdNativeSaveWindow {
    [DllImport("user32.dll")] public static extern bool ShowWindow(IntPtr h, int n);
    [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr h);
}
'@
$xd=Get-Process -ErrorAction SilentlyContinue |
    Where-Object {($_.ProcessName -match '^(XD|AdobeXD)$' -or $_.MainWindowTitle -match 'Adobe XD') -and $_.MainWindowHandle -ne 0 -and $_.SessionId -eq 1 -and $_.MainWindowTitle -match '^Untitled.*Adobe XD$'} |
    Select-Object -First 1
if(-not $xd){throw 'XD_SAVE_LIVE_TEST_DOCUMENT_NOT_ACTIVE'}
[void][XdNativeSaveWindow]::ShowWindow($xd.MainWindowHandle,9)
if(-not [XdNativeSaveWindow]::SetForegroundWindow($xd.MainWindowHandle)){
    throw 'XD_SAVE_CANNOT_FOCUS_DOCUMENT'
}
Start-Sleep -Milliseconds 550
# Official Adobe XD Windows shortcut: Shift+Ctrl+Alt+S -> Save As Local Document.
# This is a single GUI action. Never loop/repeat a potentially accepted save.
[System.Windows.Forms.SendKeys]::SendWait('^%+s')
Write-Host "XD_SAVE_AS_LOCAL_REQUESTED=PASS pid=$($xd.Id) shortcut=Ctrl+Alt+Shift+S"
$windowRoot=[System.Windows.Automation.AutomationElement]::RootElement
$targetDialog=$null
$deadline=(Get-Date).AddSeconds(25)
do {
    Start-Sleep -Milliseconds 550
    $windowList=$windowRoot.FindAll(
        [System.Windows.Automation.TreeScope]::Children,
        [System.Windows.Automation.Condition]::TrueCondition
    )
    foreach($window in $windowList){
        $windowTitle=[string]$window.Current.Name
        if($windowTitle -match 'Save As|名前を付けて保存|ローカルドキュメント|Save.*Local'){
            $targetDialog=$window
            break
        }
    }
} until($targetDialog -or (Get-Date)-gt $deadline)
if(-not $targetDialog){
    foreach($window in $windowList){
        $name=[string]$window.Current.Name
        if($name){Write-Host "XD_SAVE_DISCOVERED_WINDOW=$name"}
    }
    throw 'XD_SAVE_AS_LOCAL_DIALOG_NOT_VERIFIED_NO_REPLAY'
}
Write-Host "XD_SAVE_DIALOG_FOUND=$($targetDialog.Current.Name)"
$editFilter=New-Object System.Windows.Automation.PropertyCondition(
    [System.Windows.Automation.AutomationElement]::ControlTypeProperty,
    [System.Windows.Automation.ControlType]::Edit
)
$edits=$targetDialog.FindAll([System.Windows.Automation.TreeScope]::Descendants,$editFilter)
$fileNameControl=$null
foreach($edit in $edits){
    $label=[string]$edit.Current.Name
    $automationId=[string]$edit.Current.AutomationId
    Write-Host "XD_SAVE_EDIT_CONTROL name=$label automationId=$automationId"
    if($automationId -match '^1001$|FileName' -or $label -match 'File name|ファイル名'){
        $fileNameControl=$edit
        break
    }
}
if(-not $fileNameControl){throw 'XD_SAVE_FILENAME_CONTROL_UNVERIFIED'}
$valuePattern=$fileNameControl.GetCurrentPattern([System.Windows.Automation.ValuePattern]::Pattern)
$valuePattern.SetValue($target)
Write-Host "XD_SAVE_FILENAME_SET=PASS target=$target"
$buttonFilter=New-Object System.Windows.Automation.PropertyCondition(
    [System.Windows.Automation.AutomationElement]::ControlTypeProperty,
    [System.Windows.Automation.ControlType]::Button
)
$buttons=$targetDialog.FindAll([System.Windows.Automation.TreeScope]::Descendants,$buttonFilter)
$saveButton=$null
foreach($button in $buttons){
    $name=[string]$button.Current.Name
    if($name -match '^Save|^保存'){
        $saveButton=$button
        break
    }
}
if(-not $saveButton){throw 'XD_SAVE_BUTTON_UNVERIFIED'}
$pattern=$saveButton.GetCurrentPattern([System.Windows.Automation.InvokePattern]::Pattern)
$pattern.Invoke()
Write-Host 'XD_SAVE_BUTTON_CLICKED=PASS'
$deadline=(Get-Date).AddSeconds(25)
do{Start-Sleep -Milliseconds 600}until((Test-Path -LiteralPath $target) -or (Get-Date)-gt $deadline)
if(-not (Test-Path -LiteralPath $target)){throw 'XD_NATIVE_XD_FILE_NOT_CREATED'}
$file=Get-Item -LiteralPath $target
if($file.Length -lt 1000){throw "XD_NATIVE_XD_FILE_TOO_SMALL bytes=$($file.Length)"}
$sha=(Get-FileHash -LiteralPath $target -Algorithm SHA256).Hash
Write-Host "XD_NATIVE_FILE_VERIFIED=PASS bytes=$($file.Length) sha256=$sha path=$target"
