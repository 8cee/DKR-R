[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$GeneratedV77,

    [Parameter(Mandatory = $true)]
    [string]$GeneratedV80,

    [ValidateSet('Debug', 'Release')]
    [string]$Configuration = 'Debug',

    [switch]$ForceDependencies
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$Root = Split-Path -Parent $PSScriptRoot
$AndroidRoot = Join-Path $Root 'android'
$V77 = (Resolve-Path -LiteralPath $GeneratedV77).Path
$V80 = (Resolve-Path -LiteralPath $GeneratedV80).Path

function Invoke-Checked([string]$Label, [scriptblock]$Command) {
    Write-Host ""
    Write-Host "==> $Label" -ForegroundColor Cyan
    & $Command
    if ($LASTEXITCODE -ne 0) {
        throw "$Label failed with exit code $LASTEXITCODE."
    }
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
Require-GeneratedPayload $V80 'DKR US Rev A / v80'

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

$HostBuild = Join-Path $Root 'build\android-host-file-to-c'
$Rt64ToolSource = Join-Path $Root 'extern\rt64\src\tools\file_to_c'
Invoke-Checked 'Configuring RT64 host file_to_c' {
    & cmake -S $Rt64ToolSource -B $HostBuild -DCMAKE_BUILD_TYPE=Release
}
Invoke-Checked 'Building RT64 host file_to_c' {
    & cmake --build $HostBuild --config Release --parallel
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
$env:DKR_ANDROID_GENERATED_V80 = $V80

$gradle = Get-Command gradle -ErrorAction SilentlyContinue
if (-not $gradle) {
    throw 'Gradle was not found on PATH. Install/use Gradle 8.10.2, matching the Android CI.'
}

$task = if ($Configuration -eq 'Release') { 'assembleRelease' } else { 'assembleDebug' }
Invoke-Checked "Building full DKR-R Android $Configuration APK" {
    Push-Location $AndroidRoot
    try {
        & $gradle.Source --no-daemon --stacktrace $task
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
