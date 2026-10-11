param([Parameter(Mandatory=$true)][string]$Output,[switch]$Preflight,[string]$PreflightPath)
$ErrorActionPreference='Stop'
$rootPath=(Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$outputPath=[IO.Path]::GetFullPath($Output)
$allowedPath=Join-Path $rootPath 'artifacts\runs\EXP_069'
if(-not $outputPath.StartsWith($allowedPath+[IO.Path]::DirectorySeparatorChar)){throw 'Output outside EXP_069'}
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
foreach($sourceName in @('source_protocol','architecture_protocol')){
    Copy-Item -LiteralPath (Join-Path $rootPath $protocol.$sourceName) -Destination (Join-Path $outputPath ($sourceName+'.json'))
}
$files=@()
foreach($directory in @('src','rtl','experiments\exp_057_static_two_stage_million','experiments\exp_059_static_fixed_million','experiments\exp_060_static_auxiliary_preflight','experiments\exp_061_static_auxiliary_million','experiments\exp_062_same_input_background','experiments\exp_069_gu_learning_rate')){
    $files+=@(Get-ChildItem -LiteralPath (Join-Path $rootPath $directory) -Recurse -File | Where-Object { $_.Extension -in '.py','.cs','.ps1','.json','.md','.sv','.v' -and $_.FullName -notmatch '__pycache__' })
}
$files+=Get-Item -LiteralPath (Join-Path $rootPath 'configs\architectures\gu_behavioral_v1.yaml')
$frozen=@($files | Get-FileHash | Select-Object Path,Hash)
$frozen | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $outputPath 'source_hashes.json') -Encoding utf8
@{PSVersion=$PSVersionTable.PSVersion.ToString();Runtime=[System.Runtime.InteropServices.RuntimeInformation]::FrameworkDescription;StartedUTC=[DateTime]::UtcNow.ToString('o')} | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $outputPath 'environment.json')
try{
    $sourcePath=Join-Path $rootPath $protocol.source_folder
    $prior=Get-Content -Raw -LiteralPath (Join-Path $sourcePath 'delivery_validation.json') | ConvertFrom-Json
    if(-not $prior.passed){throw 'EXP062 delivery not passed'}
    $manifest=Get-Content -Raw -LiteralPath (Join-Path $sourcePath 'delivery_hashes.json') | ConvertFrom-Json -AsHashtable
    $seeds=if($Preflight){@($protocol.seeds[0])}else{@($protocol.seeds)}
    $sourceFiles=@('tone.bin','protocol.json','summary.json','analysis.json','verification.json','delivery_validation.json')
    foreach($case in $protocol.cases){foreach($seed in $seeds){
        $stem=$case+'_'+$seed
        foreach($suffix in @('.json','_words.bin','_outputs.bin','_point30_q22.bin','_full120_q22.bin')){$sourceFiles+=$stem+$suffix}
    }}
    $checked=@{}
    foreach($name in ($sourceFiles | Sort-Object -Unique)){
        $hash=(Get-FileHash -LiteralPath (Join-Path $sourcePath $name)).Hash.ToLower()
        if($hash -ne $manifest[$name]){throw ('EXP062 data hash mismatch '+$name)}
        $checked[$name]=$hash
    }
    $checked | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $outputPath 'data_hashes.json') -Encoding utf8
    Copy-Item -LiteralPath (Join-Path $sourcePath 'delivery_hashes.json') -Destination (Join-Path $outputPath 'source_delivery_hashes.json')
    Copy-Item -LiteralPath (Join-Path $sourcePath 'tone.bin') -Destination (Join-Path $outputPath 'tone.bin')
    Add-Type -Path (Join-Path $rootPath 'experiments\exp_057_static_two_stage_million\Kernel.cs'),(Join-Path $rootPath 'experiments\exp_059_static_fixed_million\Kernel.cs'),(Join-Path $rootPath 'experiments\exp_061_static_auxiliary_million\Kernel.cs'),(Join-Path $rootPath 'experiments\exp_062_same_input_background\Kernel.cs'),(Join-Path $PSScriptRoot 'Kernel.cs') -CompilerOptions '/optimize+'
    $rateList=if($Preflight){@($protocol.rate_scales)}else{@($protocol.rate_scales | Where-Object { $_.name -in $protocol.new_long_rate_names })}
    [Adc069+Rate[]]$rates=@($rateList | ForEach-Object { $r=[Adc069+Rate]::new();$r.Name=$_.name;$r.Num=$_.numerator;$r.Den=$_.denominator;$r })
    $windows=if($Preflight){[int]$protocol.preflight.windows}else{[int]$protocol.budget.windows_per_path}
    foreach($case in $protocol.cases){foreach($seed in $seeds){
        $stem=$case+'_'+$seed
        $result=[Adc069]::Run($outputPath,$sourcePath,$stem,$windows,$rates,[bool]$Preflight)
        $result | ConvertTo-Json -Depth 14 | Set-Content -LiteralPath (Join-Path $outputPath ($stem+'.json')) -Encoding utf8
        Write-Output ($stem+': paths='+$result.Paths.Length+', windows='+$windows+', at '+[DateTime]::UtcNow.ToString('o'))
    }}
    foreach($item in $frozen){if((Get-FileHash -LiteralPath $item.Path).Hash -ne $item.Hash){throw 'Source changed during run'}}
    foreach($name in $checked.Keys){if((Get-FileHash -LiteralPath (Join-Path $sourcePath $name)).Hash.ToLower() -ne $checked[$name]){throw 'Original data changed'}}
    'Frozen source and original data unchanged' | Set-Content -LiteralPath (Join-Path $outputPath 'completed.txt') -Encoding utf8
}catch{$_ | Out-String | Set-Content -LiteralPath (Join-Path $outputPath 'run_failure.txt');throw}
