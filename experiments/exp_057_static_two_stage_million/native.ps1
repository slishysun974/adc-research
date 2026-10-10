param([Parameter(Mandatory=$true)][string]$Output, [switch]$Preflight)
$ErrorActionPreference='Stop'
$env:TMP='D:\ADC\tmp'; $env:TEMP='D:\ADC\tmp'
$kernelPath=Join-Path $PSScriptRoot 'Kernel.cs'
Add-Type -Path $kernelPath -CompilerOptions '/optimize+'
$protocol=Get-Content -Raw -LiteralPath (Join-Path $Output 'protocol.json') | ConvertFrom-Json
if($Preflight) {
    [Adc057]::Edges((Join-Path $Output 'pwl_edges.bin'))
    [Adc057]::GateEdges((Join-Path $Output 'gate_edges.bin'))
    [Adc057]::SarEdges((Join-Path $Output 'sar_edges.bin'))
    Get-FileHash -LiteralPath $kernelPath,(Join-Path $PSScriptRoot 'common.py'),(Join-Path $PSScriptRoot 'verify.py') |
        Select-Object Path,Hash | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $Output 'preflight_source_hashes.json') -Encoding utf8
}
foreach($case in $protocol.cases) {
    if($Preflight) {
        [Adc057]::Grid((Join-Path $Output ($case.name+'_grid.bin')),[int]$protocol.verification.model_grid_points,
            [double]$case.stage1[0],[double]$case.stage1[1],[double]$case.stage2[0],[double]$case.stage2[1])
    }
    foreach($method in $protocol.methods) {
        $windows=if($Preflight) {64} else {[int]$method.training_windows}
        $seeds=if($Preflight) {@($protocol.seeds[0])} else {$protocol.seeds}
        $probeSet=[System.Collections.Generic.HashSet[int]]::new()
        for($w=0;$w -lt [Math]::Min(32,$windows);$w++) { [void]$probeSet.Add($w) }
        foreach($checkpoint in $method.checkpoint_windows) {
            if($checkpoint -gt 0 -and $checkpoint -le $windows) {
                for($w=[Math]::Max(0,$checkpoint-32);$w -lt $checkpoint;$w++) { [void]$probeSet.Add($w) }
            }
        }
        [int[]]$probeWindows=@($probeSet | Sort-Object)
        foreach($seed in $seeds) {
            $name=$case.name+'_'+$method.name
            $result=[Adc057]::Run($Output,$name,[ulong]$seed,
                [double]$case.stage1[0],[double]$case.stage1[1],
                [double]$case.stage2[0],[double]$case.stage2[1],
                $windows,[int]$method.selected,[int]$method.multiplier,$probeWindows)
            $result | ConvertTo-Json -Depth 10 | Set-Content -LiteralPath (Join-Path $Output ($name+'_'+$seed+'.json')) -Encoding utf8
            Write-Output ($name+' seed '+$seed+': observations/stage='+$result.GeneratedSamples+', overloads='+$result.PhysicalOverloads+', clips='+($result.ContinuousCoefficientClips+$result.QuantizedCoefficientClips))
        }
    }
}
