[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$Destination,
    [string]$ExecutablePath = (Join-Path $PSScriptRoot '../src-tauri/target/release/melixsa-ui.exe')
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$executable = Get-Item -LiteralPath $ExecutablePath
if ($executable.PSIsContainer) {
    throw 'La build Tauri non ha prodotto un eseguibile Windows.'
}

$distribution = Join-Path $PSScriptRoot '../distribution'
$launcher = Join-Path $distribution 'Apri MelixsaUI.cmd'
$instructions = Join-Path $distribution 'LEGGIMI.txt'
foreach ($required in @($launcher, $instructions)) {
    if (-not (Test-Path -LiteralPath $required -PathType Leaf)) {
        throw "File di distribuzione mancante: $required"
    }
}

$outputDirectory = [System.IO.Path]::GetFullPath($Destination)
New-Item -ItemType Directory -Path $outputDirectory -Force | Out-Null
$outputExecutable = Join-Path $outputDirectory 'melixsa-ui.exe'
Copy-Item -LiteralPath $executable.FullName -Destination $outputExecutable
Copy-Item -LiteralPath $launcher -Destination (Join-Path $outputDirectory 'Apri MelixsaUI.cmd')
Copy-Item -LiteralPath $instructions -Destination (Join-Path $outputDirectory 'LEGGIMI.txt')

$hash = (Get-FileHash -LiteralPath $outputExecutable -Algorithm SHA256).Hash.ToLowerInvariant()
Set-Content -LiteralPath (Join-Path $outputDirectory 'SHA256SUMS.txt') -Value "$hash  melixsa-ui.exe" -Encoding utf8
Write-Output "Pacchetto Windows pronto: $outputDirectory"
