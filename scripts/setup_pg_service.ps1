<#
.SYNOPSIS
    Write a PostgreSQL service entry "fibre" for QGIS and psql, from .env.

.DESCRIPTION
    QGIS projects in this repo connect with "service=fibre" so they never
    contain passwords. This script adds (or replaces) that entry in your
    per-user service file, %APPDATA%\postgresql\.pg_service.conf, using the
    read-only role from .env. Other entries in the file are kept.

.EXAMPLE
    .\scripts\setup_pg_service.ps1
#>
[CmdletBinding()]
param(
    [string]$EnvFile = (Join-Path $PSScriptRoot "..\.env"),
    [string]$ServiceName = "fibre"
)
$ErrorActionPreference = "Stop"

if (-not (Test-Path $EnvFile)) { throw "No .env at $EnvFile - copy .env.example first." }

# Read KEY=VALUE lines, ignoring comments and trailing "# ..." notes
$settings = @{}
foreach ($line in Get-Content $EnvFile) {
    if ($line -match '^\s*([A-Z_]+)\s*=\s*([^#]*?)\s*(#.*)?$') { $settings[$Matches[1]] = $Matches[2] }
}
foreach ($key in "POSTGRES_DB", "API_DB_USER", "API_DB_PASSWORD") {
    if (-not $settings[$key]) { throw "$key missing from $EnvFile" }
}
$hostName = if ($settings["POSTGRES_HOST"]) { $settings["POSTGRES_HOST"] } else { "127.0.0.1" }
$port = if ($settings["POSTGRES_PORT"]) { $settings["POSTGRES_PORT"] } else { "5433" }

$entry = @(
    "[$ServiceName]",
    "host=$hostName",
    "port=$port",
    "dbname=$($settings['POSTGRES_DB'])",
    "user=$($settings['API_DB_USER'])",
    "password=$($settings['API_DB_PASSWORD'])"
)

$dir = Join-Path $env:APPDATA "postgresql"
$file = Join-Path $dir ".pg_service.conf"
New-Item -ItemType Directory -Force -Path $dir | Out-Null

# Keep every other service section, replace ours
$kept = @()
if (Test-Path $file) {
    $skip = $false
    foreach ($line in Get-Content $file) {
        if ($line -match '^\s*\[(.+)\]\s*$') { $skip = ($Matches[1] -eq $ServiceName) }
        if (-not $skip) { $kept += $line }
    }
}
($kept + "" + $entry) -join "`r`n" | Set-Content -Path $file -Encoding ascii

# Only the current user should be able to read the password
icacls $file /inheritance:r /grant:r "$($env:USERNAME):(R,W)" | Out-Null
Write-Host "Service [$ServiceName] written to $file (read-only role $($settings['API_DB_USER']))"
