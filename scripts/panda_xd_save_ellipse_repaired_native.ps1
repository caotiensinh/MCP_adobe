param([string]$SourceRunId="38136531800")
$ErrorActionPreference='Stop'
if($env:COMPUTERNAME -ne 'MRCAO'){throw 'XD_FINAL_SAVE_WRONG_HOST'}
if([System.Diagnostics.Process]::GetCurrentProcess().SessionId -ne 1){throw 'XD_FINAL_SAVE_WRONG_SESSION'}
if($SourceRunId -ne "38136531800"){throw 'XD_FINAL_SAVE_WRONG_SOURCE_ID'}
$folder=Join-Path $env:USERPROFILE 'Documents\MCPAdobe'
$target=Join-Path $folder "MCP_Mode1_Panda_XD_$SourceRunId.xd"
$checkpoint=Join-Path $folder "MCP_Mode1_Panda_XD_$($SourceRunId)_ellipse_repair.json"
if(-not (Test-Path -LiteralPath $target -PathType Leaf) -or
   -not (Test-Path -LiteralPath $checkpoint -PathType Leaf)){
  throw 'XD_FINAL_SAVE_SOURCE_OR_CHECKPOINT_MISSING'
}
$data=Get-Content -LiteralPath $checkpoint -Raw | ConvertFrom-Json
$proven=@($data.proven)
$proven=@($data.repaired)
if($data.document_id -ne '98d6635b-3767-4254-b200-ec8442b69ad2' -or
   $proven.Count -ne 21 -or $null -ne $data.pending){
  throw 'XD_RADIUS_SAVE_21_APPLIED_CHECKPOINT_INVALID'
}
$unique=@($proven | Select-Object -ExpandProperty guid -Unique)
if($unique.Count -ne 21){throw 'XD_RADIUS_SAVE_GUIDS_NOT_UNIQUE'}
for($i=0;$i -lt 21;$i++){
  if($proven[$i].ordinal -ne ($i+1) -or $proven[$i].status -ne 'applied' -or
     $proven[$i].name -notmatch '^[0-9]{2} XD '){
    throw "XD_RADIUS_SAVE_CHECKPOINT_ITEM_INVALID index=$i"
  }
}
$before=(Get-FileHash -LiteralPath $target -Algorithm SHA256).Hash
$initial='598F79071CF7DBFC426F9FEF50144CF94225D2E7BB384C89E2E4FE1D67FDAD29'
if($before -ne $initial){
  throw "XD_FINAL_SAVE_SOURCE_ALREADY_CHANGED_REFUSE_BLIND_SAVE sha256=$before"
}
Write-Host 'XD_RADIUS_SAVE_PRECONDITION=PASS repaired=21 pending=0 nativeOriginalSha=$before'
Add-Type -AssemblyName UIAutomationClient
Add-Type -AssemblyName UIAutomationTypes
$root=[System.Windows.Automation.AutomationElement]::RootElement
$top=$root.FindAll([System.Windows.Automation.TreeScope]::Children,
                    [System.Windows.Automation.Condition]::TrueCondition)
$docs=@()
foreach($el in $top){
  $name=[string]$el.Current.Name
  if($name -match '^MCP_Mode1_Panda_XD_38136531800.*Adobe XD$' -and
     [string]$el.Current.ClassName -eq 'ApplicationFrameWindow'){$docs+=,$el}
}
if($docs.Count -ne 1){throw "XD_FINAL_SAVE_LIVE_DOCUMENT_COUNT=$($docs.Count)"}
$document=$docs[0]
$menuCond=New-Object System.Windows.Automation.PropertyCondition(
  [System.Windows.Automation.AutomationElement]::AutomationIdProperty,'AppMenu_File')
$menu=$document.FindFirst([System.Windows.Automation.TreeScope]::Descendants,$menuCond)
if(-not $menu){throw 'XD_FINAL_SAVE_FILE_MENU_MISSING'}
$exp=$menu.GetCurrentPattern([System.Windows.Automation.ExpandCollapsePattern]::Pattern)
if($exp.Current.ExpandCollapseState -ne [System.Windows.Automation.ExpandCollapseState]::Expanded){
  $exp.Expand()
}
Start-Sleep -Milliseconds 350
$saveCond=New-Object System.Windows.Automation.PropertyCondition(
  [System.Windows.Automation.AutomationElement]::AutomationIdProperty,'AppMenu_Save')
$save=$document.FindFirst([System.Windows.Automation.TreeScope]::Descendants,$saveCond)
if(-not $save -or -not $save.Current.IsEnabled){
  Write-Host "XD_FINAL_SAVE_MENU_ENABLED=$($save.Current.IsEnabled)"
  throw 'XD_FINAL_SAVE_FILE_MENU_NOT_ENABLED_NO_COMMAND'
}
Write-Host "XD_FINAL_SAVE_ENABLED_COMMAND=PASS name=$($save.Current.Name)"
try{
  $save.GetCurrentPattern([System.Windows.Automation.InvokePattern]::Pattern).Invoke()
}catch{
  throw "XD_FINAL_SAVE_INVOKE_UNKNOWN_NO_REPLAY=$($_.Exception.Message)"
}
Write-Host 'XD_FINAL_SAVE_MENU_INVOKED_ONCE=PASS'
$deadline=(Get-Date).AddSeconds(45)
$changed=$false
while((Get-Date) -lt $deadline){
  Start-Sleep -Milliseconds 750
  if(-not (Test-Path -LiteralPath $target -PathType Leaf)){
    throw 'XD_FINAL_SAVE_TARGET_DISAPPEARED'
  }
  $size=(Get-Item -LiteralPath $target).Length
  if($size -ge 4096){
    $current=(Get-FileHash -LiteralPath $target -Algorithm SHA256).Hash
    if($current -ne $before){$changed=$true;break}
  }
}
if(-not $changed){throw 'XD_FINAL_SAVE_ORIGINAL_NOT_UPDATED_NO_REPLAY'}
Start-Sleep -Seconds 2
$stable1=Get-Item -LiteralPath $target
Start-Sleep -Seconds 2
$stable2=Get-Item -LiteralPath $target
if($stable1.Length -ne $stable2.Length -or $stable2.Length -lt 4096){
  throw 'XD_FINAL_SAVE_NATIVE_BYTES_UNSTABLE'
}
$hash=(Get-FileHash -LiteralPath $target -Algorithm SHA256).Hash
Add-Type -AssemblyName System.IO.Compression
Add-Type -AssemblyName System.IO.Compression.FileSystem
$archive=[System.IO.Compression.ZipFile]::OpenRead($target)
try{
  if($archive.Entries.Count -lt 12){throw 'XD_FINAL_SAVE_ARCHIVE_INCOMPLETE'}
  foreach($entry in $archive.Entries){
    if($entry.Length -gt 0){
      $stream=$entry.Open()
      try{
        $buffer=New-Object byte[] 8192
        while($stream.Read($buffer,0,$buffer.Length) -gt 0){}
      }finally{$stream.Dispose()}
    }
  }
  Write-Host "XD_FINAL_SAVE_ARCHIVE=PASS entries=$($archive.Entries.Count)"
}finally{$archive.Dispose()}
Write-Host "XD_RADIUS_REPAIRED_NATIVE_FILE_VERIFIED=PASS path=$target bytes=$($stable2.Length) sha256=$hash"
