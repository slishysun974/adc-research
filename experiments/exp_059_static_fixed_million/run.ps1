param([Parameter(Mandatory=$true)][string]$Output,[switch]$Preflight,[string]$PreflightPath)
$ErrorActionPreference='Stop'
$rootPath=(Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$outputPath=[IO.Path]::GetFullPath($Output)
$allowedPath=Join-Path $rootPath 'artifacts\runs\EXP_059'
if(-not $outputPath.StartsWith($allowedPath+[IO.Path]::DirectorySeparatorChar)) {throw 'Output outside EXP_059'}
if(Test-Path -LiteralPath $outputPath){throw 'Refusing overwrite'}
if(-not $Preflight) {
    if(-not $PreflightPath){throw 'PreflightPath required'}
    $verification=Get-Content -Raw -LiteralPath (Join-Path $PreflightPath 'verification.json') | ConvertFrom-Json
    if(-not $verification.passed){throw 'Preflight not passed'}
    foreach($item in (Get-Content -Raw -LiteralPath (Join-Path $PreflightPath 'source_hashes.json') | ConvertFrom-Json)) {
        if((Get-FileHash -LiteralPath $item.Path).Hash -ne $item.Hash){throw 'Preflight source changed'}
    }
}
New-Item -ItemType Directory -Path $outputPath | Out-Null
$env:TMP=Join-Path $rootPath 'tmp';$env:TEMP=$env:TMP
Copy-Item -LiteralPath (Join-Path $PSScriptRoot 'protocol.json') -Destination (Join-Path $outputPath 'protocol.json')
$protocol=Get-Content -Raw -LiteralPath (Join-Path $outputPath 'protocol.json') | ConvertFrom-Json
$sourcePath=Join-Path $rootPath $protocol.source_protocol
Copy-Item -LiteralPath $sourcePath -Destination (Join-Path $outputPath 'source_protocol.json')
$source=Get-Content -Raw -LiteralPath $sourcePath | ConvertFrom-Json
$files=@(Get-ChildItem -LiteralPath (Join-Path $rootPath 'src') -Recurse -File | Where-Object Extension -eq '.py')
$files+=@(Get-ChildItem -LiteralPath (Join-Path $rootPath 'rtl') -Recurse -File | Where-Object Extension -in '.v','.sv')
$files+=@(Get-ChildItem -LiteralPath $PSScriptRoot -File)
$files+=@(Get-ChildItem -LiteralPath (Join-Path $rootPath 'experiments\exp_057_static_two_stage_million') -File)
$files+=Get-Item -LiteralPath (Join-Path $rootPath 'configs\architectures\gu_behavioral_v1.yaml')
$frozen=@($files | Get-FileHash | Select-Object Path,Hash)
$frozen | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $outputPath 'source_hashes.json') -Encoding utf8
Add-Type -Path (Join-Path $rootPath 'experiments\exp_057_static_two_stage_million\Kernel.cs'),(Join-Path $PSScriptRoot 'Kernel.cs') -CompilerOptions '/optimize+'
if($Preflight){[Adc059]::Edges($outputPath)}
$baselinePath=Join-Path $rootPath $protocol.baseline_run
foreach($case in $source.cases) {
    foreach($method in $source.methods) {
        $windows=if($Preflight){64}else{[int]$method.training_windows}
        $seeds=if($Preflight){@($source.seeds[0])}else{$source.seeds}
        $keep=[Collections.Generic.HashSet[int]]::new()
        for($w=0;$w -lt [Math]::Min(8,$windows);$w++){[void]$keep.Add($w)}
        $checks=if($Preflight){@($windows)}else{$method.checkpoint_windows}
        foreach($checkpoint in $checks) {
            if($checkpoint -gt 0 -and $checkpoint -le $windows) {
                for($w=[Math]::Max(0,$checkpoint-8);$w -lt $checkpoint;$w++){[void]$keep.Add($w)}
            }
        }
        [int[]]$probeWindows=@($keep | Sort-Object)
        foreach($seed in $seeds) {
            $name=$case.name+'_'+$method.name
            $result=[Adc059]::Run($outputPath,$baselinePath,$name,[ulong]$seed,[double]$case.stage1[0],[double]$case.stage1[1],
                [double]$case.stage2[0],[double]$case.stage2[1],$windows,[int]$method.selected,[int]$method.multiplier,$probeWindows,(-not $Preflight))
            $result | ConvertTo-Json -Depth 12 | Set-Content -LiteralPath (Join-Path $outputPath ($name+'_'+$seed+'.json')) -Encoding utf8
            Write-Output ($name+' seed '+$seed+': windows='+$windows+', baseline values checked='+$result.BaselineStatesChecked)
        }
    }
}
foreach($item in $frozen){if((Get-FileHash -LiteralPath $item.Path).Hash -ne $item.Hash){throw 'Source changed during run'}}
'Source hashes unchanged' | Set-Content -LiteralPath (Join-Path $outputPath 'completed.txt') -Encoding utf8
