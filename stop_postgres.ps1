$ErrorActionPreference = 'Stop'
$runtime = Join-Path $PSScriptRoot '.tools'
$asciiLink = Join-Path $env:TEMP 'lr1_python_tools_20261009'
if (-not (Test-Path -LiteralPath $asciiLink)) { throw 'Путь сервера не найден.' }
if ((Get-Item -LiteralPath $asciiLink).Target -ne $runtime) { throw 'Путь относится к другому каталогу.' }
& (Join-Path $asciiLink 'pgsql\bin\pg_ctl.exe') -D (Join-Path $asciiLink 'pgdata') -m fast -w stop
