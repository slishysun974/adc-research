param([Parameter(Mandatory=$true)][string]$Output)
$ErrorActionPreference='Stop'
$rootPath=(Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$outputPath=[IO.Path]::GetFullPath($Output)
$allowedPath=Join-Path $rootPath 'artifacts\runs\EXP_065'
if(-not $outputPath.StartsWith($allowedPath+[IO.Path]::DirectorySeparatorChar)){throw 'Output outside EXP_065'}
if(Test-Path -LiteralPath $outputPath){throw 'Refusing overwrite'}
New-Item -ItemType Directory -Path $outputPath | Out-Null
$env:TMP=Join-Path $rootPath 'tmp';$env:TEMP=$env:TMP
Copy-Item -LiteralPath (Join-Path $PSScriptRoot 'protocol.json') -Destination (Join-Path $outputPath 'protocol.json')
$protocol=Get-Content -Raw -LiteralPath (Join-Path $outputPath 'protocol.json') | ConvertFrom-Json
Copy-Item -LiteralPath (Join-Path $rootPath $protocol.source_protocol) -Destination (Join-Path $outputPath 'source_protocol.json')
$files=@()
foreach($directory in @('src','rtl','experiments\exp_057_static_two_stage_million','experiments\exp_058_static_fixed_preflight','experiments\exp_059_static_fixed_million','experiments\exp_060_static_auxiliary_preflight','experiments\exp_061_static_auxiliary_million','experiments\exp_062_same_input_background','experiments\exp_065_input_switch_tracking')){
    $files+=@(Get-ChildItem -LiteralPath (Join-Path $rootPath $directory) -Recurse -File | Where-Object { $_.Extension -in '.py','.cs','.ps1','.json','.md','.sv','.v' -and $_.FullName -notmatch '__pycache__' })
}
$files+=Get-Item -LiteralPath (Join-Path $rootPath 'configs\architectures\gu_behavioral_v1.yaml')
$files+=Get-Item -LiteralPath (Join-Path $rootPath 'artifacts\runs\EXP_062\background_v1\delivery_hashes.json')
$frozen=@($files | Get-FileHash | Select-Object Path,Hash)
$frozen | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $outputPath 'source_hashes.json') -Encoding utf8
@{PSVersion=$PSVersionTable.PSVersion.ToString();Runtime=[System.Runtime.InteropServices.RuntimeInformation]::FrameworkDescription;StartedUTC=[DateTime]::UtcNow.ToString('o')} | ConvertTo-Json | Set-Content (Join-Path $outputPath 'environment.json')
try{
    Add-Type -Path (Join-Path $rootPath 'experiments\exp_057_static_two_stage_million\Kernel.cs'),(Join-Path $rootPath 'experiments\exp_059_static_fixed_million\Kernel.cs'),(Join-Path $rootPath 'experiments\exp_061_static_auxiliary_million\Kernel.cs'),(Join-Path $PSScriptRoot 'Kernel.cs') -CompilerOptions '/optimize+'
    $n=[int]$protocol.input.samples_per_block
    $nominalPath=Join-Path $rootPath $protocol.nominal_folder
    $manifest=Get-Content -Raw -LiteralPath (Join-Path $nominalPath 'delivery_hashes.json') | ConvertFrom-Json -AsHashtable
    $prior=Get-Content -Raw -LiteralPath (Join-Path $nominalPath 'delivery_validation.json') | ConvertFrom-Json
    if(-not $prior.passed){throw 'Nominal delivery not passed'}
    $nominalFiles=@('tone.bin','protocol.json','delivery_validation.json','verification.json')
    foreach($case in $protocol.cases){foreach($seed in $protocol.seeds){
        $stem=$case.name+'_'+$seed
        foreach($suffix in @('.json','_words.bin','_outputs.bin','_point30_q22.bin','_full120_q22.bin')){$nominalFiles+=$stem+$suffix}
    }}
    $checked=@{}
    foreach($filename in ($nominalFiles | Sort-Object -Unique)){
        $hash=(Get-FileHash -LiteralPath (Join-Path $nominalPath $filename)).Hash.ToLower()
        if($hash -ne $manifest[$filename]){throw ('Nominal delivery mismatch '+$filename)}
        $checked[$filename]=$hash
    }
    $checked | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $outputPath 'nominal_hashes.json') -Encoding utf8
    Copy-Item -LiteralPath (Join-Path $nominalPath 'delivery_hashes.json') -Destination (Join-Path $outputPath 'nominal_delivery_hashes.json')
    Copy-Item -LiteralPath (Join-Path $nominalPath 'tone.bin') -Destination (Join-Path $outputPath 'tone.bin')
    $reader=[IO.BinaryReader]::new([IO.File]::OpenRead((Join-Path $outputPath 'tone.bin')))
    [double[]]$tone=[double[]]::new($n)
    try{for($i=0;$i -lt $n;$i++){$tone[$i]=$reader.ReadDouble()}}finally{$reader.Dispose()}
    $switchWindow=[int]$protocol.switch.global_window
    foreach($case in $protocol.cases){foreach($seed in @($protocol.seeds[0])){foreach($variant in $protocol.preflight.variants){
        $prefix=if($variant -eq 'fresh'){0}else{[int]$protocol.preflight.prefix_windows}
        $startWindow=$switchWindow-$prefix
        $windows=$prefix+[int]$protocol.preflight.post_windows
        $scale=if($variant -eq 'nochange'){1.0}else{[double]$protocol.input.scale_after}
        $initial=[double[][]]::new(2)
        for($m=0;$m -lt 2;$m++){
            $initial[$m]=[double[]]::new(8)
            if($variant -eq 'fresh'){for($j=0;$j -lt 8;$j++){$initial[$m][$j]=1.0}}else{
                $filename=$case.name+'_'+$seed+'_'+$protocol.methods[$m].name+'_q22.bin'
                $rd=[IO.BinaryReader]::new([IO.File]::OpenRead((Join-Path $nominalPath $filename)))
                try{[void]$rd.BaseStream.Seek(64L*$startWindow,[IO.SeekOrigin]::Begin);for($j=0;$j -lt 8;$j++){$initial[$m][$j]=$rd.ReadDouble()}}finally{$rd.Dispose()}
            }
        }
        $name=$case.name+'_'+$variant
        $initial | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath (Join-Path $outputPath ($name+'_'+$seed+'_initial.json')) -Encoding utf8
        [int[]]$probes=0..($windows-1)
        $result=[Adc065]::Run($outputPath,$name,[ulong]$seed,[double]$case.stage1[0],[double]$case.stage1[1],[double]$case.stage2[0],[double]$case.stage2[1],$tone,$windows,$probes,120L*$startWindow,[long]$protocol.switch.global_conversion,$scale,$initial)
        $result | ConvertTo-Json -Depth 12 | Set-Content -LiteralPath (Join-Path $outputPath ($name+'_'+$seed+'.json')) -Encoding utf8
        if(($result.CoefficientClips | Measure-Object -Sum).Sum -ne 0 -or ($result.OutputClips | Measure-Object -Sum).Sum -ne 0){throw ('clipping '+$name)}
        Write-Output ($name+' seed '+$seed+': global start='+$result.StartIndex+', actual conversions='+$result.Conversions)
    }}}
    foreach($item in $frozen){if((Get-FileHash -LiteralPath $item.Path).Hash -ne $item.Hash){throw 'Source changed during run'}}
    'Source hashes unchanged' | Set-Content -LiteralPath (Join-Path $outputPath 'completed.txt') -Encoding utf8
}catch{$_ | Out-String | Set-Content -LiteralPath (Join-Path $outputPath 'run_failure.txt');throw}
