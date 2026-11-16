$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$venvPython = Join-Path $env:USERPROFILE '.venv\Scripts\python.exe'
& $venvPython -m pytest -q --basetemp .pytest-tmp
exit $LASTEXITCODE
