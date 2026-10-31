$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
if (-not (Get-Command python -ErrorAction SilentlyContinue)) { throw 'Instala Python 3.11 o posterior y vuelve a ejecutar.' }
if (-not (Get-Command node -ErrorAction SilentlyContinue)) { throw 'Instala Node.js 20 o posterior y vuelve a ejecutar.' }
& python -c "import sys; assert sys.version_info >= (3,11), 'Se requiere Python 3.11 o posterior'"
if ($LASTEXITCODE -ne 0) { throw 'Version de Python no compatible.' }
& python -m venv .venv
if ($LASTEXITCODE -ne 0) { throw 'No se pudo crear el entorno Python.' }
$localPython = Join-Path $PSScriptRoot '.venv/Scripts/python.exe'
& $localPython -m pip install -r requirements.txt
if ($LASTEXITCODE -ne 0) { throw 'No se pudieron instalar las dependencias Python.' }
& npm.cmd ci --ignore-scripts --no-fund
if ($LASTEXITCODE -ne 0) { throw 'No se pudieron instalar las dependencias Node.' }
$runtimeConfig = @{python=$localPython;node=(Get-Command node).Source} | ConvertTo-Json
[System.IO.File]::WriteAllText((Join-Path $PSScriptRoot 'runtime.json'), $runtimeConfig, [System.Text.UTF8Encoding]::new($false))
Write-Host 'Instalacion completa. Abre iniciar.cmd.'
