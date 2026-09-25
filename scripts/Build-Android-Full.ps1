[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$GeneratedV77,

    [string]$GeneratedV80 = "",

    [ValidateSet('Debug', 'Release')]
    [string]$Configuration = 'Debug',

    [switch]$ForceDependencies
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$Root = Split-Path -Parent $PSScriptRoot
$AndroidRoot = Join-Path $Root 'android'
$V77 = (Resolve-Path -LiteralPath $GeneratedV77).Path
$V80 = ""
if (-not [string]::IsNullOrWhiteSpace($GeneratedV80)) {
    $V80 = (Resolve-Path -LiteralPath $GeneratedV80).Path
}

function Invoke-Checked([string]$Label, [scriptblock]$Command) {
    Write-Host ""
    Write-Host "==> $Label" -ForegroundColor Cyan
    & $Command
    if ($LASTEXITCODE -ne 0) {
        throw "$Label failed with exit code $LASTEXITCODE."
    }
}

function Resolve-AndroidSdk {
    $candidates = @(
        $env:ANDROID_SDK_ROOT,
        $env:ANDROID_HOME,
        (Join-Path $env:LOCALAPPDATA 'Android\\Sdk')
    ) | Where-Object { $_ -and (Test-Path -LiteralPath $_ -PathType Container) } |
        Select-Object -Unique

    foreach ($candidate in $candidates) {
        return (Resolve-Path -LiteralPath $candidate).Path
    }
    throw 'Android SDK not found. Install Android Studio/SDK once or set ANDROID_SDK_ROOT.'
}

$AndroidSdk = Resolve-AndroidSdk
$env:ANDROID_SDK_ROOT = $AndroidSdk
$env:ANDROID_HOME = $AndroidSdk

$SdkManagerCandidates = @(
    (Join-Path $AndroidSdk 'cmdline-tools\\latest\\bin\\sdkmanager.bat'),
    (Join-Path $AndroidSdk 'cmdline-tools\\bin\\sdkmanager.bat'),
    (Join-Path $AndroidSdk 'tools\\bin\\sdkmanager.bat')
)
$SdkManager = $SdkManagerCandidates |
    Where-Object { Test-Path -LiteralPath $_ -PathType Leaf } |
    Select-Object -First 1

if ($SdkManager) {
    $SdkPackages = @(
        'platforms;android-35',
        'build-tools;35.0.0',
        'ndk;27.2.12479018',
        'cmake;3.22.1'
    )
    Invoke-Checked 'Ensuring Android SDK 35 / NDK 27.2 / CMake 3.22.1 are installed' {
        & $SdkManager @SdkPackages
    }
}

$SdkCMake = Join-Path $AndroidSdk 'cmake\\3.22.1\\bin\\cmake.exe'
if (-not (Test-Path -LiteralPath $SdkCMake -PathType Leaf)) {
    $cmakeCommand = Get-Command cmake -ErrorAction SilentlyContinue
    if (-not $cmakeCommand) {
        if ($SdkManager) {
            throw "Android SDK CMake 3.22.1 was requested but was not found at $SdkCMake."
        }
        throw 'CMake was not found. Install Android SDK CMake 3.22.1 or put cmake on PATH.'
    }
    $SdkCMake = $cmakeCommand.Source
}

function Require-GeneratedPayload([string]$Path, [string]$Revision) {
    $sources = @(Get-ChildItem -LiteralPath $Path -File -Recurse -Include '*.c','*.cpp' -ErrorAction SilentlyContinue)
    if ($sources.Count -eq 0) {
        throw "$Revision generated payload contains no C/C++ source files: $Path"
    }
    $funcs = Get-ChildItem -LiteralPath $Path -File -Recurse -Filter 'funcs.h' -ErrorAction SilentlyContinue |
        Select-Object -First 1
    if (-not $funcs) {
        throw "$Revision generated payload is missing funcs.h: $Path"
    }
    Write-Host "[OK] $Revision payload: $($sources.Count) source files" -ForegroundColor Green
}

Require-GeneratedPayload $V77 'DKR US v1.0 / v77'

$RequiredRuntimeInputs = @(
    (Join-Path $Root 'runtime-recomp\RecompiledRSP\aspMain.cpp'),
    (Join-Path $Root 'runtime-recomp\dkr.us.v77.recomp-policy.json'),
    (Join-Path $Root 'runtime-recomp\legacy-mods.v77.recomp-fragment.json'),
    (Join-Path $Root 'runtime-recomp\legacy-track-menu.v77.recomp-fragment.json'),
    (Join-Path $Root 'runtime-recomp\legacy-characters.v77.recomp-fragment.json'),
    (Join-Path $Root 'runtime-recomp\legacy-character-menu.v77.recomp-fragment.json')
)
foreach ($required in $RequiredRuntimeInputs) {
    if (-not (Test-Path -LiteralPath $required -PathType Leaf)) {
        throw "Required full-runtime input is missing: $required"
    }
}
Write-Host '[OK] Full-runtime RSP and Patch Pipeline inputs are present.' -ForegroundColor Green

if ($V80) {
    Require-GeneratedPayload $V80 'DKR US Rev A / v80'
} else {
    Write-Host '[INFO] No v80 payload supplied; this APK will support DKR US v1.0 only.' -ForegroundColor Yellow
}

if (-not (Get-Command python -ErrorAction SilentlyContinue) -and
    -not (Get-Command python3 -ErrorAction SilentlyContinue)) {
    throw 'Python 3 is required.'
}
$Python = if (Get-Command python3 -ErrorAction SilentlyContinue) { 'python3' } else { 'python' }

$bootstrapArgs = @((Join-Path $Root 'scripts\bootstrap_dependencies.py'))
if ($ForceDependencies) { $bootstrapArgs += '--force' }
Invoke-Checked 'Preparing all pinned DKR-R dependencies' {
    & $Python @bootstrapArgs
}

$patchScript = Join-Path $Root 'scripts\apply_dependency_patches.py'
Invoke-Checked 'Applying pinned dependency patches' {
    & $Python $patchScript
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
$NinjaCandidates = @(
    (Join-Path (Split-Path -Parent $SdkCMake) 'ninja.exe'),
    (Get-Command ninja -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Source -ErrorAction SilentlyContinue)
) | Where-Object { $_ -and (Test-Path -LiteralPath $_ -PathType Leaf) } |
    Select-Object -Unique
$Ninja = $NinjaCandidates | Select-Object -First 1
if (-not $Ninja) {
    throw 'Ninja was not found. Android Studio CMake normally includes ninja.exe beside cmake.exe.'
}

$HostBuild = Join-Path $Root 'build\android-host-file-to-c'
Reset-CMakeGeneratorCache $HostBuild
$Rt64ToolSource = Join-Path $Root 'extern\rt64\src\tools\file_to_c'
$configureFileToCArgs = @(
    '-S', $Rt64ToolSource,
    '-B', $HostBuild,
    '-G', 'Ninja',
    "-DCMAKE_MAKE_PROGRAM=$Ninja",
    '-DCMAKE_BUILD_TYPE=Release'
)
Invoke-Checked 'Configuring RT64 host file_to_c' {
    & $SdkCMake @configureFileToCArgs
}
Invoke-Checked 'Building RT64 host file_to_c' {
    & $SdkCMake --build $HostBuild --config Release --parallel
}

$FileToC = Get-ChildItem -LiteralPath $HostBuild -File -Recurse |
    Where-Object { $_.Name -eq 'file_to_c' -or $_.Name -eq 'file_to_c.exe' } |
    Select-Object -First 1
if (-not $FileToC) {
    throw "Host file_to_c was not found under $HostBuild"
}

$env:RT64_HOST_FILE_TO_C = $FileToC.FullName
$env:DKR_ANDROID_FULL_RUNTIME = '1'
$env:DKR_ANDROID_GENERATED_V77 = $V77
if ($V80) {
    $env:DKR_ANDROID_GENERATED_V80 = $V80
} else {
    Remove-Item Env:DKR_ANDROID_GENERATED_V80 -ErrorAction SilentlyContinue
}

function Resolve-Gradle {
    $wrapper = Join-Path $AndroidRoot 'gradlew.bat'
    if (Test-Path -LiteralPath $wrapper -PathType Leaf) {
        return $wrapper
    }

    $installed = Get-Command gradle -ErrorAction SilentlyContinue
    if ($installed) {
        return $installed.Source
    }

    $version = '8.10.2'
    $toolRoot = Join-Path $Root "build\tools\gradle-$version"
    $gradleExe = Join-Path $toolRoot "gradle-$version\bin\gradle.bat"
    if (Test-Path -LiteralPath $gradleExe -PathType Leaf) {
        return $gradleExe
    }

    New-Item -ItemType Directory -Force -Path $toolRoot | Out-Null
    $zip = Join-Path $toolRoot "gradle-$version-bin.zip"
    $shaFile = "$zip.sha256"
    $url = "https://services.gradle.org/distributions/gradle-$version-bin.zip"

    Write-Host ""
    Write-Host "==> Downloading pinned Gradle $version" -ForegroundColor Cyan
    Invoke-WebRequest -UseBasicParsing -Uri $url -OutFile $zip
    Invoke-WebRequest -UseBasicParsing -Uri "$url.sha256" -OutFile $shaFile

    $expected = (Get-Content -LiteralPath $shaFile -Raw).Trim().ToLowerInvariant()
    $actual = (Get-FileHash -LiteralPath $zip -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($expected -ne $actual) {
        Remove-Item -LiteralPath $zip -Force -ErrorAction SilentlyContinue
        throw "Gradle $version checksum mismatch. Expected $expected, got $actual."
    }

    Expand-Archive -LiteralPath $zip -DestinationPath $toolRoot -Force
    if (-not (Test-Path -LiteralPath $gradleExe -PathType Leaf)) {
        throw "Pinned Gradle was extracted but gradle.bat was not found: $gradleExe"
    }
    return $gradleExe
}

$Gradle = Resolve-Gradle
$task = if ($Configuration -eq 'Release') { 'assembleRelease' } else { 'assembleDebug' }
Invoke-Checked "Building full DKR-R Android $Configuration APK" {
    Push-Location $AndroidRoot
    try {
        & $Gradle --no-daemon --stacktrace $task
    } finally {
        Pop-Location
    }
}

$apkDir = Join-Path $AndroidRoot "app\build\outputs\apk\$($Configuration.ToLowerInvariant())"
$apk = Get-ChildItem -LiteralPath $apkDir -Filter '*.apk' -File -ErrorAction SilentlyContinue |
    Select-Object -First 1
if (-not $apk) {
    throw "Gradle completed but no APK was found in $apkDir"
}

Write-Host ""
Write-Host '[OK] Full DKR-R Android APK built.' -ForegroundColor Green
Write-Host "APK: $($apk.FullName)"
Write-Host 'No ROM is copied into the APK or repository.'
