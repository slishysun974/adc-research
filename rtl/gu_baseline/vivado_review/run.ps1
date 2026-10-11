param(
    [Parameter(Mandatory=$true)][string]$RunDirectory,
    [string]$Vivado = 'D:\programs\2026.1\Vivado\bin\vivado.bat',
    [string]$Python = 'python'
)
$ErrorActionPreference = 'Stop'
$reviewSource = $PSScriptRoot
& $Python (Join-Path $reviewSource 'prepare.py') $RunDirectory
if ($LASTEXITCODE -ne 0) { throw 'Review workspace preparation failed' }
$resolvedRun = (Resolve-Path -LiteralPath $RunDirectory).Path
# A writable ASCII directory avoids command-wrapper and locale path surprises.
$vivadoBin = Split-Path -Parent $Vivado
Push-Location -LiteralPath $vivadoBin
try {
    & $Vivado -mode batch -notrace -journal (Join-Path $resolvedRun 'logs\vivado.jou') -log (Join-Path $resolvedRun 'logs\vivado.log') -source (Join-Path $resolvedRun 'build.tcl')
    if ($LASTEXITCODE -ne 0) { throw "Vivado review failed ($LASTEXITCODE); inspect retained logs" }
} finally { Pop-Location }
& $Python (Join-Path $reviewSource 'validate.py') $resolvedRun
if ($LASTEXITCODE -ne 0) { throw 'Simulation evidence validation failed' }
