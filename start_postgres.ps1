$ErrorActionPreference = 'Stop'
$runtime = Join-Path $PSScriptRoot '.tools'
$asciiLink = Join-Path $env:TEMP 'lr1_python_tools_20261009'
if (-not (Test-Path -LiteralPath $asciiLink)) {
    New-Item -ItemType Junction -Path $asciiLink -Target $runtime | Out-Null
}
if ((Get-Item -LiteralPath $asciiLink).Target -ne $runtime) {
    throw 'Временный путь принадлежит другому каталогу. Запуск остановлен.'
}
$server = Join-Path $asciiLink 'pgsql\bin\pg_ctl.exe'
$data = Join-Path $asciiLink 'pgdata'
& $server -D $data -l (Join-Path $asciiLink 'postgres.log') -o '-p 55432 -h 127.0.0.1' -w start
