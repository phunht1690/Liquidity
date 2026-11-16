param(
    [ValidateSet('Status','Start','Stop','EnableAutostart','DisableAutostart')]
    [string]$Action = 'Status',
    [int]$Port = 8765
)
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$lopmPython = Join-Path $env:USERPROFILE '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $lopmPython)) { throw 'Chưa có Python trong môi trường dùng chung.' }
switch ($Action) {
    'Start' { & $lopmPython -X utf8 -B -m src.app.launcher --background --port $Port }
    'Stop' { & $lopmPython -X utf8 -B -m src.app.background --stop --port $Port }
    'EnableAutostart' { & $lopmPython -X utf8 -B -m src.app.background --install-autostart --port $Port }
    'DisableAutostart' { & $lopmPython -X utf8 -B -m src.app.background --remove-autostart --port $Port }
    'Status' { & $lopmPython -X utf8 -B -m src.app.background --status --port $Port }
}
exit $LASTEXITCODE
