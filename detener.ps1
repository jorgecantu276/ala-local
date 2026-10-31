$ErrorActionPreference = 'Stop'
$pidFile = Join-Path $PSScriptRoot 'data/server.pid'
if (-not (Test-Path -LiteralPath $pidFile)) { Write-Host 'No hay un proceso registrado.'; exit }
$serverProcessId = [int](Get-Content -Raw -LiteralPath $pidFile)
$processInfo = Get-CimInstance Win32_Process -Filter "ProcessId=$serverProcessId" -ErrorAction SilentlyContinue
$expectedScript = Join-Path $PSScriptRoot 'server.py'
if ($processInfo -and $processInfo.CommandLine -and $processInfo.CommandLine.IndexOf($expectedScript, [StringComparison]::OrdinalIgnoreCase) -ge 0) {
    Stop-Process -Id $serverProcessId
    Remove-Item -LiteralPath $pidFile
    Write-Host 'Ala Local detenido. Las reservas permanecen guardadas.'
} else { Write-Host 'El proceso registrado ya no corresponde a este servidor. No se detuvo ningun otro proceso.' }
