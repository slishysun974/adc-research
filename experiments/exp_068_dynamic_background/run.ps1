param([Parameter(Mandatory=$true)][string]$Output,[switch]$Preflight,[string]$PreflightPath)
$ErrorActionPreference='Stop'
$rootPath=(Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$outputPath=[IO.Path]::GetFullPath($Output)
$allowedPath=Join-Path $rootPath 'artifacts\runs\EXP_068'
if(-not $outputPath.StartsWith($allowedPath+[IO.Path]::DirectorySeparatorChar)){throw 'Output outside EXP_068'}
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
if(-not $Preflight){
    Copy-Item -LiteralPath (Join-Path $PreflightPath 'verification.json') -Destination (Join-Path $outputPath 'accepted_preflight.json')
    Copy-Item -LiteralPath (Join-Path $PreflightPath 'source_hashes.json') -Destination (Join-Path $outputPath 'accepted_preflight_sources.json')
}
$env:TMP=Join-Path $rootPath 'tmp';$env:TEMP=$env:TMP
Copy-Item -LiteralPath (Join-Path $PSScriptRoot 'protocol.json') -Destination (Join-Path $outputPath 'protocol.json')
$protocol=Get-Content -Raw -LiteralPath (Join-Path $outputPath 'protocol.json') | ConvertFrom-Json
Copy-Item -LiteralPath (Join-Path $rootPath $protocol.source_protocol) -Destination (Join-Path $outputPath 'source_protocol.json')
$files=@()
foreach($directory in @('src','rtl','experiments\exp_057_static_two_stage_million','experiments\exp_058_static_fixed_preflight','experiments\exp_059_static_fixed_million','experiments\exp_060_static_auxiliary_preflight','experiments\exp_061_static_auxiliary_million','experiments\exp_062_same_input_background','experiments\exp_067_dynamic_history_preflight','experiments\exp_068_dynamic_background')){
    $files+=@(Get-ChildItem -LiteralPath (Join-Path $rootPath $directory) -Recurse -File | Where-Object { $_.Extension -in '.py','.cs','.ps1','.json','.md','.sv','.v' -and $_.FullName -notmatch '__pycache__' })
}
$files+=@(Get-ChildItem -LiteralPath (Join-Path $rootPath 'tests') -Filter 'test_dynamic*.py')
$files+=Get-Item -LiteralPath (Join-Path $rootPath 'configs\architectures\gu_behavioral_v1.yaml')
$frozen=@($files | Get-FileHash | Select-Object Path,Hash)
$frozen | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $outputPath 'source_hashes.json') -Encoding utf8
@{PSVersion=$PSVersionTable.PSVersion.ToString();Runtime=[System.Runtime.InteropServices.RuntimeInformation]::FrameworkDescription;StartedUTC=[DateTime]::UtcNow.ToString('o')} | ConvertTo-Json | Set-Content (Join-Path $outputPath 'environment.json')
try{
    Add-Type -Path (Join-Path $rootPath 'experiments\exp_057_static_two_stage_million\Kernel.cs'),(Join-Path $rootPath 'experiments\exp_059_static_fixed_million\Kernel.cs'),(Join-Path $rootPath 'experiments\exp_061_static_auxiliary_million\Kernel.cs'),(Join-Path $rootPath 'experiments\exp_062_same_input_background\Kernel.cs'),(Join-Path $PSScriptRoot 'Kernel.cs') -CompilerOptions '/optimize+'
    $n=[int]$protocol.input.samples_per_block
    $nominalPath=Join-Path $rootPath $protocol.nominal_folder
    $manifest=Get-Content -Raw -LiteralPath (Join-Path $nominalPath 'delivery_hashes.json') | ConvertFrom-Json -AsHashtable
    if(-not (Get-Content -Raw -LiteralPath (Join-Path $nominalPath 'delivery_validation.json') | ConvertFrom-Json).passed){throw 'Nominal delivery failed'}
    $names=@('tone.bin','protocol.json','verification.json','delivery_validation.json')
    foreach($case in $protocol.cases){foreach($seed in $protocol.seeds){
        $stem=$case.name+'_'+$seed
        foreach($suffix in @('.json','_words.bin','_outputs.bin','_point30_q22.bin','_full120_q22.bin')){$names+=$stem+$suffix}
    }}
    $checked=@{}
    foreach($name in $names){
        $hash=(Get-FileHash -LiteralPath (Join-Path $nominalPath $name)).Hash.ToLower()
        if($hash -ne $manifest[$name]){throw ('Nominal hash mismatch '+$name)}
        $checked[$name]=$hash
    }
    $checked | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $outputPath 'nominal_hashes.json') -Encoding utf8
    Copy-Item -LiteralPath (Join-Path $nominalPath 'delivery_hashes.json') -Destination (Join-Path $outputPath 'nominal_delivery_hashes.json')
    Copy-Item -LiteralPath (Join-Path $nominalPath 'tone.bin') -Destination (Join-Path $outputPath 'tone.bin')
    $shortPath=Join-Path $rootPath $protocol.short_reference
    if(-not (Get-Content -Raw -LiteralPath (Join-Path $shortPath 'delivery_validation.json') | ConvertFrom-Json).passed){throw 'EXP067 delivery failed'}
    $shortHashes=Get-Content -Raw -LiteralPath (Join-Path $shortPath 'source_hashes.json') | ConvertFrom-Json -AsHashtable
    foreach($name in $shortHashes.Keys){if((Get-FileHash -LiteralPath (Join-Path $rootPath $name)).Hash.ToLower() -ne $shortHashes[$name]){throw 'EXP067 source changed'}}
    $shortDelivery=Get-Content -Raw -LiteralPath (Join-Path $shortPath 'delivery_validation.json') | ConvertFrom-Json -AsHashtable
    $shortManifest=$shortDelivery['raw_record_files']
    foreach($name in $shortManifest.Keys){if((Get-FileHash -LiteralPath (Join-Path $shortPath $name)).Hash.ToLower() -ne $shortManifest[$name]){throw 'EXP067 data changed'}}
    $shortManifest | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $outputPath 'short_delivery_hashes.json') -Encoding utf8
    $reader=[IO.BinaryReader]::new([IO.File]::OpenRead((Join-Path $outputPath 'tone.bin')))
    [double[]]$tone=[double[]]::new($n)
    try{for($i=0;$i -lt $n;$i++){$tone[$i]=$reader.ReadDouble()}}finally{$reader.Dispose()}
    $windows=if($Preflight){[int]$protocol.preflight.windows}else{[int]$protocol.budget.windows_per_path}
    $seeds=if($Preflight){@($protocol.seeds[0])}else{$protocol.seeds}
    $keep=[Collections.Generic.HashSet[int]]::new()
    if($Preflight){for($w=0;$w -lt $windows;$w++){[void]$keep.Add($w)}}else{
        foreach($b in $protocol.verification.long_probe_blocks){for($j=0;$j -lt 4;$j++){[void]$keep.Add([int]$b*($n/120)+$j)}}
        for($w=$windows-4;$w -lt $windows;$w++){[void]$keep.Add($w)}
    }
    [int[]]$probes=@($keep | Sort-Object)
    foreach($case in $protocol.cases){foreach($seed in $seeds){foreach($phase in $protocol.phases){
        if(-not $Preflight -and $phase.name -eq 'static'){continue}
        $name=$case.name+'_'+$phase.name
        $result=[Adc068]::Run($outputPath,$name,[ulong]$seed,[double]$case.stage1[0],[double]$case.stage1[1],[double]$case.stage2[0],[double]$case.stage2[1],[double[]]$phase.amplification,[double]$phase.tracking,$tone,$windows,$probes)
        $result | ConvertTo-Json -Depth 12 | Set-Content -LiteralPath (Join-Path $outputPath ($name+'_'+$seed+'.json')) -Encoding utf8
        if(($result.CoefficientClips | Measure-Object -Sum).Sum -ne 0 -or ($result.OutputClips | Measure-Object -Sum).Sum -ne 0){throw ('clipping '+$name)}
        Write-Output ($name+' seed '+$seed+': actual conversions='+$result.Conversions+', both methods completed at '+[DateTime]::UtcNow.ToString('o'))
    }}}
    foreach($item in $frozen){if((Get-FileHash -LiteralPath $item.Path).Hash -ne $item.Hash){throw 'Source changed during run'}}
    'Source hashes unchanged' | Set-Content -LiteralPath (Join-Path $outputPath 'completed.txt') -Encoding utf8
}catch{$_ | Out-String | Set-Content -LiteralPath (Join-Path $outputPath 'run_failure.txt');throw}
