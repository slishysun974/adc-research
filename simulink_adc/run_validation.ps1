param(
    [string]$Python = '',
    [string]$Matlab = 'matlab',
    [string]$RunDirectory = ''
)
$ErrorActionPreference = 'Stop'
$modelFolder = $PSScriptRoot
$projectFolder = Split-Path -Parent $modelFolder
if (-not $Python) {
    $candidates = @(
        (Join-Path $env:USERPROFILE '.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe'),
        'python'
    )
    foreach ($candidate in $candidates) {
        try {
            & $candidate -c 'import numpy' 2>$null
            if ($LASTEXITCODE -eq 0) { $Python = $candidate; break }
        } catch { }
    }
    if (-not $Python) { throw 'Specify -Python with a Python >=3.10 containing numpy and PyYAML.' }
}
if (-not $RunDirectory) {
    $stamp = Get-Date -Format 'yyyyMMdd_HHmmss'
    $RunDirectory = Join-Path $modelFolder "validation_runs/$stamp"
}
$runFolder = [System.IO.Path]::GetFullPath($RunDirectory)
if (Test-Path -LiteralPath $runFolder) { throw "Run directory already exists: $runFolder" }
New-Item -ItemType Directory -Path $runFolder | Out-Null
$referenceFolder = Join-Path $runFolder 'reference'
$actualFolder = Join-Path $runFolder 'simulink'
& $Python (Join-Path $modelFolder 'python_reference.py') export $referenceFolder 2>&1 |
    Tee-Object -FilePath (Join-Path $runFolder 'python_export.log')
if ($LASTEXITCODE -ne 0) { throw 'Python reference export failed.' }
function MatlabLiteral([string]$value) { return "'" + $value.Replace("'", "''") + "'" }
$cacheFolder = Join-Path $runFolder 'cache'
$codeFolder = Join-Path $runFolder 'codegen'
$matlabScript = @"
addpath($(MatlabLiteral $modelFolder));
Simulink.fileGenControl('set','CacheFolder',$(MatlabLiteral $cacheFolder),'CodeGenFolder',$(MatlabLiteral $codeFolder),'createDir',true);
build_adc_model($(MatlabLiteral $referenceFolder));
run_adc_validation($(MatlabLiteral $referenceFolder),$(MatlabLiteral $actualFolder));
"@
$scriptFile = Join-Path $runFolder 'run_matlab.m'
Set-Content -LiteralPath $scriptFile -Value $matlabScript -Encoding utf8
& $Matlab -batch "run($(MatlabLiteral $scriptFile))" 2>&1 |
    Tee-Object -FilePath (Join-Path $runFolder 'matlab.log')
if ($LASTEXITCODE -ne 0) { throw 'MATLAB/Simulink validation failed; logs retained.' }
& $Python (Join-Path $modelFolder 'python_reference.py') compare $referenceFolder $actualFolder (Join-Path $runFolder 'parity.json') 2>&1 |
    Tee-Object -FilePath (Join-Path $runFolder 'comparison.log')
if ($LASTEXITCODE -ne 0) { throw 'Parity check failed; failed samples and logs retained.' }
Write-Host "Verified run saved at $runFolder"
