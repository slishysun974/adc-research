param([Parameter(Mandatory=$true)][string]$Folder)
$ErrorActionPreference='Stop'
$rootPath=(Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$outputPath=(Resolve-Path -LiteralPath $Folder).Path
$allowedPath=Join-Path $rootPath 'artifacts\runs\EXP_070'
if(-not $outputPath.StartsWith($allowedPath+[IO.Path]::DirectorySeparatorChar)){throw 'Output outside EXP_070'}
if(Test-Path -LiteralPath (Join-Path $outputPath 'started.json')){throw 'Refusing rerun'}
function Check-Frozen {
    foreach($manifestName in @('source_hashes.json','data_hashes.json')){
        $manifest=Get-Content -Raw -LiteralPath (Join-Path $outputPath $manifestName) | ConvertFrom-Json -AsHashtable
        foreach($key in $manifest.Keys){if((Get-FileHash -LiteralPath (Join-Path $rootPath $key)).Hash.ToLower() -ne $manifest[$key]){throw ('Frozen mismatch '+$key)}}
    }
}
Check-Frozen
$env:TMP=Join-Path $rootPath 'tmp';$env:TEMP=$env:TMP
@{StartedUTC=[DateTime]::UtcNow.ToString('o');PSVersion=$PSVersionTable.PSVersion.ToString();Runtime=[System.Runtime.InteropServices.RuntimeInformation]::FrameworkDescription} | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $outputPath 'started.json') -Encoding utf8
try {
    $plan=Get-Content -Raw -LiteralPath (Join-Path $outputPath 'runplan.json') | ConvertFrom-Json
    $dependencies=@('experiments\exp_057_static_two_stage_million\Kernel.cs','experiments\exp_059_static_fixed_million\Kernel.cs','experiments\exp_061_static_auxiliary_million\Kernel.cs','experiments\exp_062_same_input_background\Kernel.cs','experiments\exp_069_gu_learning_rate\Kernel.cs','experiments\exp_070_gu_learning_rate_switch\Kernel.cs')
    Add-Type -Path @($dependencies | ForEach-Object { Join-Path $rootPath $_ }) -CompilerOptions '/optimize+'
    foreach($task in $plan.tasks){
        [Adc070+PathSpec[]]$specs=@($task.paths | ForEach-Object {
            $s=[Adc070+PathSpec]::new();$s.Name=$_.name;$s.Rate=$_.rate;$s.Variant=$_.variant;$s.Method=$_.method
            $s.Num=$_.num;$s.Den=$_.den;$s.Selected=$_.selected;$s.Multiplier=$_.multiplier
            $s.Initial=if($task.resume_task){[Adc070]::LastState($outputPath,$task.resume_task,$s.Name)}else{[int[]]$_.initial}
            $s
        })
        $result=[Adc070]::Run($outputPath,$task.stem,(Join-Path $rootPath $task.word_file),$task.word_start,$task.windows,$task.global_start,$specs)
        $result | ConvertTo-Json -Depth 14 | Set-Content -LiteralPath (Join-Path $outputPath ($task.stem+'.json')) -Encoding utf8
        Write-Output ($task.stem+': '+$specs.Length+' paths x '+$task.windows+' windows at '+[DateTime]::UtcNow.ToString('o'))
    }
    Check-Frozen
    @{CompletedUTC=[DateTime]::UtcNow.ToString('o');Tasks=$plan.tasks.Count} | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $outputPath 'completed.json') -Encoding utf8
} catch { $_ | Out-String | Set-Content -LiteralPath (Join-Path $outputPath 'run_failure.txt');throw }
