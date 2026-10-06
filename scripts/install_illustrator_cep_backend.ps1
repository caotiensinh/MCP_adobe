[CmdletBinding()]
param(
    [string]$PythonVersion = "3.12",
    [string]$UvCommandPath = "",
    [string]$InstallRoot = "",
    [string]$PanelTarget = "",
    [switch]$SkipRegistry
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$UpstreamRepo = "https://github.com/jinkeda/Illustrator_MCP.git"
$UpstreamSha = "5d7a3edc8ebc89a0fc56b059e1311d3b2bfca815"
$ExpectedPackageVersion = "3.0.0"
$ExtensionId = "com.illustrator.mcp.panel"

function Resolve-CommandPath([string]$Name) {
    $cmd = Get-Command $Name -ErrorAction SilentlyContinue
    if ($null -eq $cmd) { return $null }
    if ($cmd.Source) { return $cmd.Source }
    return $cmd.Path
}

function Invoke-Checked([string]$Program, [string[]]$Arguments, [string]$Label) {
    & $Program @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "$Label failed (exit $LASTEXITCODE)"
    }
}

function Get-ExistingItem([string]$Path) {
    return Get-Item -LiteralPath $Path -Force -ErrorAction SilentlyContinue
}

if ([string]::IsNullOrWhiteSpace($InstallRoot)) {
    if ([string]::IsNullOrWhiteSpace($env:LOCALAPPDATA)) {
        throw "LOCALAPPDATA is unavailable; pass -InstallRoot explicitly"
    }
    $InstallRoot = Join-Path $env:LOCALAPPDATA "MCPAdobe\illustrator-mcp"
}
if ([string]::IsNullOrWhiteSpace($PanelTarget)) {
    if ([string]::IsNullOrWhiteSpace($env:APPDATA)) {
        throw "APPDATA is unavailable; pass -PanelTarget explicitly"
    }
    $PanelTarget = Join-Path $env:APPDATA "Adobe\CEP\extensions\$ExtensionId"
}

$uv = $UvCommandPath
if ([string]::IsNullOrWhiteSpace($uv)) { $uv = Resolve-CommandPath "uv" }
if ([string]::IsNullOrWhiteSpace($uv) -or -not (Test-Path -LiteralPath $uv)) {
    throw "uv.exe is required. Run scripts/install_windows.ps1 or pass -UvCommandPath."
}
$git = Resolve-CommandPath "git"
if (-not $git) { throw "git is required for the pinned Illustrator backend install" }
$node = Resolve-CommandPath "node"
if (-not $node) { throw "node is required to validate the Illustrator CEP panel" }

# Never replace a backend while its persistent bridge may still be serving Illustrator.
$listeners = @(Get-NetTCPConnection -State Listen -LocalPort 8081 -ErrorAction SilentlyContinue)
if ($listeners.Count -gt 0) {
    foreach ($listener in $listeners) {
        $process = Get-Process -Id $listener.OwningProcess -ErrorAction SilentlyContinue
        Write-Host "illustrator_backend_port_busy=PID:$($listener.OwningProcess) PROCESS:$($process.ProcessName)"
    }
    throw "Port 8081 is in use. Close the active Illustrator MCP bridge before installing."
}

$installParent = Split-Path -Parent $InstallRoot
$installLeaf = Split-Path -Leaf $InstallRoot
$panelParent = Split-Path -Parent $PanelTarget
$panelLeaf = Split-Path -Leaf $PanelTarget
New-Item -ItemType Directory -Path $installParent -Force | Out-Null
New-Item -ItemType Directory -Path $panelParent -Force | Out-Null

$nonce = [Guid]::NewGuid().ToString("N")
$stagingRoot = Join-Path $installParent "$installLeaf.staging.$nonce"
$panelStage = Join-Path $panelParent "$panelLeaf.staging.$nonce"
$previousRoot = "$InstallRoot.previous"
$previousPanel = "$PanelTarget.previous"

if (Get-ExistingItem $previousRoot) {
    throw "Previous backend backup exists: $previousRoot. Resolve it before installing."
}
if (Get-ExistingItem $previousPanel) {
    throw "Previous CEP panel backup exists: $previousPanel. Resolve it before installing."
}

$source = Join-Path $stagingRoot "source"
$venv = Join-Path $stagingRoot "venv"
$rootMoved = $false
$panelMoved = $false
$newRootInstalled = $false
$newPanelInstalled = $false

