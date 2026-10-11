param([string]$RunId='38132321143')
$ErrorActionPreference='Stop'
if($env:COMPUTERNAME -ne 'MRCAO'){throw 'XD_MENU_SAVE_NOT_MRCAO'}
if([System.Diagnostics.Process]::GetCurrentProcess().SessionId -ne 1){throw 'XD_MENU_SAVE_NOT_DESKTOP_1'}
if($RunId -notmatch '^[0-9]{8,20}$'){throw 'XD_MENU_SAVE_INVALID_RUN_ID'}
$root=Join-Path $env:USERPROFILE 'Documents\MCPAdobe'
$target=Join-Path $root "MCP_Mode1_Panda_XD_$RunId.xd"
if(Test-Path -LiteralPath $target){throw 'XD_MENU_SAVE_TARGET_EXISTS_NO_OVERWRITE'}
Add-Type -AssemblyName UIAutomationClient
Add-Type -AssemblyName UIAutomationTypes

$windows=@(Get-Process -ErrorAction SilentlyContinue | Where-Object {
  $_.SessionId -eq 1 -and $_.MainWindowHandle -ne 0 -and
  $_.MainWindowTitle -match '^Untitled.*Adobe XD$'
})
if($windows.Count -ne 1){
  foreach($w in $windows){Write-Host "XD_MENU_SAVE_CANDIDATE pid=$($w.Id) title=$($w.MainWindowTitle)"}
  throw "XD_MENU_SAVE_TEST_WINDOW_AMBIGUOUS count=$($windows.Count)"
}
$xd=$windows[0]
Write-Host "XD_MENU_SAVE_TEST_DOCUMENT=PASS pid=$($xd.Id) title=$($xd.MainWindowTitle)"

function Controls([System.Windows.Automation.AutomationElement]$container){
  if($null -eq $container){return @()}
  return @($container.FindAll([System.Windows.Automation.TreeScope]::Descendants,
                              [System.Windows.Automation.Condition]::TrueCondition))
}
function NamedMatches($elements,[string]$regex){
  $out=@()
  foreach($element in $elements){
    try{
      $name=[string]$element.Current.Name
      $id=[string]$element.Current.AutomationId
      if($name -match $regex -or $id -match $regex){$out+=,$element}
    }catch{}
  }
  return $out
}
function TraceRelevant($elements,[string]$prefix){
  $i=0
  foreach($element in $elements){
    try{
      $name=[string]$element.Current.Name
      $id=[string]$element.Current.AutomationId
      if($name -match 'Save|Local|File|保存|ローカル|キャンセル|Cancel|Name|名前' -or
         $id -match 'Save|Local|File|Dialog|Name'){
        Write-Host "$prefix ordinal=$i name=$name id=$id type=$($element.Current.ControlType.ProgrammaticName) class=$($element.Current.ClassName)"
      }
    }catch{}
    $i++
  }
}
$app=[System.Windows.Automation.AutomationElement]::FromHandle($xd.MainWindowHandle)
$children=Controls $app
$menus=@($children | Where-Object {$_.Current.AutomationId -eq 'AppMenu_File'})
if($menus.Count -ne 1){throw "XD_MENU_SAVE_FILE_MENU_NOT_UNIQUE count=$($menus.Count)"}
$fileMenu=$menus[0]
try{
  $exp=$fileMenu.GetCurrentPattern([System.Windows.Automation.ExpandCollapsePattern]::Pattern)
  $exp.Expand()
  Write-Host 'XD_MENU_SAVE_FILE_EXPANDED=PASS via=ExpandCollapse'
}catch{
  try{
    $invoke=$fileMenu.GetCurrentPattern([System.Windows.Automation.InvokePattern]::Pattern)
    $invoke.Invoke()
    Write-Host 'XD_MENU_SAVE_FILE_EXPANDED=PASS via=Invoke'
  }catch{
    $legacy=$fileMenu.GetCurrentPattern([System.Windows.Automation.LegacyIAccessiblePattern]::Pattern)
    $legacy.DoDefaultAction()
    Write-Host 'XD_MENU_SAVE_FILE_EXPANDED=PASS via=LegacyAction'
  }
}
$rootElement=[System.Windows.Automation.AutomationElement]::RootElement
$menuItem=$null
$deadline=(Get-Date).AddSeconds(12)
do{
  Start-Sleep -Milliseconds 550
  $children=Controls $app
  $fromRoot=Controls $rootElement
  $matching=@(NamedMatches $children 'Save As Local Document|Save.*Local Document|ローカルドキュメントとして保存')
  if($matching.Count -eq 0){$matching=@(NamedMatches $fromRoot 'Save As Local Document|Save.*Local Document|ローカルドキュメントとして保存')}
  if($matching.Count -gt 0){$menuItem=$matching[0]}
}until($menuItem -or (Get-Date) -ge $deadline)
if(-not $menuItem){
  TraceRelevant $children 'XD_MENU_SAVE_APP_CONTROL'
  TraceRelevant $fromRoot 'XD_MENU_SAVE_ROOT_CONTROL'
  throw 'XD_MENU_SAVE_LOCAL_DOCUMENT_MENU_NOT_FOUND_NO_SAVE_SENT'
}
Write-Host "XD_MENU_SAVE_LOCAL_COMMAND_FOUND=PASS title=$($menuItem.Current.Name)"
try{
  $invoke=$menuItem.GetCurrentPattern([System.Windows.Automation.InvokePattern]::Pattern)
  $invoke.Invoke()
}catch{
  try{
    $legacy=$menuItem.GetCurrentPattern([System.Windows.Automation.LegacyIAccessiblePattern]::Pattern)
    $legacy.DoDefaultAction()
  }catch{
    throw 'XD_MENU_SAVE_LOCAL_COMMAND_NOT_INVOKABLE'
  }
}
Write-Host 'XD_MENU_SAVE_LOCAL_CLICKED=PASS_NO_REPLAY'

