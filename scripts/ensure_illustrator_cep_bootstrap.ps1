[CmdletBinding()]
param(
    [string]$PanelTarget = "",
    [switch]$VerifyOnly
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$BootstrapId = "com.illustrator.mcp.bootstrap"
$PanelId = "com.illustrator.mcp.panel"

if ([string]::IsNullOrWhiteSpace($PanelTarget)) {
    if ([string]::IsNullOrWhiteSpace($env:APPDATA)) {
        throw "APPDATA is unavailable; pass -PanelTarget explicitly"
    }
    $PanelTarget = Join-Path $env:APPDATA ("Adobe\CEP\extensions\" + $PanelId)
}

$manifest = Join-Path $PanelTarget "CSXS\manifest.xml"
$csInterface = Join-Path $PanelTarget "dist\CSInterface.js"
$bootstrapDir = Join-Path $PanelTarget "bootstrap"
$bootstrapHtml = Join-Path $bootstrapDir "index.html"

function Test-BootstrapContract {
    if (-not (Test-Path -LiteralPath $manifest)) {
        throw "Illustrator CEP manifest missing: $manifest"
    }
    if (-not (Test-Path -LiteralPath $csInterface)) {
        throw "Illustrator CEP CSInterface.js missing: $csInterface"
    }
    if (-not (Test-Path -LiteralPath $bootstrapHtml)) {
        throw "Illustrator CEP bootstrap HTML missing: $bootstrapHtml"
    }

    $manifestText = [IO.File]::ReadAllText($manifest)
    $htmlText = [IO.File]::ReadAllText($bootstrapHtml)
    $extensionEntry = '<Extension Id="{0}" Version="1.0.0" />' -f $BootstrapId
    $dispatchEntry = '<Extension Id="{0}">' -f $BootstrapId
    foreach ($required in @(
        $extensionEntry,
        $dispatchEntry,
        "<MainPath>./bootstrap/index.html</MainPath>",
        "<AutoVisible>false</AutoVisible>",
        "<Event>applicationActivate</Event>",
        "<Event>com.adobe.csxs.events.ApplicationActivate</Event>",
        "<Event>com.adobe.csxs.events.ApplicationInitialized</Event>",
        "<Type>Custom</Type>"
    )) {
        if (-not $manifestText.Contains($required)) {
            throw "Illustrator CEP bootstrap manifest marker missing: $required"
        }
    }
    if (-not $htmlText.Contains("requestOpenExtension")) {
        throw "Illustrator CEP bootstrap does not request the MCP Control panel"
    }
    if (-not $htmlText.Contains($PanelId)) {
        throw "Illustrator CEP bootstrap target panel id is missing"
    }
}

if ($VerifyOnly) {
    Test-BootstrapContract
    Write-Host "illustrator_cep_bootstrap=VERIFY_PASS"
    exit 0
}

if (-not (Test-Path -LiteralPath $manifest)) {
    throw "Illustrator CEP manifest missing: $manifest"
}
if (-not (Test-Path -LiteralPath $csInterface)) {
    throw "Illustrator CEP CSInterface.js missing: $csInterface"
}

$manifestText = [IO.File]::ReadAllText($manifest)
$extensionListMarker = "</ExtensionList>"
$dispatchListMarker = "</DispatchInfoList>"
$extensionEntry = '<Extension Id="{0}" Version="1.0.0" />' -f $BootstrapId
$dispatchEntry = '<Extension Id="{0}">' -f $BootstrapId

if (-not $manifestText.Contains($extensionEntry)) {
    if (-not $manifestText.Contains($extensionListMarker)) {
        throw "Illustrator CEP manifest ExtensionList marker missing"
    }
    $entry = "        " + $extensionEntry + [Environment]::NewLine + "    "
    $manifestText = $manifestText.Replace($extensionListMarker, $entry + $extensionListMarker)
}

if (-not $manifestText.Contains($dispatchEntry)) {
    if (-not $manifestText.Contains($dispatchListMarker)) {
        throw "Illustrator CEP manifest DispatchInfoList marker missing"
    }
    $dispatch = @"
        <Extension Id="$BootstrapId">
            <DispatchInfo>
                <Resources>
                    <MainPath>./bootstrap/index.html</MainPath>
                </Resources>
                <Lifecycle>
                    <AutoVisible>false</AutoVisible>
                    <StartOn>
                        <Event>applicationActivate</Event>
                        <Event>com.adobe.csxs.events.ApplicationActivate</Event>
                        <Event>com.adobe.csxs.events.ApplicationInitialized</Event>
                    </StartOn>
                </Lifecycle>
                <UI>
                    <Type>Custom</Type>
                    <Geometry>
                        <Size>
                            <Height>1</Height>
                            <Width>1</Width>
                        </Size>
                    </Geometry>
                </UI>
            </DispatchInfo>
        </Extension>
"@
    $manifestText = $manifestText.Replace(
        $dispatchListMarker,
        $dispatch + [Environment]::NewLine + "    " + $dispatchListMarker
    )
}

New-Item -ItemType Directory -Path $bootstrapDir -Force | Out-Null
$html = @"
<!doctype html>
<html>
<head>
  <meta charset="utf-8">
  <script src="../dist/CSInterface.js"></script>
</head>
<body>
<script>
(function () {
  var target = "$PanelId";
  var cs = new CSInterface();
  function openPanel() {
    try { cs.requestOpenExtension(target, ""); } catch (e) {}
  }
  openPanel();
  window.setTimeout(openPanel, 1000);
  window.setTimeout(openPanel, 3000);
})();
</script>
</body>
</html>
"@

$manifestTemp = "$manifest.bootstrap.tmp"
$htmlTemp = "$bootstrapHtml.tmp"
try {
    [IO.File]::WriteAllText($manifestTemp, $manifestText, (New-Object Text.UTF8Encoding($false)))
    [IO.File]::WriteAllText($htmlTemp, $html, (New-Object Text.UTF8Encoding($false)))
    Move-Item -LiteralPath $manifestTemp -Destination $manifest -Force
    Move-Item -LiteralPath $htmlTemp -Destination $bootstrapHtml -Force
}
finally {
    Remove-Item -LiteralPath $manifestTemp -Force -ErrorAction SilentlyContinue
    Remove-Item -LiteralPath $htmlTemp -Force -ErrorAction SilentlyContinue
}

Test-BootstrapContract
Write-Host "illustrator_cep_bootstrap=PATCH_PASS"
Write-Host "illustrator_cep_bootstrap_manifest=$manifest"
Write-Host "illustrator_cep_bootstrap_html=$bootstrapHtml"
