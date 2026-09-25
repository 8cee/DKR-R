[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$RomV77,

    [string]$RomV80 = "",

    [ValidateSet('Debug', 'Release')]
    [string]$Configuration = 'Debug',

    [switch]$ForceDependencies
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$Root = Split-Path -Parent $PSScriptRoot
$BuildRoot = Join-Path $Root 'build'
$AndroidGenerated = Join-Path $BuildRoot 'android-generated'
$AndroidRoms = Join-Path $BuildRoot 'android-roms'
$DkrDecomp = Join-Path $Root 'extern\dkr-decomp'
$N64Runtime = Join-Path $Root 'extern\n64-modern-runtime'
$N64RecompSource = Join-Path $N64Runtime 'N64Recomp'

function Invoke-Checked([string]$Label, [scriptblock]$Command) {
    Write-Host ""
    Write-Host "==> $Label" -ForegroundColor Cyan
    & $Command
    if ($LASTEXITCODE -ne 0) {
        throw "$Label failed with exit code $LASTEXITCODE."
    }
}

$PythonCommand = Get-Command python3 -ErrorAction SilentlyContinue
if (-not $PythonCommand) { $PythonCommand = Get-Command python -ErrorAction SilentlyContinue }
if (-not $PythonCommand) { throw 'Python 3 was not found on PATH.' }
$Python = $PythonCommand.Source

$RomV77Path = (Resolve-Path -LiteralPath $RomV77).Path
$RomV80Path = ""
if (-not [string]::IsNullOrWhiteSpace($RomV80)) {
    $RomV80Path = (Resolve-Path -LiteralPath $RomV80).Path
}

$bootstrap = Join-Path $Root 'scripts\bootstrap_dependencies.py'
$bootstrapArgs = @($bootstrap, '--only', 'dkr-decomp', '--only', 'n64-modern-runtime', '--force')
Invoke-Checked 'Preparing pinned DKR metadata and N64Recomp sources' {
    & $Python @bootstrapArgs
}

Invoke-Checked 'Applying checksummed runtime patches' {
    & $Python (Join-Path $Root 'scripts\apply_dependency_patches.py')
}

function Resolve-HostCMake {
    $candidates = New-Object System.Collections.Generic.List[string]
    if ($env:ANDROID_SDK_ROOT) { $candidates.Add((Join-Path $env:ANDROID_SDK_ROOT 'cmake\3.22.1\bin\cmake.exe')) }
    if ($env:ANDROID_HOME) { $candidates.Add((Join-Path $env:ANDROID_HOME 'cmake\3.22.1\bin\cmake.exe')) }
    if ($env:LOCALAPPDATA) { $candidates.Add((Join-Path $env:LOCALAPPDATA 'Android\Sdk\cmake\3.22.1\bin\cmake.exe')) }
    $pathCMake = Get-Command cmake -ErrorAction SilentlyContinue
    if ($pathCMake) { $candidates.Add($pathCMake.Source) }
    foreach ($candidate in $candidates | Select-Object -Unique) {
        if ($candidate -and (Test-Path -LiteralPath $candidate -PathType Leaf)) { return $candidate }
    }
    throw 'CMake was not found. Install Android Studio CMake 3.22.1 or put cmake on PATH.'
}

$CMake = Resolve-HostCMake
$HostRecompBuild = Join-Path $BuildRoot 'android-host-n64recomp'
Invoke-Checked 'Configuring pinned host N64Recomp' {
    & $CMake -S $N64RecompSource -B $HostRecompBuild -DCMAKE_BUILD_TYPE=Release
}
Invoke-Checked 'Building pinned host N64Recomp' {
    & $CMake --build $HostRecompBuild --config Release --target N64RecompCLI --parallel
}

$N64Recomp = Get-ChildItem -LiteralPath $HostRecompBuild -File -Recurse |
    Where-Object { $_.Name -eq 'N64Recomp.exe' -or $_.Name -eq 'N64Recomp' } |
    Select-Object -First 1
if (-not $N64Recomp) { throw "N64Recomp executable was not found under $HostRecompBuild" }
Write-Host "[OK] Host N64Recomp: $($N64Recomp.FullName)" -ForegroundColor Green

New-Item -ItemType Directory -Force -Path $AndroidRoms, $AndroidGenerated | Out-Null

$CanonicalV77 = Join-Path $AndroidRoms 'dkr.us.v77.z64'
$romArgsV77 = @(
    (Join-Path $Root 'scripts\prepare_android_rom.py'),
    '--revision', 'v77',
    '--input', $RomV77Path,
    '--output', $CanonicalV77
)
Invoke-Checked 'Validating and normalizing DKR US v1.0 ROM' { & $Python @romArgsV77 }

$GeneratedV77 = Join-Path $AndroidGenerated 'v77'
$payloadArgsV77 = @(
    (Join-Path $Root 'scripts\generate_android_payload_from_rom.py'),
    '--revision', 'v77',
    '--rom', $CanonicalV77,
    '--decomp-root', $DkrDecomp,
    '--n64recomp', $N64Recomp.FullName,
    '--output', $GeneratedV77
)
Invoke-Checked 'Generating DKR v77 CPU payload directly from ROM metadata' { & $Python @payloadArgsV77 }

$GeneratedV80 = ""
if ($RomV80Path) {
    $CanonicalV80 = Join-Path $AndroidRoms 'dkr.us.v80.z64'
    $romArgsV80 = @(
        (Join-Path $Root 'scripts\prepare_android_rom.py'),
        '--revision', 'v80',
        '--input', $RomV80Path,
        '--output', $CanonicalV80
    )
    Invoke-Checked 'Validating and normalizing DKR US Rev A ROM' { & $Python @romArgsV80 }

    $GeneratedV80 = Join-Path $AndroidGenerated 'v80'
    $payloadArgsV80 = @(
        (Join-Path $Root 'scripts\generate_android_payload_from_rom.py'),
        '--revision', 'v80',
        '--rom', $CanonicalV80,
        '--decomp-root', $DkrDecomp,
        '--n64recomp', $N64Recomp.FullName,
        '--output', $GeneratedV80
    )
    Invoke-Checked 'Generating DKR v80 CPU payload directly from ROM metadata' { & $Python @payloadArgsV80 }
}

$fullBuild = Join-Path $Root 'scripts\Build-Android-Full.ps1'
$fullArgs = @(
    '-NoLogo', '-NoProfile', '-ExecutionPolicy', 'Bypass',
    '-File', $fullBuild,
    '-GeneratedV77', $GeneratedV77,
    '-Configuration', $Configuration,
    '-ForceDependencies'
)
if ($GeneratedV80) { $fullArgs += @('-GeneratedV80', $GeneratedV80) }

Invoke-Checked 'Building full native DKR-R Android APK' {
    & powershell.exe @fullArgs
}

Write-Host ""
Write-Host '[OK] ROM-to-APK pipeline completed without WSL or Ubuntu.' -ForegroundColor Green
Write-Host "Generated v77 payload: $GeneratedV77"
if ($GeneratedV80) { Write-Host "Generated v80 payload: $GeneratedV80" }
Write-Host 'ROM inputs remain private under build/android-roms and are ignored by Git.'
