param([int]$Port = 8765)
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$venvPython = Join-Path $env:USERPROFILE '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $venvPython)) {
    throw 'Chưa có môi trường dùng chung. Xem README.md để cài Python và môi trường.'
}
& $venvPython -m src.app.launcher --port $Port
exit $LASTEXITCODE
