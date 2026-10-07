<#
.SYNOPSIS
    Build the Python wheel and the QGIS plugin zip, and publish the wheel to the
    private package index (pypiserver locally; JFrog Artifactory in a company).

.DESCRIPTION
    1. Builds dist\fibre_planning-<version>-py3-none-any.whl (pip wheel).
    2. Builds dist\fibre_planning_qgis-<version>.zip, installable in QGIS via
       Plugins > Manage and Install Plugins > Install from ZIP.
    3. Starts the index (docker compose profile "packages"), uploads the wheel
       with twine using the publisher credentials from .env, then proves the
       round trip by downloading it back with pip from that index.

    Against Artifactory only the URL and the token change:
    twine upload --repository-url https://<company>.jfrog.io/artifactory/api/pypi/<repo> ...

.EXAMPLE
    .\scripts\package.ps1            # build and publish
    .\scripts\package.ps1 -NoPublish # build only
#>
[CmdletBinding()]
param([switch]$NoPublish)
$ErrorActionPreference = "Stop"
$Root = Resolve-Path (Join-Path $PSScriptRoot "..")
Set-Location $Root
$Dist = Join-Path $Root "dist"
New-Item -ItemType Directory -Force -Path $Dist | Out-Null

function Invoke-Checked([string]$Name, [scriptblock]$Command) {
    Write-Host "==> $Name" -ForegroundColor Cyan
    # Native tools (conda, docker) write warnings to stderr; judge them by exit code only
    $ErrorActionPreference = "Continue"
    & $Command
    if ($LASTEXITCODE -ne 0) { throw "$Name failed (exit code $LASTEXITCODE)" }
}

function Read-DotEnv {
    $values = @{}
    foreach ($line in Get-Content (Join-Path $Root ".env")) {
        if ($line -match '^\s*([A-Z_]+)\s*=\s*([^#]*?)\s*(#.*)?$') { $values[$Matches[1]] = $Matches[2] }
    }
    return $values
}

# --- 1. wheel -------------------------------------------------------------------
Invoke-Checked "build wheel" {
    conda run -n fibre --no-capture-output pip wheel . --no-deps --wheel-dir $Dist -q
}
$wheel = Get-ChildItem $Dist -Filter "fibre_planning-*.whl" | Sort-Object LastWriteTime -Descending | Select-Object -First 1
Write-Host "    $($wheel.Name)"

# --- 2. QGIS plugin zip -----------------------------------------------------------
$pluginDir = Join-Path $Root "qgis_plugin\fibre_planning_qgis"
$version = (Select-String -Path (Join-Path $pluginDir "metadata.txt") -Pattern '^version=(.+)$').Matches[0].Groups[1].Value
$zip = Join-Path $Dist "fibre_planning_qgis-$version.zip"
Write-Host "==> build QGIS plugin zip" -ForegroundColor Cyan
$staging = Join-Path ([IO.Path]::GetTempPath()) "fibre_planning_qgis_$([guid]::NewGuid().ToString('N'))"
# QGIS expects the plugin folder at the top level of the zip
Copy-Item $pluginDir (Join-Path $staging "fibre_planning_qgis") -Recurse
Get-ChildItem $staging -Recurse -Directory -Filter "__pycache__" | Remove-Item -Recurse -Force
if (Test-Path $zip) { Remove-Item $zip }
Compress-Archive -Path (Join-Path $staging "fibre_planning_qgis") -DestinationPath $zip
Remove-Item $staging -Recurse -Force
Write-Host "    $(Split-Path $zip -Leaf)"

if ($NoPublish) { return }

# --- 3. publish to the private index ------------------------------------------------
$envValues = Read-DotEnv
$port = if ($envValues["PYPI_PORT"]) { $envValues["PYPI_PORT"] } else { "8081" }
$user = $envValues["PYPI_USER"]
$password = $envValues["PYPI_PASSWORD"]
if (-not $user -or -not $password) { throw "PYPI_USER / PYPI_PASSWORD missing from .env" }

# htpasswd for the index, hashed with bcrypt inside the pypiserver image (passlib)
$htpasswd = Join-Path $Root "data\pypi\htpasswd"
New-Item -ItemType Directory -Force -Path (Split-Path $htpasswd) | Out-Null
Invoke-Checked "write htpasswd" {
    $hash = docker run --rm --entrypoint python -e "PW=$password" pypiserver/pypiserver:v2.3.2 `
        -c "import os; from passlib.hash import bcrypt; print(bcrypt.hash(os.environ['PW']))"
    "${user}:$hash" | Set-Content -Path $htpasswd -Encoding ascii -NoNewline
}
Invoke-Checked "start package index" { docker compose --profile packages up -d pypi }
$indexUrl = "http://127.0.0.1:$port"
for ($i = 0; $i -lt 30; $i++) {
    try { Invoke-WebRequest "$indexUrl/simple/" -UseBasicParsing -TimeoutSec 2 | Out-Null; break } catch { Start-Sleep 1 }
}

# Credentials go to twine through environment variables, never on the command line
$env:TWINE_USERNAME = $user
$env:TWINE_PASSWORD = $password
try {
    # Published versions are immutable (as in Artifactory): skip if this one is already there
    $listing = (Invoke-WebRequest "$indexUrl/simple/fibre-planning/" -UseBasicParsing -ErrorAction SilentlyContinue).Content
    if ($listing -and $listing.Contains($wheel.Name)) {
        Write-Host "==> $($wheel.Name) already on the index: not re-uploaded (bump the version to publish)" -ForegroundColor Yellow
    } else {
        Invoke-Checked "twine upload" {
            conda run -n fibre --no-capture-output twine upload --repository-url "$indexUrl/" --non-interactive $wheel.FullName
        }
    }
} finally {
    Remove-Item Env:TWINE_USERNAME, Env:TWINE_PASSWORD -ErrorAction SilentlyContinue
}

$check = Join-Path ([IO.Path]::GetTempPath()) "fibre_download_check"
Remove-Item $check -Recurse -Force -ErrorAction SilentlyContinue
Invoke-Checked "download back from the index" {
    conda run -n fibre --no-capture-output pip download fibre-planning --no-deps `
        --index-url "$indexUrl/simple/" --dest $check -q
}
Get-ChildItem $check | ForEach-Object { Write-Host "    downloaded $($_.Name) from $indexUrl" -ForegroundColor Green }
Remove-Item $check -Recurse -Force
