[CmdletBinding()]
param(
    [string]$PythonVersion = "3.12",
    [string]$UvCommandPath = "",
    [string]$NodeCommandPath = "",
    [string]$NpmCommandPath = "",
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

function Refresh-ProcessPath {
    $machinePath = [Environment]::GetEnvironmentVariable("Path", "Machine")
    $userPath = [Environment]::GetEnvironmentVariable("Path", "User")
    $parts = @($machinePath, $userPath, $env:Path) | Where-Object { -not [string]::IsNullOrWhiteSpace($_) }
    $env:Path = ($parts -join ";")
}

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

function Test-CepPanelPayload([string]$Root, [string]$Label) {
    $rootFull = [IO.Path]::GetFullPath($Root)
    $prefix = $rootFull.TrimEnd([char[]]"\/") + [IO.Path]::DirectorySeparatorChar

    function Require-PanelFile([string]$RelativePath) {
        $candidate = [IO.Path]::GetFullPath((Join-Path $rootFull $RelativePath))
        if (-not $candidate.StartsWith($prefix, [StringComparison]::OrdinalIgnoreCase)) {
            throw "$Label failed: panel path escapes root: $RelativePath"
        }
        $item = Get-Item -LiteralPath $candidate -Force -ErrorAction SilentlyContinue
        if ($null -eq $item -or $item.PSIsContainer -or $item.Length -le 0) {
            throw "$Label failed: missing, empty, or invalid panel file: $RelativePath"
        }
        return $candidate
    }

    foreach ($required in @("dist/index.html", "dist/CSInterface.js", "CSXS/manifest.xml", "jsx/host.jsx")) {
        Require-PanelFile $required | Out-Null
    }

    $htmlPath = Require-PanelFile "dist/index.html"
    $html = [IO.File]::ReadAllText($htmlPath)
    $matches = [regex]::Matches(
        $html,
        '\b(?:src|href)\s*=\s*["'']([^"'']+)["'']',
        [Text.RegularExpressions.RegexOptions]::IgnoreCase
    )
    $assetCount = 0
    foreach ($match in $matches) {
        $url = $match.Groups[1].Value
        if ($url.StartsWith("#") -or $url.StartsWith("data:")) { continue }
        if ($url -match '^(?:[a-z]+:|/)') {
            throw "$Label failed: panel asset must be local and relative: $url"
        }
        $clean = ($url -split '[?#]', 2)[0]
        $decoded = [Uri]::UnescapeDataString($clean)
        Require-PanelFile (Join-Path "dist" $decoded) | Out-Null
        $assetCount++
    }
    if ($assetCount -eq 0) {
        throw "$Label failed: panel HTML contains no asset references"
    }
    Write-Host "$Label=PASS assets=$assetCount validator=powershell"
}

function Invoke-CepPanelValidation([string]$Root, [string]$Label) {
    $validator = Join-Path $Root "validate-panel.mjs"
    if (-not (Test-Path -LiteralPath $validator)) {
        throw "$Label failed: upstream validator missing: $validator"
    }
    if ($node) {
        Invoke-Checked $node @($validator, $Root) $Label
        Write-Host "$Label validator=node"
        return
    }
    Test-CepPanelPayload $Root $Label
}

# A child PowerShell (for example from GitHub Actions or the main installer)
# can inherit a stale PATH even when Node/Git were installed system-wide.
# Refresh before resolving any external executable so this script is robust
# when invoked directly as well as through install_windows.ps1.
Refresh-ProcessPath

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
$node = $NodeCommandPath
if ([string]::IsNullOrWhiteSpace($node)) { $node = Resolve-CommandPath "node" }
if (-not [string]::IsNullOrWhiteSpace($node) -and -not (Test-Path -LiteralPath $node)) {
    throw "Node command path does not exist: $node"
}
$npm = $NpmCommandPath
if ([string]::IsNullOrWhiteSpace($npm)) { $npm = Resolve-CommandPath "npm.cmd" }
if ([string]::IsNullOrWhiteSpace($npm)) { $npm = Resolve-CommandPath "npm" }
if (-not [string]::IsNullOrWhiteSpace($npm) -and -not (Test-Path -LiteralPath $npm)) {
    throw "npm command path does not exist: $npm"
}
if (-not $node) {
    Write-Host "illustrator_cep_validator=node-unavailable; PowerShell validation remains available for prebuilt payloads"
}

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

    New-Item -ItemType Directory -Path $source -Force | Out-Null
    Invoke-Checked $git @("-C", $source, "init") "Illustrator upstream init"
    Invoke-Checked $git @("-C", $source, "remote", "add", "origin", $UpstreamRepo) "Illustrator upstream remote"
    Invoke-Checked $git @("-C", $source, "-c", "protocol.version=2", "fetch", "--no-tags", "--depth=1", "origin", $UpstreamSha) "Illustrator upstream exact-SHA fetch"
    Invoke-Checked $git @("-C", $source, "checkout", "--detach", "FETCH_HEAD") "Illustrator upstream checkout"
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
    $distIndex = Join-Path $cepSource "dist\index.html"
    if (-not (Test-Path -LiteralPath $distIndex)) {
        if (-not $node -or -not $npm) {
            throw "Illustrator CEP dist is absent at the pinned upstream SHA; Node.js and npm are required to build the panel."
        }
        Write-Host "illustrator_cep_build=START"
        Push-Location $cepSource
        try {
            Invoke-Checked $npm @("ci", "--no-audit", "--no-fund") "Illustrator CEP npm ci"
            Invoke-Checked $npm @("run", "build") "Illustrator CEP npm build"
        }
        finally {
            Pop-Location
        }
        if (-not (Test-Path -LiteralPath $distIndex)) {
            throw "Illustrator CEP build completed without dist/index.html"
        }
        Write-Host "illustrator_cep_build=PASS"
    }
    else {
        Write-Host "illustrator_cep_build=SKIP prebuilt-dist-present"
    }
    Invoke-CepPanelValidation $cepSource "Illustrator source CEP validation"

    Copy-Item -LiteralPath $cepSource -Destination $panelStage -Recurse -Force
    Invoke-CepPanelValidation $panelStage "Illustrator staged CEP validation"

    $nodeModules = Join-Path $source "cep-extension\node_modules"
    if (Test-Path -LiteralPath $nodeModules) {
        Remove-Item -LiteralPath $nodeModules -Recurse -Force
        Write-Host "illustrator_cep_build_dependencies=REMOVED"
    }

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
    Invoke-CepPanelValidation $PanelTarget "Installed Illustrator CEP validation"
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
