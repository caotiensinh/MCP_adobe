[CmdletBinding()]
param(
    [string]$UpstreamRepository = "https://github.com/jinkeda/Illustrator_MCP.git",
    [string]$UpstreamRef = "5d7a3edc8ebc89a0fc56b059e1311d3b2bfca815",
    [string]$SourceDir = "",
    [string]$TargetDir = "",
    [string]$PythonCommand = "python",
    [switch]$SkipBuild,
    [switch]$EnableUnsignedDebug
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Resolve-Tool([string]$Name) {
    $cmd = Get-Command $Name -ErrorAction SilentlyContinue
    if ($null -eq $cmd) { throw "required command not found: $Name" }
    if ($cmd.Source) { return $cmd.Source }
    return $cmd.Path
}

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$ownsSource = $false
if ([string]::IsNullOrWhiteSpace($SourceDir)) {
    $SourceDir = Join-Path $env:TEMP "MCPAdobe-Illustrator-MCP"
    $ownsSource = $true
}
if ([string]::IsNullOrWhiteSpace($TargetDir)) {
    $TargetDir = Join-Path $env:APPDATA "Adobe\CEP\extensions\com.illustrator.mcp.panel"
}

$git = Resolve-Tool "git"
$node = Resolve-Tool "node"
$npm = Resolve-Tool "npm"

if ($ownsSource) {
    if (Test-Path -LiteralPath $SourceDir) {
        Remove-Item -LiteralPath $SourceDir -Recurse -Force
    }
    Write-Host "illustrator_cep=clone $UpstreamRepository"
    & $git clone $UpstreamRepository $SourceDir
    if ($LASTEXITCODE -ne 0) { throw "Illustrator CEP upstream clone failed" }
}
elseif (-not (Test-Path -LiteralPath $SourceDir -PathType Container)) {
    throw "Illustrator CEP SourceDir does not exist: $SourceDir"
}

& $git -C $SourceDir checkout --detach $UpstreamRef
if ($LASTEXITCODE -ne 0) { throw "Illustrator CEP upstream checkout failed: $UpstreamRef" }
$actual = (& $git -C $SourceDir rev-parse HEAD).Trim()
if ($actual -ne $UpstreamRef) {
    throw "Illustrator CEP pinned checkout mismatch: expected=$UpstreamRef actual=$actual"
}
Write-Host "illustrator_cep_upstream=$actual"

$cep = Join-Path $SourceDir "cep-extension"
if (-not (Test-Path -LiteralPath $cep -PathType Container)) {
    throw "Illustrator CEP extension directory is missing: $cep"
}

if (-not $SkipBuild) {
    Push-Location $cep
    try {
        Write-Host "illustrator_cep=npm_ci"
        & $npm ci
        if ($LASTEXITCODE -ne 0) { throw "Illustrator CEP npm ci failed" }
        & $npm run typecheck
        if ($LASTEXITCODE -ne 0) { throw "Illustrator CEP typecheck failed" }
        & $npm run build
        if ($LASTEXITCODE -ne 0) { throw "Illustrator CEP build failed" }
        & $node validate-panel.mjs $cep
        if ($LASTEXITCODE -ne 0) { throw "Illustrator CEP upstream validation failed" }
    }
    finally {
        Pop-Location
    }
}

$prepare = Join-Path $PSScriptRoot "prepare_illustrator_cep.py"
& $PythonCommand $prepare $cep
if ($LASTEXITCODE -ne 0) { throw "Illustrator CEP production compatibility preparation failed" }

if (Test-Path -LiteralPath $TargetDir) {
    Remove-Item -LiteralPath $TargetDir -Recurse -Force
}
New-Item -ItemType Directory -Force -Path $TargetDir | Out-Null
Copy-Item -Path (Join-Path $cep "*") -Destination $TargetDir -Recurse -Force

& $node (Join-Path $TargetDir "validate-panel.mjs") $TargetDir
if ($LASTEXITCODE -ne 0) { throw "Installed Illustrator CEP validation failed" }

$installedManifest = Get-Content -LiteralPath (Join-Path $TargetDir "CSXS\manifest.xml") -Raw
$installedIndex = Get-Content -LiteralPath (Join-Path $TargetDir "dist\index.html") -Raw
if ($installedManifest -notmatch '<StartOn>' -or $installedManifest -notmatch 'applicationActivate') {
    throw "Installed Illustrator CEP StartOn verification failed"
}
if ($installedIndex -match '<script type="module"' -or $installedIndex -notmatch '<script defer src="\./assets/[^\"]+\.js"></script>') {
    throw "Installed Illustrator CEP classic/defer verification failed"
}
foreach ($marker in @("mcp_adobe_cep_inline_probe", "INLINE_START", "ROOT_LEN:", "WS_OPEN")) {
    if ($installedIndex.Contains($marker)) {
        throw "Diagnostic-only marker leaked into installed Illustrator CEP payload: $marker"
    }
}

if ($EnableUnsignedDebug) {
    foreach ($version in @("11", "12")) {
        & reg add "HKEY_CURRENT_USER\Software\Adobe\CSXS.$version" /v PlayerDebugMode /t REG_SZ /d 1 /f | Out-Null
        if ($LASTEXITCODE -ne 0) { throw "Failed to enable CSXS.$version PlayerDebugMode" }
    }
    Write-Host "illustrator_cep_unsigned_debug=enabled"
}
else {
    Write-Host "illustrator_cep_unsigned_debug=unchanged"
}

Write-Host "illustrator_cep_target=$TargetDir"
Write-Host "illustrator_cep_result=PASS"
