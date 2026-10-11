param([Parameter(Mandatory=$true)][string]$Output)
$ErrorActionPreference='Stop'
$rootPath=(Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$env:TMP=Join-Path $rootPath 'tmp';$env:TEMP=$env:TMP
Add-Type -Path (Join-Path $rootPath 'experiments\exp_057_static_two_stage_million\Kernel.cs'),(Join-Path $rootPath 'experiments\exp_059_static_fixed_million\Kernel.cs') -CompilerOptions '/optimize+'
$source=Get-Content -Raw (Join-Path $Output 'source_protocol.json') | ConvertFrom-Json
$protocol=Get-Content -Raw (Join-Path $Output 'protocol.json') | ConvertFrom-Json
$aux=Get-Content -Raw (Join-Path $Output 'auxiliary_protocol.json') | ConvertFrom-Json
foreach($case in $aux.cases){
    $reader=[IO.BinaryReader]::new([IO.File]::OpenRead((Join-Path $Output ($case.name+'_tone_input.bin'))))
    $n=[int]$protocol.test_record.samples
    $words=@();for($j=0;$j -lt 5;$j++){$words+=,[int[]]::new($n)}
    try{for($i=0;$i -lt $n;$i++){for($j=0;$j -lt 5;$j++){$words[$j][$i]=$reader.ReadInt32()}}}finally{$reader.Dispose()}
    foreach($method in $source.methods){foreach($seed in $protocol.seeds){
        $stem=$case.name+'_'+$method.name+'_'+$seed
        $writer=[IO.BinaryWriter]::new([IO.File]::Open((Join-Path $Output ($stem+'_tones.bin')),[IO.FileMode]::CreateNew))
        try{foreach($checkpoint in $method.checkpoint_windows){
            $reader=[IO.BinaryReader]::new([IO.File]::OpenRead((Join-Path $Output ($stem+'_q22.bin'))))
            [double[]]$hidden=[double[]]::new(8)
            try{[void]$reader.BaseStream.Seek(64L*$checkpoint,[IO.SeekOrigin]::Begin);for($j=0;$j -lt 8;$j++){$hidden[$j]=$reader.ReadDouble()}}finally{$reader.Dispose()}
            foreach($online in @($false,$true)){
                $values=[Adc059]::Tone($words[0],$words[1],$words[2],$words[3],$words[4],$hidden,3,[int]$method.selected,[int]$method.multiplier,$online)
                $bytes=[byte[]]::new(8*$values.Length);[Buffer]::BlockCopy($values,0,$bytes,0,$bytes.Length);$writer.Write($bytes)
            }
        }}finally{$writer.Dispose()}
        Write-Output ('scored '+$stem)
    }}
}
