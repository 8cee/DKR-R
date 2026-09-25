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

function Ensure-HostCompiler {
    if (Get-Command cl.exe -ErrorAction SilentlyContinue) { return }
    if (Get-Command clang++.exe -ErrorAction SilentlyContinue) { return }
    if (Get-Command g++.exe -ErrorAction SilentlyContinue) { return }

    $programFilesX86 = [Environment]::GetFolderPath('ProgramFilesX86')
    $programFiles = [Environment]::GetFolderPath('ProgramFiles')
    $vswhereCandidates = @(
        (Join-Path $programFilesX86 'Microsoft Visual Studio\Installer\vswhere.exe'),
        (Join-Path $programFiles 'Microsoft Visual Studio\Installer\vswhere.exe')
    ) | Where-Object { $_ -and (Test-Path -LiteralPath $_ -PathType Leaf) }

    foreach ($vswhere in $vswhereCandidates) {
        $install = (& $vswhere -latest -products * -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath).Trim()
        if (-not $install) { continue }

        $devCmd = Join-Path $install 'Common7\Tools\VsDevCmd.bat'
        if (-not (Test-Path -LiteralPath $devCmd -PathType Leaf)) { continue }

        $command = '""{0}" -no_logo -arch=x64 -host_arch=x64 >nul && set"' -f $devCmd
        $environment = & cmd.exe /s /c $command
        if ($LASTEXITCODE -ne 0) { continue }

        foreach ($line in $environment) {
            $separator = $line.IndexOf('=')
            if ($separator -le 0) { continue }
            $name = $line.Substring(0, $separator)
            $value = $line.Substring($separator + 1)
            Set-Item -Path "Env:$name" -Value $value
        }
        if (Get-Command cl.exe -ErrorAction SilentlyContinue) {
            Write-Host '[OK] Visual Studio x64 host compiler environment loaded.' -ForegroundColor Green
            return
        }
    }

    throw 'No Windows host C/C++ compiler was found. Install Visual Studio Build Tools with Desktop development with C++, or put clang++/g++ on PATH.'
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

function Reset-CMakeGeneratorCache([string]$BuildDirectory) {
    $cache = Join-Path $BuildDirectory 'CMakeCache.txt'
    $files = Join-Path $BuildDirectory 'CMakeFiles'
    if (Test-Path -LiteralPath $cache -PathType Leaf) {
        Remove-Item -LiteralPath $cache -Force
    }
    if (Test-Path -LiteralPath $files -PathType Container) {
        Remove-Item -LiteralPath $files -Recurse -Force
    }
}

Ensure-HostCompiler
$CMake = Resolve-HostCMake
$NinjaCandidates = @(
    (Join-Path (Split-Path -Parent $CMake) 'ninja.exe'),
    (Get-Command ninja -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Source -ErrorAction SilentlyContinue)
) | Where-Object { $_ -and (Test-Path -LiteralPath $_ -PathType Leaf) } |
    Select-Object -Unique
$Ninja = $NinjaCandidates | Select-Object -First 1
if (-not $Ninja) {
    throw 'Ninja was not found. Android Studio CMake normally includes ninja.exe beside cmake.exe.'
}

$HostRecompBuild = Join-Path $BuildRoot 'android-host-n64recomp'
Reset-CMakeGeneratorCache $HostRecompBuild
$configureRecompArgs = @(
    '-S', $N64RecompSource,
    '-B', $HostRecompBuild,
    '-G', 'Ninja',
    "-DCMAKE_MAKE_PROGRAM=$Ninja",
    '-DCMAKE_BUILD_TYPE=Release'
)
Invoke-Checked 'Configuring pinned host N64Recomp' {
    & $CMake @configureRecompArgs
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
