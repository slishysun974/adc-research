param(
    [string]$Python = '',
    [string]$Matlab = 'matlab',
    [string]$Protocol = ''
)
$ErrorActionPreference = 'Stop'
$taskFolder = $PSScriptRoot
if (-not $Protocol) { $Protocol = Join-Path $taskFolder 'performance_protocol.json' }
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
    if (-not $Python) { throw 'Specify -Python with Python >=3.10 and NumPy/PyYAML.' }
}
$runFolder = Join-Path $taskFolder ('performance_runs\' + (Get-Date -Format 'yyyyMMdd_HHmmss'))
& $Python (Join-Path $taskFolder 'performance_demo.py') prepare $runFolder --protocol $Protocol
if ($LASTEXITCODE -ne 0) { throw 'Original-core reference/preflight failed; records preserved.' }
$matlabFolder = $taskFolder.Replace('\','/').Replace("'","''")
$matlabRun = $runFolder.Replace('\','/').Replace("'","''")
& $Matlab -batch "addpath('$matlabFolder'); Simulink.fileGenControl('set','CacheFolder',fullfile('$matlabRun','cache'),'CodeGenFolder',fullfile('$matlabRun','codegen'),'createDir',true); run_adc_performance('$matlabRun')" -logfile (Join-Path $runFolder 'matlab_simulation.log')
if ($LASTEXITCODE -ne 0) { throw 'Native Simulink run failed; records preserved.' }
& $Python (Join-Path $taskFolder 'performance_demo.py') analyze $runFolder
if ($LASTEXITCODE -ne 0) { throw 'Independent comparison failed; records preserved.' }
& $Matlab -batch "addpath('$matlabFolder'); verify_adc_performance_metrics('$matlabRun'); render_adc_performance('$matlabRun')" -logfile (Join-Path $runFolder 'matlab_figures.log')
if ($LASTEXITCODE -ne 0) { throw 'Scientific figure export failed; numerical records preserved.' }
Write-Output "Performance demo complete: $runFolder"
