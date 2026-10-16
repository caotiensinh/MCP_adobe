param([string]$SourceRunId="38136531800")
$ErrorActionPreference='Stop'
if($env:COMPUTERNAME -ne 'MRCAO'){throw 'XD_FINAL_SAVE_WRONG_HOST'}
if([System.Diagnostics.Process]::GetCurrentProcess().SessionId -ne 1){throw 'XD_FINAL_SAVE_WRONG_SESSION'}
if($SourceRunId -ne "38136531800"){throw 'XD_FINAL_SAVE_WRONG_SOURCE_ID'}
$folder=Join-Path $env:USERPROFILE 'Documents\MCPAdobe'
$target=Join-Path $folder "MCP_Mode1_Panda_XD_$SourceRunId.xd"
$checkpoint=Join-Path $folder "MCP_Mode1_Panda_XD_$SourceRunId.json"
if(-not (Test-Path -LiteralPath $target -PathType Leaf) -or
   -not (Test-Path -LiteralPath $checkpoint -PathType Leaf)){
  throw 'XD_FINAL_SAVE_SOURCE_OR_CHECKPOINT_MISSING'
}
$data=Get-Content -LiteralPath $checkpoint -Raw | ConvertFrom-Json
$proven=@($data.proven)
if($data.run -ne $SourceRunId -or $data.document_id -ne '98d6635b-3767-4254-b200-ec8442b69ad2' -or
   $proven.Count -ne 32 -or $null -ne $data.pending){
  throw 'XD_FINAL_SAVE_32_APPLIED_CHECKPOINT_INVALID'
}
$unique=@($proven | Select-Object -ExpandProperty guid -Unique)
if($unique.Count -ne 32){throw 'XD_FINAL_SAVE_GUIDS_NOT_UNIQUE'}
for($i=0;$i -lt 32;$i++){
  if($proven[$i].ordinal -ne ($i+1) -or $proven[$i].status -ne 'applied' -or
     $proven[$i].name -notmatch ('^'+('{0:D2}' -f ($i+1))+' XD ')){
    throw "XD_FINAL_SAVE_CHECKPOINT_ITEM_INVALID index=$i"
  }
}
$before=(Get-FileHash -LiteralPath $target -Algorithm SHA256).Hash
$initial='D27EB3087D9DD4AA12FA055DFD1AE91F2E81E959235D31E4A430FF3BE0645E39'
if($before -ne $initial){
  throw "XD_FINAL_SAVE_SOURCE_ALREADY_CHANGED_REFUSE_BLIND_SAVE sha256=$before"
}
Write-Host 'XD_FINAL_SAVE_PRECONDITION=PASS shapes=32 pending=0 nativeOriginalSha=$before'
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
Write-Host "XD_FINAL_NATIVE_FILE_VERIFIED=PASS path=$target bytes=$($stable2.Length) sha256=$hash"
