param(
  [string]$DevelopFolder
)
$ErrorActionPreference='Stop'
$repoRoot=Split-Path -Parent $PSScriptRoot
$source=Join-Path $repoRoot 'experimental\mode2-xd-uxp'
$main=Join-Path $source 'main.js'
$manifest=Join-Path $source 'manifest.json'
if(!(Test-Path -LiteralPath $main -PathType Leaf) -or
   !(Test-Path -LiteralPath $manifest -PathType Leaf)){
  throw 'MODE2_STAGE_SOURCE_MISSING'
}
$m=Get-Content -LiteralPath $manifest -Raw -Encoding UTF8 | ConvertFrom-Json
if($m.id -ne 'MCPADM2E' -or $m.host.app -ne 'XD' -or $m.main -ne 'main.js' -or
   $m.manifestVersion -ne 4 -or @($m.entrypoints).Count -lt 3){
  throw 'MODE2_STAGE_MANIFEST_NOT_ISOLATED'
}
$plugin=Get-Content -LiteralPath $main -Raw -Encoding UTF8
if($plugin -notmatch 'BRIDGE_URL = "ws://127\.0\.0\.1:8766"' -or
   $plugin -notmatch 'BRIDGE_BUILD = "xd-mode2-guarded-experimental-v1"'){
  throw 'MODE2_STAGE_PLUGIN_BRIDGE_NOT_ISOLATED'
}
if($DevelopFolder){
  $develop=[IO.Path]::GetFullPath($DevelopFolder)
  if(!(Test-Path -LiteralPath $develop -PathType Container)){
    throw 'MODE2_EXPLICIT_DEVELOP_FOLDER_NOT_FOUND'
  }
}else{
  if(!$env:LOCALAPPDATA){throw 'MODE2_STAGE_LOCALAPPDATA_MISSING'}
  $root=Join-Path $env:LOCALAPPDATA 'Packages'
  if(!(Test-Path -LiteralPath $root -PathType Container)){throw 'MODE2_XD_PACKAGES_MISSING'}
  $candidates=@(
    Get-ChildItem -LiteralPath $root -Directory -ErrorAction Stop |
      Where-Object {$_.Name -match '^Adobe\.(CC\.)?XD_'} |
      ForEach-Object {Join-Path $_.FullName 'LocalState\develop'} |
      Where-Object {Test-Path -LiteralPath (Split-Path -Parent $_) -PathType Container}
  )
  $candidates=@($candidates | Select-Object -Unique)
  if($candidates.Count -ne 1){
    throw "MODE2_XD_DEVELOP_FOLDER_AMBIGUOUS count=$($candidates.Count)"
  }
  $develop=[IO.Path]::GetFullPath($candidates[0])
  if(!(Test-Path -LiteralPath $develop)){
    New-Item -ItemType Directory -Path $develop -Force | Out-Null
  }
}
$production=Join-Path $develop 'MCPAdobeBridge'
$productionMain=Join-Path $production 'main.js'
$productionManifest=Join-Path $production 'manifest.json'
$productionBefore=@{}
foreach($p in @($productionMain,$productionManifest)){
  if(Test-Path -LiteralPath $p -PathType Leaf){
    $productionBefore[$p]=(Get-FileHash -LiteralPath $p -Algorithm SHA256).Hash
  }
}
$target=Join-Path $develop 'MCPAdobeMode2Experiment'
$sourceHash=(Get-FileHash -LiteralPath $main -Algorithm SHA256).Hash
$manifestHash=(Get-FileHash -LiteralPath $manifest -Algorithm SHA256).Hash
if(Test-Path -LiteralPath $target){
  if(!(Test-Path -LiteralPath $target -PathType Container) -or
     !(Test-Path -LiteralPath (Join-Path $target 'manifest.json') -PathType Leaf) -or
     !(Test-Path -LiteralPath (Join-Path $target 'main.js') -PathType Leaf)){
    throw 'MODE2_STAGE_EXISTING_DESTINATION_UNOWNED'
  }
  $existing=Get-Content -LiteralPath (Join-Path $target 'manifest.json') -Raw -Encoding UTF8 | ConvertFrom-Json
  if($existing.id -ne 'MCPADM2E'){throw 'MODE2_STAGE_EXISTING_PLUGIN_ID_MISMATCH'}
  if((Get-FileHash -LiteralPath (Join-Path $target 'manifest.json') -Algorithm SHA256).Hash -ne $manifestHash -or
     (Get-FileHash -LiteralPath (Join-Path $target 'main.js') -Algorithm SHA256).Hash -ne $sourceHash){
    throw 'MODE2_STAGE_EXISTING_DIFFERENT_CONTENT_NO_OVERWRITE'
  }
  Write-Host 'MODE2_EXPERIMENTAL_ALREADY_STAGED=PASS'
}else{
  $staging=Join-Path $develop ('.MCPAdobeMode2Experiment.stage-'+$PID)
  if(Test-Path -LiteralPath $staging){throw 'MODE2_STAGE_COLLISION'}
  try{
    New-Item -ItemType Directory -Path $staging -ErrorAction Stop|Out-Null
    Copy-Item -LiteralPath $main -Destination (Join-Path $staging 'main.js') -ErrorAction Stop
    Copy-Item -LiteralPath $manifest -Destination (Join-Path $staging 'manifest.json') -ErrorAction Stop
    if((Get-FileHash -LiteralPath (Join-Path $staging 'main.js') -Algorithm SHA256).Hash -ne $sourceHash -or
       (Get-FileHash -LiteralPath (Join-Path $staging 'manifest.json') -Algorithm SHA256).Hash -ne $manifestHash){
      throw 'MODE2_STAGE_HASH_MISMATCH'
    }
    Move-Item -LiteralPath $staging -Destination $target -ErrorAction Stop
  }finally{
    if(Test-Path -LiteralPath $staging){Remove-Item -LiteralPath $staging -Recurse -Force}
  }
  Write-Host 'MODE2_EXPERIMENTAL_NEW_STAGE=PASS'
}
foreach($p in @($productionMain,$productionManifest)){
  if($productionBefore.ContainsKey($p) -and
     (Get-FileHash -LiteralPath $p -Algorithm SHA256).Hash -ne $productionBefore[$p]){
    throw 'MODE2_STAGE_PRODUCTION_PLUGIN_CHANGED'
  }
}
Write-Host "MODE2_EXPERIMENTAL_STAGE_PATH=$target"
Write-Host 'MODE2_PRODUCTION_DEVELOP_PLUGIN_PRESERVED=PASS'
Write-Host 'MODE2_EXPERIMENTAL_PORT=8766'
Write-Host 'MODE2_EXPERIMENTAL_PLUGIN_ID=MCPADM2E'
Write-Host 'MODE2_RELOAD_OR_ACTIVATION_PERFORMED=False'
