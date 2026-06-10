$ErrorActionPreference = "Continue"

Set-Location (Split-Path -Parent $PSScriptRoot)

Write-Host "Android environment check"
Write-Host "========================="

function Add-UniquePath {
    param(
        [System.Collections.ArrayList]$List,
        [string]$Path
    )
    if ($Path -and $Path.Trim() -ne "") {
        $normalized = $Path.Trim().Trim('"')
        if (-not $List.Contains($normalized)) {
            [void]$List.Add($normalized)
        }
    }
}

function Convert-GradleSdkDir {
    param([string]$Value)
    if (-not $Value) {
        return $null
    }
    $path = $Value.Trim().Trim('"')
    $path = $path -replace "\\:", ":"
    $path = $path -replace "\\\\", "\"
    return $path
}

function Get-GradleSdkPath {
    $localProperties = ".\client\local.properties"
    if (-not (Test-Path $localProperties)) {
        return $null
    }
    foreach ($line in Get-Content $localProperties) {
        if ($line -match "^\s*sdk\.dir\s*=\s*(.+)\s*$") {
            return Convert-GradleSdkDir $Matches[1]
        }
    }
    return $null
}

function Get-FirstExistingPath {
    param([string[]]$Paths)
    foreach ($path in $Paths) {
        if ($path -and (Test-Path $path)) {
            return $path
        }
    }
    return $null
}

function Get-SdkManagerPaths {
    param([string]$SdkPath)
    if (-not $SdkPath -or -not (Test-Path $SdkPath)) {
        return @()
    }
    $paths = @()
    $latest = Join-Path $SdkPath "cmdline-tools\latest\bin\sdkmanager.bat"
    if (Test-Path $latest) {
        $paths += $latest
    }
    $all = Get-ChildItem -Path (Join-Path $SdkPath "cmdline-tools") -Filter "sdkmanager.bat" -Recurse -ErrorAction SilentlyContinue |
        Select-Object -ExpandProperty FullName
    foreach ($path in $all) {
        if ($paths -notcontains $path) {
            $paths += $path
        }
    }
    return $paths
}

$java = Get-Command java -ErrorAction SilentlyContinue
if ($java) {
    Write-Host "[OK] java:" $java.Source
    java -version
} else {
    $studioJava = Get-FirstExistingPath @(
        "D:\Android\Studio\jbr\bin\java.exe",
        "C:\Program Files\Android\Android Studio\jbr\bin\java.exe"
    )
    if ($studioJava) {
        Write-Host "[OK] Android Studio bundled java:" $studioJava
        & $studioJava -version
    } else {
        Write-Host "[MISS] java was not found in PATH or Android Studio JBR"
    }
}

if (Test-Path ".\client\gradlew.bat") {
    Write-Host "[OK] Gradle wrapper: client\gradlew.bat"
} else {
    $gradle = Get-Command gradle -ErrorAction SilentlyContinue
    if ($gradle) {
        Write-Host "[OK] system gradle:" $gradle.Source
        gradle --version
    } else {
        Write-Host "[MISS] Gradle wrapper/system Gradle was not found"
    }
}

$gradleSdk = Get-GradleSdkPath
$sdkCandidates = New-Object System.Collections.ArrayList
Add-UniquePath $sdkCandidates $gradleSdk
Add-UniquePath $sdkCandidates $env:ANDROID_HOME
Add-UniquePath $sdkCandidates $env:ANDROID_SDK_ROOT
Add-UniquePath $sdkCandidates ([Environment]::GetEnvironmentVariable("ANDROID_HOME", "User"))
Add-UniquePath $sdkCandidates ([Environment]::GetEnvironmentVariable("ANDROID_SDK_ROOT", "User"))
Add-UniquePath $sdkCandidates ([Environment]::GetEnvironmentVariable("ANDROID_HOME", "Machine"))
Add-UniquePath $sdkCandidates ([Environment]::GetEnvironmentVariable("ANDROID_SDK_ROOT", "Machine"))
Add-UniquePath $sdkCandidates "D:\Android\Sdk"
Add-UniquePath $sdkCandidates "$env:LOCALAPPDATA\Android\Sdk"