try {
    New-Item -ItemType Directory -Path $stagingRoot -Force | Out-Null

    Invoke-Checked $git @("clone", "--no-checkout", $UpstreamRepo, $source) "Illustrator upstream clone"
    Invoke-Checked $git @("-C", $source, "fetch", "--depth=1", "origin", $UpstreamSha) "Illustrator upstream fetch"
    Invoke-Checked $git @("-C", $source, "checkout", "--detach", $UpstreamSha) "Illustrator upstream checkout"
    $actualSha = (& $git -C $source rev-parse HEAD).Trim()
    if ($LASTEXITCODE -ne 0 -or $actualSha -ne $UpstreamSha) {
        throw "Illustrator upstream SHA mismatch: expected=$UpstreamSha actual=$actualSha"
    }

    Invoke-Checked $uv @("venv", "--python", $PythonVersion, $venv) "Illustrator backend venv"
    $stagingPython = Join-Path $venv "Scripts\python.exe"
    if (-not (Test-Path -LiteralPath $stagingPython)) {
        throw "Illustrator backend Python was not created: $stagingPython"
    }
    Invoke-Checked $uv @("pip", "install", "--python", $stagingPython, $source) "Illustrator backend package install"

    $packageVersion = (& $stagingPython -c "import importlib.metadata as m; print(m.version('illustrator-mcp'))").Trim()
    if ($LASTEXITCODE -ne 0 -or $packageVersion -ne $ExpectedPackageVersion) {
        throw "Illustrator backend package mismatch: expected=$ExpectedPackageVersion actual=$packageVersion"
    }

    $cepSource = Join-Path $source "cep-extension"
    $validator = Join-Path $cepSource "validate-panel.mjs"
    if (-not (Test-Path -LiteralPath $validator)) {
        throw "Illustrator CEP validator missing: $validator"
    }
    Invoke-Checked $node @($validator, $cepSource) "Illustrator source CEP validation"

    Copy-Item -LiteralPath $cepSource -Destination $panelStage -Recurse -Force
    $stagedValidator = Join-Path $panelStage "validate-panel.mjs"
    Invoke-Checked $node @($stagedValidator, $panelStage) "Illustrator staged CEP validation"

    $metadata = [ordered]@{
        upstream_repository = "jinkeda/Illustrator_MCP"
        upstream_sha = $UpstreamSha
        package_version = $ExpectedPackageVersion
        python_version = $PythonVersion
        extension_id = $ExtensionId
        installed_utc = [DateTime]::UtcNow.ToString("o")
    }
    $metadata | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath (Join-Path $stagingRoot "install-metadata.json") -Encoding UTF8

    $existingRoot = Get-ExistingItem $InstallRoot
    if ($existingRoot) {
        Move-Item -LiteralPath $InstallRoot -Destination $previousRoot -Force
        $rootMoved = $true
    }
    Move-Item -LiteralPath $stagingRoot -Destination $InstallRoot
    $newRootInstalled = $true

    $existingPanel = Get-ExistingItem $PanelTarget
    if ($existingPanel) {
        Move-Item -LiteralPath $PanelTarget -Destination $previousPanel -Force
        $panelMoved = $true
    }
    Move-Item -LiteralPath $panelStage -Destination $PanelTarget
    $newPanelInstalled = $true

    if (-not $SkipRegistry) {
        foreach ($csxs in @("CSXS.11", "CSXS.12")) {
            $key = "HKCU:\Software\Adobe\$csxs"
            New-Item -Path $key -Force | Out-Null
            New-ItemProperty -Path $key -Name "PlayerDebugMode" -PropertyType String -Value "1" -Force | Out-Null
        }
    }

    $finalSource = Join-Path $InstallRoot "source"
    $finalPython = Join-Path $InstallRoot "venv\Scripts\python.exe"
    $finalSha = (& $git -C $finalSource rev-parse HEAD).Trim()
    if ($LASTEXITCODE -ne 0 -or $finalSha -ne $UpstreamSha) {
        throw "Installed Illustrator upstream SHA verification failed: $finalSha"
    }
    if (-not (Test-Path -LiteralPath $finalPython)) {
        throw "Installed Illustrator backend Python missing: $finalPython"
    }
    $finalVersion = (& $finalPython -c "import importlib.metadata as m; print(m.version('illustrator-mcp'))").Trim()
    if ($LASTEXITCODE -ne 0 -or $finalVersion -ne $ExpectedPackageVersion) {
        throw "Installed Illustrator package verification failed: $finalVersion"
    }
    $finalValidator = Join-Path $PanelTarget "validate-panel.mjs"
    Invoke-Checked $node @($finalValidator, $PanelTarget) "Installed Illustrator CEP validation"
    $manifest = Join-Path $PanelTarget "CSXS\manifest.xml"
    if (-not (Test-Path -LiteralPath $manifest)) {
        throw "Installed Illustrator CEP manifest missing: $manifest"
    }

    if ($rootMoved -and (Get-ExistingItem $previousRoot)) {
        Remove-Item -LiteralPath $previousRoot -Recurse -Force
        $rootMoved = $false
    }
    if ($panelMoved -and (Get-ExistingItem $previousPanel)) {
        Remove-Item -LiteralPath $previousPanel -Recurse -Force
        $panelMoved = $false
    }

    Write-Host "illustrator_backend=PASS"
    Write-Host "illustrator_backend_sha=$finalSha"
    Write-Host "illustrator_backend_version=$finalVersion"
    Write-Host "illustrator_backend_python=$finalPython"
    Write-Host "illustrator_cep_panel=$PanelTarget"
}
catch {
    Write-Host "illustrator_backend=FAIL"
    Write-Host "illustrator_backend_error=$($_.Exception.Message)"

    if ($newPanelInstalled -and (Get-ExistingItem $PanelTarget)) {
        Remove-Item -LiteralPath $PanelTarget -Recurse -Force -ErrorAction SilentlyContinue
    }
    if ($panelMoved -and (Get-ExistingItem $previousPanel)) {
        Move-Item -LiteralPath $previousPanel -Destination $PanelTarget -Force -ErrorAction SilentlyContinue
    }
    if ($newRootInstalled -and (Get-ExistingItem $InstallRoot)) {
        Remove-Item -LiteralPath $InstallRoot -Recurse -Force -ErrorAction SilentlyContinue
    }
    if ($rootMoved -and (Get-ExistingItem $previousRoot)) {
        Move-Item -LiteralPath $previousRoot -Destination $InstallRoot -Force -ErrorAction SilentlyContinue
    }
    throw
}
finally {
    if (Get-ExistingItem $stagingRoot) {
        Remove-Item -LiteralPath $stagingRoot -Recurse -Force -ErrorAction SilentlyContinue
    }
    if (Get-ExistingItem $panelStage) {
        Remove-Item -LiteralPath $panelStage -Recurse -Force -ErrorAction SilentlyContinue
    }
}
