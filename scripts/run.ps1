<#
.SYNOPSIS
    Task runner for the fibre planning project (Windows / PowerShell 5.1+).

.DESCRIPTION
    One entry point for the common workflows, so nobody has to remember the
    order of docker, alembic, kedro and the publishers. Every task stops at
    the first failing command.

.PARAMETER Task
    setup    create .env (random passwords), conda env and pg_service entry
    up       start PostGIS, the API and GeoServer (docker compose)
    migrate  apply database migrations (alembic upgrade head)
    pipeline run the Kedro pipeline
    publish  publish layers to GeoServer and rebuild the QGIS project
    test     lint, type-check and run the test suite
    all      up, migrate, pipeline, publish, test
    down     stop the containers (data volumes are kept)
    status   show container health and the latest pipeline run

.EXAMPLE
    .\scripts\run.ps1 all
#>
[CmdletBinding()]
param(
    [Parameter(Position = 0)]
    [ValidateSet("setup", "up", "migrate", "pipeline", "publish", "test", "all", "down", "status")]
    [string]$Task = "status"
)
$ErrorActionPreference = "Stop"
$Root = Resolve-Path (Join-Path $PSScriptRoot "..")
Set-Location $Root

$CondaEnv = "fibre"
$QgisPython = Get-ChildItem "C:\Program Files\QGIS *\bin\python-qgis*.bat" -ErrorAction SilentlyContinue |
    Sort-Object FullName -Descending | Select-Object -First 1

function Invoke-Step([string]$Name, [scriptblock]$Command) {
    Write-Host "==> $Name" -ForegroundColor Cyan
    $started = Get-Date
    # Native tools (conda, docker) write warnings to stderr; judge them by exit code only
    $ErrorActionPreference = "Continue"
    & $Command
    if ($LASTEXITCODE -ne 0) { throw "$Name failed (exit code $LASTEXITCODE)" }
    Write-Host ("    done in {0:N1} s" -f ((Get-Date) - $started).TotalSeconds) -ForegroundColor DarkGray
}

function Invoke-InEnv([string[]]$Arguments) {
    # conda run keeps the env's variables (PROJ/GDAL paths, Kedro logging)
    & conda run -n $CondaEnv --no-capture-output @Arguments
}

function New-Secret {
    $bytes = New-Object byte[] 24
    [Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($bytes)
    return [Convert]::ToBase64String($bytes).Replace("+", "-").Replace("/", "_").TrimEnd("=")
}

function Wait-Healthy([string]$Service, [int]$TimeoutSeconds = 180) {
    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    while ((Get-Date) -lt $deadline) {
        $health = docker inspect -f "{{.State.Health.Status}}" (docker compose ps -q $Service) 2>$null
        if ($health -eq "healthy") { return }
        Start-Sleep -Seconds 3
    }
    throw "$Service did not become healthy within $TimeoutSeconds s"
}

$tasks = @{
    setup    = {
        if (-not (Test-Path .env)) {
            $text = Get-Content .env.example -Raw
            # [regex]::Replace with a script block works in Windows PowerShell 5.1 too
            [regex]::Replace($text, "change-me-[a-z]+", { New-Secret }) | Set-Content .env -Encoding ascii -NoNewline
            Write-Host "Created .env with random passwords"
        }
        $envs = conda env list
        if (-not ($envs -match "^$CondaEnv\s")) {
            Invoke-Step "conda env create" { conda env create -f environment.yml }
        }
        Invoke-Step "pg_service entry" { & "$PSScriptRoot\setup_pg_service.ps1"; $global:LASTEXITCODE = 0 }
    }
    up       = {
        Invoke-Step "docker compose up" { docker compose up -d --build }
        Wait-Healthy postgis; Wait-Healthy api; Wait-Healthy geoserver
    }
    migrate  = { Invoke-Step "alembic upgrade head" { Invoke-InEnv @("alembic", "upgrade", "head") } }
    pipeline = { Invoke-Step "kedro run" { Invoke-InEnv @("kedro", "run") } }
    publish  = {
        Invoke-Step "GeoServer publish" { Invoke-InEnv @("python", "-m", "fibre_planning.geoserver") }
        if ($QgisPython) {
            Invoke-Step "QGIS project" { & $QgisPython.FullName qgis_project\build_project.py }
        } else {
            Write-Warning "QGIS not found: skipped the QGIS project"
        }
    }
    test     = {
        Invoke-Step "ruff" { Invoke-InEnv @("ruff", "check", "src", "tests", "migrations") }
        Invoke-Step "mypy" { Invoke-InEnv @("mypy", "src") }
        Invoke-Step "pytest" { Invoke-InEnv @("pytest", "-q") }
    }
    down     = { Invoke-Step "docker compose down" { docker compose down } }
    status   = {
        docker compose ps --format "table {{.Service}}	{{.Status}}	{{.Ports}}"
        Invoke-Step "latest pipeline runs" { Invoke-InEnv @("python", "-m", "fibre_planning.status") }
    }
}

if ($Task -eq "all") {
    foreach ($t in "up", "migrate", "pipeline", "publish", "test") { & $tasks[$t] }
} else {
    & $tasks[$Task]
}
Write-Host "Task '$Task' finished." -ForegroundColor Green
