param([Parameter(Mandatory=$true)][string]$Output,[switch]$Preflight,[string]$PreflightPath)
$ErrorActionPreference='Stop'
$rootPath=(Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$outputPath=[IO.Path]::GetFullPath($Output)
$allowedPath=Join-Path $rootPath 'artifacts\runs\EXP_062'
if(-not $outputPath.StartsWith($allowedPath+[IO.Path]::DirectorySeparatorChar)){throw 'Output outside EXP_062'}
if(Test-Path -LiteralPath $outputPath){throw 'Refusing overwrite'}
if(-not $Preflight){
    if(-not $PreflightPath){throw 'PreflightPath required'}
    $check=Get-Content -Raw -LiteralPath (Join-Path $PreflightPath 'verification.json') | ConvertFrom-Json
    if(-not $check.passed){throw 'Preflight not passed'}
    foreach($item in (Get-Content -Raw -LiteralPath (Join-Path $PreflightPath 'source_hashes.json') | ConvertFrom-Json)){
        if((Get-FileHash -LiteralPath $item.Path).Hash -ne $item.Hash){throw 'Preflight source changed'}
    }
}
New-Item -ItemType Directory -Path $outputPath | Out-Null
$env:TMP=Join-Path $rootPath 'tmp';$env:TEMP=$env:TMP
Copy-Item -LiteralPath (Join-Path $PSScriptRoot 'protocol.json') -Destination (Join-Path $outputPath 'protocol.json')
$protocol=Get-Content -Raw -LiteralPath (Join-Path $outputPath 'protocol.json') | ConvertFrom-Json
Copy-Item -LiteralPath (Join-Path $rootPath $protocol.source_protocol) -Destination (Join-Path $outputPath 'source_protocol.json')
$files=@()
foreach($directory in @('src','rtl','experiments\exp_057_static_two_stage_million','experiments\exp_058_static_fixed_preflight','experiments\exp_059_static_fixed_million','experiments\exp_060_static_auxiliary_preflight','experiments\exp_061_static_auxiliary_million','experiments\exp_062_same_input_background')){
    $files+=@(Get-ChildItem -LiteralPath (Join-Path $rootPath $directory) -Recurse -File | Where-Object { $_.Extension -in '.py','.cs','.ps1','.json','.md','.sv','.v' -and $_.FullName -notmatch '__pycache__' })
}
$files+=Get-Item -LiteralPath (Join-Path $rootPath 'configs\architectures\gu_behavioral_v1.yaml')
$frozen=@($files | Get-FileHash | Select-Object Path,Hash)
$frozen | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $outputPath 'source_hashes.json') -Encoding utf8
@{PSVersion=$PSVersionTable.PSVersion.ToString();Runtime=[System.Runtime.InteropServices.RuntimeInformation]::FrameworkDescription;StartedUTC=[DateTime]::UtcNow.ToString('o')} | ConvertTo-Json | Set-Content (Join-Path $outputPath 'environment.json')
try{
    Add-Type -Path (Join-Path $rootPath 'experiments\exp_057_static_two_stage_million\Kernel.cs'),(Join-Path $rootPath 'experiments\exp_059_static_fixed_million\Kernel.cs'),(Join-Path $rootPath 'experiments\exp_061_static_auxiliary_million\Kernel.cs'),(Join-Path $PSScriptRoot 'Kernel.cs') -CompilerOptions '/optimize+'
    $n=[int]$protocol.input.samples_per_block
    [double[]]$tone=[double[]]::new($n)
    for($i=0;$i -lt $n;$i++){$tone[$i]=[double]$protocol.input.amplitude*[Math]::Sin(2*[Math]::PI*[int]$protocol.input.tone_bin*$i/$n)}
    $writer=[IO.BinaryWriter]::new([IO.File]::Open((Join-Path $outputPath 'tone.bin'),[IO.FileMode]::CreateNew))
    try{foreach($v in $tone){$writer.Write($v)}}finally{$writer.Dispose()}
    $windows=if($Preflight){[int]$protocol.preflight.windows}else{[int]$protocol.budget.windows_per_path}
    $seeds=if($Preflight){@($protocol.seeds[0])}else{$protocol.seeds}
    $keep=[Collections.Generic.HashSet[int]]::new()
    if($Preflight){for($w=0;$w -lt $windows;$w++){[void]$keep.Add($w)}}else{
        foreach($b in $protocol.verification.long_probe_blocks){for($j=0;$j -lt 4;$j++){[void]$keep.Add([int]$b*($n/120)+$j)}}
        for($w=$windows-4;$w -lt $windows;$w++){[void]$keep.Add($w)}
    }
    [int[]]$probes=@($keep | Sort-Object)
    foreach($case in $protocol.cases){foreach($seed in $seeds){
        $result=[Adc062]::Run($outputPath,$case.name,[ulong]$seed,[double]$case.stage1[0],[double]$case.stage1[1],[double]$case.stage2[0],[double]$case.stage2[1],$tone,$windows,$probes)
        $result | ConvertTo-Json -Depth 12 | Set-Content -LiteralPath (Join-Path $outputPath ($case.name+'_'+$seed+'.json')) -Encoding utf8
        if(($result.CoefficientClips | Measure-Object -Sum).Sum -ne 0 -or ($result.OutputClips | Measure-Object -Sum).Sum -ne 0){throw ('clipping '+$case.name)}
        Write-Output ($case.name+' seed '+$seed+': actual conversions='+$result.Conversions+', both methods completed at '+[DateTime]::UtcNow.ToString('o'))
    }}
    foreach($item in $frozen){if((Get-FileHash -LiteralPath $item.Path).Hash -ne $item.Hash){throw 'Source changed during run'}}
    'Source hashes unchanged' | Set-Content -LiteralPath (Join-Path $outputPath 'completed.txt') -Encoding utf8
}catch{$_ | Out-String | Set-Content -LiteralPath (Join-Path $outputPath 'run_failure.txt');throw}
