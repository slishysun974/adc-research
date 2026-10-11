param([Parameter(Mandatory=$true)][string]$Output,[switch]$Preflight,[string]$PreflightPath)
$ErrorActionPreference='Stop'
$rootPath=(Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$outputPath=[IO.Path]::GetFullPath($Output)
$allowedPath=Join-Path $rootPath 'artifacts\runs\EXP_061'
if(-not $outputPath.StartsWith($allowedPath+[IO.Path]::DirectorySeparatorChar)){throw 'Output outside EXP_061'}
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
foreach($field in @('source_protocol','auxiliary_protocol')){
    Copy-Item -LiteralPath (Join-Path $rootPath $protocol.$field) -Destination (Join-Path $outputPath ($field+'.json'))
}
$source=Get-Content -Raw -LiteralPath (Join-Path $outputPath 'source_protocol.json') | ConvertFrom-Json
$aux=Get-Content -Raw -LiteralPath (Join-Path $outputPath 'auxiliary_protocol.json') | ConvertFrom-Json
$files=@()
foreach($directory in @('src','rtl','experiments\exp_057_static_two_stage_million','experiments\exp_058_static_fixed_preflight','experiments\exp_059_static_fixed_million','experiments\exp_060_static_auxiliary_preflight','experiments\exp_061_static_auxiliary_million')){
    $files+=@(Get-ChildItem -LiteralPath (Join-Path $rootPath $directory) -Recurse -File | Where-Object { $_.Extension -in '.py','.cs','.ps1','.json','.md','.sv','.v' -and $_.FullName -notmatch '__pycache__' })
}
$files+=Get-Item -LiteralPath (Join-Path $rootPath 'configs\architectures\gu_behavioral_v1.yaml')
$frozen=@($files | Get-FileHash | Select-Object Path,Hash)
$frozen | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $outputPath 'source_hashes.json') -Encoding utf8
@{PSVersion=$PSVersionTable.PSVersion.ToString();Runtime=[System.Runtime.InteropServices.RuntimeInformation]::FrameworkDescription;StartedUTC=[DateTime]::UtcNow.ToString('o')} | ConvertTo-Json | Set-Content (Join-Path $outputPath 'environment.json')
try{
    Add-Type -Path (Join-Path $rootPath 'experiments\exp_057_static_two_stage_million\Kernel.cs'),(Join-Path $rootPath 'experiments\exp_059_static_fixed_million\Kernel.cs'),(Join-Path $PSScriptRoot 'Kernel.cs') -CompilerOptions '/optimize+'
    foreach($case in $aux.cases){foreach($method in $source.methods){
        $windows=if($Preflight){[int]$protocol.preflight.windows}else{[int]$method.training_windows}
        $seeds=if($Preflight){@($protocol.seeds[0])}else{$protocol.seeds}
        $keep=[Collections.Generic.HashSet[int]]::new()
        if($Preflight){for($w=0;$w -lt $windows;$w++){[void]$keep.Add($w)}}else{
            for($w=0;$w -lt 8;$w++){[void]$keep.Add($w)}
            foreach($cp in $method.checkpoint_windows){if($cp -gt 0){for($w=$cp-8;$w -lt $cp;$w++){[void]$keep.Add($w)}}}
        }
        [int[]]$probes=@($keep | Sort-Object)
        foreach($seed in $seeds){
            $name=$case.name+'_'+$method.name
            $result=[Adc061]::Run($outputPath,$name,[ulong]$seed,[double]$case.stage1[0],[double]$case.stage1[1],[double]$case.auxiliary[0],[double]$case.auxiliary[1],[double]$case.stage2[0],[double]$case.stage2[1],$windows,[int]$method.selected,[int]$method.multiplier,$probes)
            $result | ConvertTo-Json -Depth 10 | Set-Content -LiteralPath (Join-Path $outputPath ($name+'_'+$seed+'.json')) -Encoding utf8
            if($result.CoefficientClips -ne 0 -or $result.OutputClips -ne 0){throw ('clipping '+$name)}
            Write-Output ($name+' seed '+$seed+': windows='+$windows+', samples='+$result.GeneratedSamples)
        }
    }}
    foreach($item in $frozen){if((Get-FileHash -LiteralPath $item.Path).Hash -ne $item.Hash){throw 'Source changed during run'}}
    'Source hashes unchanged' | Set-Content -LiteralPath (Join-Path $outputPath 'completed.txt') -Encoding utf8
}catch{$_ | Out-String | Set-Content -LiteralPath (Join-Path $outputPath 'run_failure.txt');throw}
