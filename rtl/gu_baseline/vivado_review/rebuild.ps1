param(
    [Parameter(Mandatory=$true)][string]$NewRun,
    [string]$Vivado='D:\programs\2026.1\Vivado\bin\vivado.bat',
    [string]$Python='python'
)
$ErrorActionPreference='Stop'
if (Test-Path -LiteralPath $NewRun) {throw 'Choose a new run directory; existing evidence is preserved'}
New-Item -ItemType Directory -Path $NewRun | Out-Null
foreach ($sub in @('sources','vectors')) {Copy-Item -LiteralPath (Join-Path $PSScriptRoot $sub) -Destination $NewRun -Recurse}
foreach ($name in @('build.tcl','manifest.json','review_protocol.json','validate.py')) {
    Copy-Item -LiteralPath (Join-Path $PSScriptRoot $name) -Destination $NewRun
}
foreach ($sub in @('reports','netlists','checkpoints','schematics','logs','sim')) {New-Item -ItemType Directory -Path (Join-Path $NewRun $sub) | Out-Null}
$newRoot=(Resolve-Path -LiteralPath $NewRun).Path
Push-Location -LiteralPath (Split-Path -Parent $Vivado)
try {
    & $Vivado -mode batch -notrace -journal (Join-Path $newRoot 'logs\vivado.jou') -log (Join-Path $newRoot 'logs\vivado.log') -source (Join-Path $newRoot 'build.tcl')
    if ($LASTEXITCODE -ne 0) {throw 'Vivado failed; see retained logs'}
} finally {Pop-Location}
if (Get-Command $Python -ErrorAction SilentlyContinue) {
    & $Python (Join-Path $newRoot 'validate.py') $newRoot --snapshot-only
    if ($LASTEXITCODE -ne 0) {throw 'Actual simulation marker or frozen-copy validation failed'}
} else {
    Write-Output 'Vivado checked PASS markers and the negative control. Optional independent summary: python validate.py <new run> --snapshot-only'
}
