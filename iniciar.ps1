param([switch]$NoBrowser)
$ErrorActionPreference = 'Stop'
$localUrl = 'http://127.0.0.1:8877'
try {
    $health = Invoke-RestMethod -Uri "$localUrl/api/health" -TimeoutSec 2
    if ($health.app -eq 'ala-local') { if (-not $NoBrowser) { Start-Process $localUrl }; exit 0 }
    throw 'El puerto 8877 esta ocupado por otra aplicacion.'
} catch {
    if ($_.Exception.Message -like '*otra aplicacion*') { throw }
}
$configFile = Join-Path $PSScriptRoot 'runtime.json'
if (Test-Path -LiteralPath $configFile) { $pythonPath = (Get-Content -Raw -LiteralPath $configFile | ConvertFrom-Json).python }
elseif (Test-Path -LiteralPath (Join-Path $PSScriptRoot '.venv/Scripts/python.exe')) { $pythonPath = Join-Path $PSScriptRoot '.venv/Scripts/python.exe' }
else { $pythonPath = (Get-Command python -ErrorAction Stop).Source }
$dataFolder = Join-Path $PSScriptRoot 'data'
New-Item -ItemType Directory -Force -Path $dataFolder | Out-Null
$serverPath = Join-Path $PSScriptRoot 'server.py'
$serverArgs = '"' + $serverPath + '"'
$process = Start-Process -FilePath $pythonPath -ArgumentList $serverArgs -WorkingDirectory $PSScriptRoot -WindowStyle Hidden -RedirectStandardOutput (Join-Path $dataFolder 'server.log') -RedirectStandardError (Join-Path $dataFolder 'server-error.log') -PassThru
$process.Id | Set-Content -LiteralPath (Join-Path $dataFolder 'server.pid')
for ($attempt=0; $attempt -lt 30; $attempt++) {
    Start-Sleep -Milliseconds 250
    try { $health = Invoke-RestMethod -Uri "$localUrl/api/health" -TimeoutSec 1; if ($health.app -eq 'ala-local') { if (-not $NoBrowser) { Start-Process $localUrl }; exit 0 } } catch { }
}
throw 'No se pudo iniciar. Revisa data/server-error.log o ejecuta instalar.ps1.'
