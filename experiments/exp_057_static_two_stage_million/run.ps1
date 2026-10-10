param([Parameter(Mandatory=$true)][string]$Output, [string]$PreflightPath='D:\ADC\artifacts\runs\EXP_057\preflight_v3')
$ErrorActionPreference='Stop'
$rootPath=(Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$outputPath=[System.IO.Path]::GetFullPath($Output)
$allowedPath=Join-Path $rootPath 'artifacts\runs\EXP_057'
if(-not $outputPath.StartsWith($allowedPath+[System.IO.Path]::DirectorySeparatorChar)) { throw 'Output outside EXP_057' }
if(Test-Path -LiteralPath $outputPath) { throw 'Refusing overwrite' }
$preflight=Get-Content -Raw -LiteralPath (Join-Path $PreflightPath 'verification.json') | ConvertFrom-Json
if(-not $preflight.passed) { throw 'Preflight not passed' }
foreach($hash in (Get-Content -Raw -LiteralPath (Join-Path $PreflightPath 'preflight_source_hashes.json') | ConvertFrom-Json)) {
    if((Get-FileHash -LiteralPath $hash.Path).Hash -ne $hash.Hash) {throw 'Preflight source changed'}
}
New-Item -ItemType Directory -Path $outputPath | Out-Null
Copy-Item -LiteralPath (Join-Path $PSScriptRoot 'protocol.json') -Destination (Join-Path $outputPath 'protocol.json')
Copy-Item -LiteralPath (Join-Path $PreflightPath 'verification.json') -Destination (Join-Path $outputPath 'preflight_verification.json')
$files=@(Get-ChildItem -LiteralPath (Join-Path $rootPath 'src') -Recurse -File | Where-Object Extension -eq '.py')
$files+=@(Get-ChildItem -LiteralPath (Join-Path $rootPath 'rtl') -Recurse -File | Where-Object Extension -in '.v','.sv')
$files+=@(Get-ChildItem -LiteralPath $PSScriptRoot -File)
$files+=Get-Item -LiteralPath (Join-Path $rootPath 'configs\architectures\gu_behavioral_v1.yaml')
$frozen=@($files | Get-FileHash | Select-Object Path,Hash)
$frozen | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $outputPath 'source_hashes.json') -Encoding utf8
& (Join-Path $PSScriptRoot 'native.ps1') -Output $outputPath
foreach($hash in $frozen) {
    if((Get-FileHash -LiteralPath $hash.Path).Hash -ne $hash.Hash) { throw ('Source changed: '+$hash.Path) }
}
'Completed; source hashes unchanged' | Set-Content -LiteralPath (Join-Path $outputPath 'completed.txt') -Encoding utf8
