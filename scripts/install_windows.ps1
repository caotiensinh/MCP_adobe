[CmdletBinding()]
param(
    [string]$PythonVersion = "3.12",
    [switch]$InstallXdPlugin,
    [switch]$GenerateConfigsOnly,
    [string]$UvCommandPath = "",
    [string]$OutputDir = ""
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
if ([string]::IsNullOrWhiteSpace($OutputDir)) {
    $OutputDir = Join-Path $RepoRoot ".mcp-adobe\client-configs"
}

function Refresh-ProcessPath {
    $machinePath = [Environment]::GetEnvironmentVariable("Path", "Machine")
    $userPath = [Environment]::GetEnvironmentVariable("Path", "User")
    $parts = @($machinePath, $userPath, $env:Path) | Where-Object { -not [string]::IsNullOrWhiteSpace($_) }
    $env:Path = ($parts -join ";")
}

function Resolve-CommandPath([string]$Name) {
    $cmd = Get-Command $Name -ErrorAction SilentlyContinue
    if ($null -ne $cmd) {
        if ($cmd.Source) { return $cmd.Source }
        return $cmd.Path
    }
    return $null
}

function Resolve-Uv {
    if (-not [string]::IsNullOrWhiteSpace($UvCommandPath)) {
        return $UvCommandPath
    }

    $uv = Resolve-CommandPath "uv"
    if ($uv) { return $uv }

    if ($GenerateConfigsOnly) {
        return "uv"
    }

    $winget = Resolve-CommandPath "winget"
    if ($winget) {
        Write-Host "uv=installing via WinGet"
        & $winget install --id astral-sh.uv -e --accept-package-agreements --accept-source-agreements --silent
        if ($LASTEXITCODE -ne 0) {
            Write-Host "uv=WinGet install failed; falling back to official Astral installer"
        }
        Refresh-ProcessPath
        $uv = Resolve-CommandPath "uv"
        if ($uv) { return $uv }
    }

    Write-Host "uv=installing via official Astral installer"
    $oldNoModify = $env:UV_NO_MODIFY_PATH
    try {
        $env:UV_NO_MODIFY_PATH = "1"
        $installer = Invoke-RestMethod -Uri "https://astral.sh/uv/install.ps1" -UseBasicParsing
        Invoke-Expression $installer
    }
    finally {
        if ($null -eq $oldNoModify) {
            Remove-Item Env:UV_NO_MODIFY_PATH -ErrorAction SilentlyContinue
        }
        else {
            $env:UV_NO_MODIFY_PATH = $oldNoModify
        }
    }

    Refresh-ProcessPath
    $candidates = @(
        (Join-Path $HOME ".local\bin\uv.exe"),
        (Join-Path $env:LOCALAPPDATA "Microsoft\WinGet\Links\uv.exe")
    )
    foreach ($candidate in $candidates) {
        if (Test-Path -LiteralPath $candidate) { return $candidate }
    }
    $uv = Resolve-CommandPath "uv"
    if ($uv) { return $uv }
    throw "uv installation completed but uv.exe could not be located"
}

function Ensure-NodeToolchain {
    $node = Resolve-CommandPath "node"
    $npx = Resolve-CommandPath "npx"
    if ($node -and $npx) {
        Write-Host "node=$(& $node --version)"
        Write-Host "npx=$(& $npx --version)"
        return
    }

    $winget = Resolve-CommandPath "winget"
    if (-not $winget) {
        throw "Node.js/npx is required for the pinned Photoshop launcher and Illustrator CEP validation, and WinGet is unavailable. Install Node.js LTS and rerun this script."
    }

    Write-Host "node=installing Node.js LTS via WinGet"
    & $winget install --id OpenJS.NodeJS.LTS -e --accept-package-agreements --accept-source-agreements --silent
    if ($LASTEXITCODE -ne 0) {
        throw "WinGet failed to install Node.js LTS (exit $LASTEXITCODE)"
    }
    Refresh-ProcessPath

    $node = Resolve-CommandPath "node"
    $npx = Resolve-CommandPath "npx"
    if (-not $node -or -not $npx) {
        throw "Node.js installation completed but node/npx is not visible in PATH. Open a new PowerShell and rerun the installer."
    }
    Write-Host "node=$(& $node --version)"
    Write-Host "npx=$(& $npx --version)"
}

function ConvertTo-TomlString([string]$Value) {
    $escaped = $Value.Replace("\", "\\").Replace('"', '\"')
    return '"' + $escaped + '"'
}

function Write-ClientConfigs([string]$UvExe) {
    New-Item -ItemType Directory -Path $OutputDir -Force | Out-Null

    $stdioArgs = @(
        "run",
        "--directory",
        $RepoRoot,
        "mcp-adobe",
        "--transport",
        "stdio"
    )

    $claudeConfig = [ordered]@{
        mcpServers = [ordered]@{
            "adobe-creative" = [ordered]@{
                type = "stdio"
                command = $UvExe
                args = $stdioArgs
            }
        }
    }
    $claudePath = Join-Path $OutputDir "claude-code.mcp.json"
    $claudeConfig | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $claudePath -Encoding UTF8

    $tomlArgs = ($stdioArgs | ForEach-Object { ConvertTo-TomlString $_ }) -join ", "
    $codex = @(
        "[mcp_servers.adobe_creative]",
        "command = $(ConvertTo-TomlString $UvExe)",
        "args = [$tomlArgs]",
        "cwd = $(ConvertTo-TomlString $RepoRoot)"
    ) -join [Environment]::NewLine
    $codexPath = Join-Path $OutputDir "codex.config.toml.snippet"
    Set-Content -LiteralPath $codexPath -Value $codex -Encoding UTF8

    $claudeCommand = 'claude mcp add --transport stdio --scope user adobe-creative -- "' + $UvExe + '" run --directory "' + $RepoRoot + '" mcp-adobe --transport stdio'
    $instructions = @(
        "MCP Adobe local stdio setup",
        "",
        "Claude Code:",
        $claudeCommand,
        "Verify: claude mcp get adobe-creative",
        "",
        "Claude Desktop / JSON-compatible clients:",
        "Use: $claudePath",
        "",
        "Codex:",
        "Merge the following file into your Codex config:",
        $codexPath,
        "",
        "Direct smoke:",
        '"' + $UvExe + '" run --directory "' + $RepoRoot + '" mcp-adobe --transport stdio',
        "",
        "Illustrator backend:",
        "The installer pins jinkeda/Illustrator_MCP and installs its CEP panel automatically.",
        "Start Illustrator, then open Window > Extensions > MCP Control if the panel is not already visible.",
        "",
        "No OAuth secret is stored in these generated local stdio configs."
    ) -join [Environment]::NewLine
    $instructionsPath = Join-Path $OutputDir "LOCAL_MCP_SETUP.txt"
    Set-Content -LiteralPath $instructionsPath -Value $instructions -Encoding UTF8

    Write-Host "client_configs=$OutputDir"
    Write-Host "claude_json=$claudePath"
    Write-Host "codex_toml=$codexPath"
    Write-Host "instructions=$instructionsPath"
}

$uvExe = Resolve-Uv
Write-Host "repo=$RepoRoot"
Write-Host "uv=$uvExe"

if ($GenerateConfigsOnly) {
    Write-ClientConfigs $uvExe
    Write-Host "result=PASS generate-configs-only"
    exit 0
}

Ensure-NodeToolchain

Write-Host "python=installing $PythonVersion via uv"
& $uvExe python install $PythonVersion
if ($LASTEXITCODE -ne 0) { throw "uv python install failed (exit $LASTEXITCODE)" }

Write-Host "project=sync"
& $uvExe sync --directory $RepoRoot --python $PythonVersion
if ($LASTEXITCODE -ne 0) { throw "uv sync failed (exit $LASTEXITCODE)" }

Write-Host "smoke=mcp-adobe"
& $uvExe run --directory $RepoRoot mcp-adobe --help | Out-Null
if ($LASTEXITCODE -ne 0) { throw "mcp-adobe CLI smoke failed" }

Write-Host "smoke=oauth-preflight"
& $uvExe run --directory $RepoRoot mcp-adobe-oauth-preflight --help | Out-Null
if ($LASTEXITCODE -ne 0) { throw "mcp-adobe-oauth-preflight CLI smoke failed" }

Write-Host "smoke=remote-probe"
& $uvExe run --directory $RepoRoot mcp-adobe-remote-probe --help | Out-Null
if ($LASTEXITCODE -ne 0) { throw "mcp-adobe-remote-probe CLI smoke failed" }

Write-Host "illustrator_backend=install"
& powershell -NoProfile -ExecutionPolicy Bypass -File (Join-Path $PSScriptRoot "install_illustrator_cep_backend.ps1") -PythonVersion $PythonVersion -UvCommandPath $uvExe
if ($LASTEXITCODE -ne 0) { throw "Illustrator CEP backend installation failed (exit $LASTEXITCODE)" }

if ($InstallXdPlugin) {
    Write-Host "xd_plugin=install"
    & powershell -NoProfile -ExecutionPolicy Bypass -File (Join-Path $PSScriptRoot "install_xd_plugin.ps1")
    if ($LASTEXITCODE -ne 0) { throw "XD development plugin installation failed (exit $LASTEXITCODE)" }
}

Write-ClientConfigs $uvExe

Write-Host "result=PASS"
Write-Host "next=See $(Join-Path $OutputDir 'LOCAL_MCP_SETUP.txt')"
