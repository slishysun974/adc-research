param([Parameter(Mandatory=$true)][string]$Output)
$ErrorActionPreference='Stop'
$rootPath=(Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$env:TMP=Join-Path $rootPath 'tmp';$env:TEMP=$env:TMP
Add-Type -Path (Join-Path $rootPath 'experiments\exp_057_static_two_stage_million\Kernel.cs'),(Join-Path $PSScriptRoot 'Kernel.cs') -CompilerOptions '/optimize+'
$source=Get-Content -Raw -LiteralPath (Join-Path $Output 'source_protocol.json') | ConvertFrom-Json
$protocol=Get-Content -Raw -LiteralPath (Join-Path $Output 'protocol.json') | ConvertFrom-Json
$baselinePath=Join-Path $rootPath $protocol.baseline_run
foreach($case in $source.cases) {
    $inputPath=Join-Path $Output ($case.name+'_tone_input.bin')
    $reader=[IO.BinaryReader]::new([IO.File]::OpenRead($inputPath))
    $n=[int]$source.test_record.samples
    $words=@();for($j=0;$j -lt 5;$j++){$words+=,[int[]]::new($n)}
    try{for($i=0;$i -lt $n;$i++){for($j=0;$j -lt 5;$j++){$words[$j][$i]=$reader.ReadInt32()}}}finally{$reader.Dispose()}
    foreach($method in $source.methods) {
        foreach($seed in $source.seeds) {
            $stem=$case.name+'_'+$method.name+'_'+$seed
            $writer=[IO.BinaryWriter]::new([IO.File]::Open((Join-Path $Output ($stem+'_tones.bin')),[IO.FileMode]::CreateNew))
            try {
                foreach($checkpoint in $method.checkpoint_windows) {
                    for($mode=0;$mode -lt 4;$mode++) {
                        $suffix=@('sar8','q3','export','q22')[$mode]
                        $statePath=if($mode -eq 0){Join-Path $baselinePath ($stem+'_'+$suffix+'.bin')}else{Join-Path $Output ($stem+'_'+$suffix+'.bin')}
                        $reader=[IO.BinaryReader]::new([IO.File]::OpenRead($statePath))
                        [double[]]$hidden=[double[]]::new(8)
                        try{[void]$reader.BaseStream.Seek(64L*$checkpoint,[IO.SeekOrigin]::Begin);for($j=0;$j -lt 8;$j++){$hidden[$j]=$reader.ReadDouble()}}finally{$reader.Dispose()}
                        foreach($online in @($false,$true)) {
                            $values=[Adc059]::Tone($words[0],$words[1],$words[2],$words[3],$words[4],$hidden,$mode,[int]$method.selected,[int]$method.multiplier,$online)
                            $bytes=[byte[]]::new(8*$values.Length);[Buffer]::BlockCopy($values,0,$bytes,0,$bytes.Length);$writer.Write($bytes)
                        }
                    }
                }
            }finally{$writer.Dispose()}
            Write-Output ('scored '+$stem)
        }
    }
}