$existingSdks = @()
foreach ($candidate in $sdkCandidates) {
    if (Test-Path $candidate) {
        $existingSdks += $candidate
        Write-Host "[OK] Android SDK candidate:" $candidate
    } else {
        Write-Host "[MISS] Android SDK candidate not found:" $candidate
    }
}

if ($gradleSdk) {
    if (Test-Path $gradleSdk) {
        Write-Host "[OK] Gradle SDK from client/local.properties:" $gradleSdk
    } else {
        Write-Host "[MISS] Gradle SDK from client/local.properties:" $gradleSdk
    }
} else {
    Write-Host "[INFO] client/local.properties does not set sdk.dir. Android Studio can generate it."
}

if ($existingSdks.Count -eq 0) {
    Write-Host "[MISS] Android SDK was not found. Install Android Studio or set ANDROID_HOME."
} else {
    $adbCandidates = @()
    foreach ($sdk in $existingSdks) {
        $adbCandidates += (Join-Path $sdk "platform-tools\adb.exe")
    }
    $adb = Get-FirstExistingPath $adbCandidates
    if ($adb) {
        Write-Host "[OK] adb:" $adb
        & $adb version | Select-Object -First 2
    } else {
        Write-Host "[MISS] adb was not found under any SDK platform-tools directory"
    }

    $platform35Sdks = @()
    $cmdlineToolSdks = @()
    $buildToolSdks = @()
    foreach ($sdk in $existingSdks) {
        if (Test-Path (Join-Path $sdk "platforms\android-35")) {
            $platform35Sdks += $sdk
        }
        if ((Get-SdkManagerPaths $sdk).Count -gt 0) {
            $cmdlineToolSdks += $sdk
        }
        if (Test-Path (Join-Path $sdk "build-tools")) {
            $buildTools = Get-ChildItem -Path (Join-Path $sdk "build-tools") -Directory -ErrorAction SilentlyContinue
            if ($buildTools.Count -gt 0) {
                $buildToolSdks += $sdk
            }
        }
    }

    if ($platform35Sdks.Count -gt 0) {
        Write-Host "[OK] Android SDK Platform 35:" ($platform35Sdks -join ", ")
    } else {
        Write-Host "[MISS] Android SDK Platform 35 in all detected SDKs"
    }

    if ($cmdlineToolSdks.Count -gt 0) {
        Write-Host "[OK] Android SDK Command-line Tools:" ($cmdlineToolSdks -join ", ")
    } else {
        Write-Host "[MISS] Android SDK Command-line Tools in all detected SDKs"
    }

    if ($buildToolSdks.Count -gt 0) {
        Write-Host "[OK] Android SDK Build-Tools:" ($buildToolSdks -join ", ")
    } else {
        Write-Host "[MISS] Android SDK Build-Tools in all detected SDKs"
    }

    $effectiveSdk = if ($gradleSdk) { $gradleSdk } else { $existingSdks[0] }
    if ($effectiveSdk) {
        Write-Host "[INFO] Effective Gradle SDK:" $effectiveSdk
        $effectiveSdkNeedsInstall = $false
        if (-not (Test-Path (Join-Path $effectiveSdk "platforms\android-35"))) {
            Write-Host "[WARN] Effective Gradle SDK is missing platforms\android-35. The Android build may fail."
            $effectiveSdkNeedsInstall = $true
        }
        if ((Get-SdkManagerPaths $effectiveSdk).Count -eq 0) {
            Write-Host "[WARN] Effective Gradle SDK is missing Command-line Tools."
            $effectiveSdkNeedsInstall = $true
        }
        $effectiveBuildTools = Get-ChildItem -Path (Join-Path $effectiveSdk "build-tools") -Directory -ErrorAction SilentlyContinue
        if (-not $effectiveBuildTools -or $effectiveBuildTools.Count -eq 0) {
            Write-Host "[WARN] Effective Gradle SDK is missing Build-Tools."
            $effectiveSdkNeedsInstall = $true
        }
        if ($effectiveSdkNeedsInstall) {
            Write-Host "[INFO] Install missing components in Android Studio SDK Manager, or run sdkmanager from a SDK that already has Command-line Tools."
        }
    }
}

if (Test-Path ".\client\app\build.gradle.kts") {
    Write-Host "[OK] Android project files are present"
}