$dialog=$null
$deadline=(Get-Date).AddSeconds(30)
do{
  Start-Sleep -Milliseconds 700
  $top=@($rootElement.FindAll([System.Windows.Automation.TreeScope]::Children,
                             [System.Windows.Automation.Condition]::TrueCondition))
  foreach($candidate in $top){
    $title=[string]$candidate.Current.Name
    $class=[string]$candidate.Current.ClassName
    if($class -eq '#32770' -or $title -match 'Save As|名前を付けて保存|Save.*Local'){
      $dialog=$candidate;break
    }
  }
}until($dialog -or (Get-Date) -ge $deadline)
if(-not $dialog){
  $controls=Controls $app
  TraceRelevant $controls 'XD_MENU_SAVE_AFTER_COMMAND'
  TraceRelevant (Controls $rootElement) 'XD_MENU_SAVE_AFTER_COMMAND_ROOT'
  throw 'XD_MENU_SAVE_DIALOG_NOT_SEPARATE_TOP_LEVEL_INSPECT_UIA'
}
Write-Host "XD_MENU_SAVE_NATIVE_DIALOG=PASS title=$($dialog.Current.Name)"
$desc=Controls $dialog
$filename=@(NamedMatches $desc '^File name:|^File name$|^ファイル名$|^1001$|FileName')
$edit=$null
foreach($candidate in $filename){
  if($candidate.Current.ControlType.ProgrammaticName -eq 'ControlType.Edit'){
    $edit=$candidate;break
  }
}
if(-not $edit){TraceRelevant $desc 'XD_MENU_SAVE_DIALOG';throw 'XD_MENU_SAVE_FILENAME_EDIT_UNAVAILABLE'}
$value=$edit.GetCurrentPattern([System.Windows.Automation.ValuePattern]::Pattern)
$value.SetValue($target)
Write-Host "XD_MENU_SAVE_FILENAME=PASS target=$target"
$buttons=@(NamedMatches $desc '^Save$|^保存$|^1$')
$saveButton=$null
foreach($button in $buttons){
 if($button.Current.ControlType.ProgrammaticName -eq 'ControlType.Button'){$saveButton=$button;break}
}
if(-not $saveButton){throw 'XD_MENU_SAVE_BUTTON_MISSING'}
$saveButton.GetCurrentPattern([System.Windows.Automation.InvokePattern]::Pattern).Invoke()
Write-Host 'XD_MENU_SAVE_NATIVE_SAVE_CLICKED=PASS'
$deadline=(Get-Date).AddSeconds(30)
do{Start-Sleep -Milliseconds 600}until((Test-Path -LiteralPath $target) -or (Get-Date) -ge $deadline)
if(-not (Test-Path -LiteralPath $target)){throw 'XD_MENU_SAVE_NATIVE_FILE_NOT_CREATED'}
$f=Get-Item -LiteralPath $target
if($f.Length -lt 1000){throw 'XD_MENU_SAVE_NATIVE_FILE_INVALID'}
$sha=(Get-FileHash -LiteralPath $target -Algorithm SHA256).Hash
Write-Host "XD_MENU_SAVE_ORIGINAL_VERIFIED=PASS path=$target bytes=$($f.Length) sha256=$sha"
