param(
    [string]$OutputPath = "",
    [string]$McpbVersion = "2.1.2"
)

$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path -Parent $PSScriptRoot

if ([string]::IsNullOrWhiteSpace($OutputPath)) {
    $OutputPath = Join-Path $repoRoot 'dist\mcp-adobe-creative-gateway.mcpb'
}

if (-not (Get-Command npx -ErrorAction SilentlyContinue)) {
    throw 'npx was not found. Install Node.js 20+ before building the MCPB package.'
}

$manifest = Join-Path $repoRoot 'manifest.json'
if (-not (Test-Path $manifest)) {
    throw "MCPB manifest not found: $manifest"
}

$outputDirectory = Split-Path -Parent $OutputPath
New-Item -ItemType Directory -Path $outputDirectory -Force | Out-Null
if (Test-Path $OutputPath) {
    Remove-Item -Force $OutputPath
}

$cli = "@anthropic-ai/mcpb@$McpbVersion"

Push-Location $repoRoot
try {
    Write-Host "Validating MCPB manifest with $cli"
    & npx -y $cli validate .
    if ($LASTEXITCODE -ne 0) {
        throw "MCPB manifest validation failed with exit code $LASTEXITCODE"
    }

    Write-Host "Packing MCPB to $OutputPath"
    & npx -y $cli pack . $OutputPath
    if ($LASTEXITCODE -ne 0) {
        throw "MCPB pack failed with exit code $LASTEXITCODE"
    }
} finally {
    Pop-Location
}

if (-not (Test-Path $OutputPath)) {
    throw "MCPB output was not created: $OutputPath"
}

$file = Get-Item $OutputPath
if ($file.Length -le 0) {
    throw "MCPB output is empty: $OutputPath"
}

Write-Host "PASS: MCPB package created"
Write-Host "Path=$($file.FullName)"
Write-Host "Bytes=$($file.Length)"
