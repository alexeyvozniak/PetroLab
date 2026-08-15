$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"

$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$installer = Join-Path $RepoRoot "dist\PetroLab-Setup-x64.exe"
if (-not (Test-Path -LiteralPath $installer -PathType Leaf)) { throw "Installer is missing: $installer" }

$installRoot = Join-Path $env:RUNNER_TEMP "PetroLabInstallSmoke"
if ([string]::IsNullOrWhiteSpace($env:RUNNER_TEMP)) { $installRoot = Join-Path $env:TEMP "PetroLabInstallSmoke" }
$smokeData = Join-Path $env:TEMP "PetroLabInstalledData"
$documents = [Environment]::GetFolderPath("MyDocuments")
if ([string]::IsNullOrWhiteSpace($documents)) { $documents = Join-Path $env:USERPROFILE "Documents" }
New-Item -ItemType Directory -Force -Path $documents | Out-Null
$preservedData = Join-Path $documents "PetroLab Data"
$markerName = if ($env:GITHUB_RUN_ID) { "installer-preservation-marker-$($env:GITHUB_RUN_ID).txt" } else { "installer-preservation-marker-local.txt" }
$marker = Join-Path $preservedData $markerName

$launcherProcess = $null
$serverPid = $null

try {
    Remove-Item -LiteralPath $installRoot -Recurse -Force -ErrorAction SilentlyContinue
    Remove-Item -LiteralPath $smokeData -Recurse -Force -ErrorAction SilentlyContinue
    New-Item -ItemType Directory -Force -Path $preservedData, $smokeData | Out-Null
    Set-Content -LiteralPath $marker -Value "must survive uninstall" -Encoding ASCII

    $installProcess = Start-Process -FilePath $installer -ArgumentList @(
        "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/SP-", "/DIR=$installRoot"
    ) -Wait -PassThru
    if ($installProcess.ExitCode -ne 0) { throw "Silent installer returned exit code $($installProcess.ExitCode)." }

    $python = Join-Path $installRoot "runtime\python.exe"
    $app = Join-Path $installRoot "current\app.py"
    $launcherExe = Join-Path $installRoot "PetroLab.exe"
    $stateFile = Join-Path $installRoot "petrolab-server.state"
    $launcherLog = Join-Path $installRoot "logs\launcher.log"
    $updater = Join-Path $installRoot "update_petrolab.ps1"

    foreach ($required in @(
        $python,
        (Join-Path $installRoot "runtime\pythonw.exe"),
        $app,
        $launcherExe,
        (Join-Path $installRoot "PetroLab.ico"),
        (Join-Path $installRoot "PetroLab-Installer.ico"),
        (Join-Path $installRoot "launch_petrolab.vbs"),
        $updater,
        (Join-Path $installRoot "update_petrolab.cmd"),
        (Join-Path $installRoot "diagnose_petrolab.cmd")
    )) {
        if (-not (Test-Path -LiteralPath $required -PathType Leaf)) { throw "Installed file is missing: $required" }
    }

    $env:PETROLAB_DATA_DIR = $smokeData
    $env:PETROLAB_LAUNCHER_NO_BROWSER = "1"
    & $python -c "import sys; sys.path.insert(0, r'$($installRoot)\current'); import petrolab; from petrolab.storage import ensure_storage; ensure_storage(); print('installed payload OK', petrolab.__version__)"
    if ($LASTEXITCODE -ne 0) { throw "Installed payload smoke failed." }

    Remove-Item -LiteralPath $stateFile -Force -ErrorAction SilentlyContinue
    $launcherProcess = Start-Process -FilePath $launcherExe -PassThru
    $healthy = $false
    $port = $null
    for ($attempt = 0; $attempt -lt 120; $attempt++) {
        Start-Sleep -Milliseconds 500
        if ($launcherProcess.HasExited) {
            $tail = if (Test-Path $launcherLog) { (Get-Content $launcherLog -Tail 50) -join "`n" } else { "launcher.log missing" }
            throw "Installed PetroLab.exe exited before becoming healthy (code $($launcherProcess.ExitCode)).`n$tail"
        }
        if (-not (Test-Path -LiteralPath $stateFile -PathType Leaf)) { continue }
        $stateText = (Get-Content -LiteralPath $stateFile -Raw).Trim()
        $parts = $stateText -split '\|'
        if ($parts.Count -ne 2) { continue }
        $serverPid = [int]$parts[0]
        $port = [int]$parts[1]
        try {
            $response = Invoke-WebRequest -Uri "http://127.0.0.1:$port/_stcore/health" -UseBasicParsing -TimeoutSec 2
            if ($response.StatusCode -eq 200) { $healthy = $true; break }
        } catch {}
    }
    if (-not $healthy) {
        $tail = if (Test-Path $launcherLog) { (Get-Content $launcherLog -Tail 50) -join "`n" } else { "launcher.log missing" }
        throw "Installed PetroLab.exe did not make Streamlit healthy.`n$tail"
    }
    if (-not (Select-String -LiteralPath $launcherLog -Pattern "Server healthy" -Quiet)) {
        throw "Native launcher did not record a healthy startup in launcher.log."
    }

    # Re-launching must focus/reopen the existing server, not create a second one.
    $stateBefore = (Get-Content -LiteralPath $stateFile -Raw).Trim()
    $secondLaunch = Start-Process -FilePath $launcherExe -Wait -PassThru
    if ($secondLaunch.ExitCode -ne 0) { throw "Second PetroLab.exe launch returned $($secondLaunch.ExitCode)." }
    $stateAfter = (Get-Content -LiteralPath $stateFile -Raw).Trim()
    if ($stateAfter -ne $stateBefore) { throw "Second PetroLab.exe launch started a different server." }

    # Stop the app before testing transactional update/uninstall.
    if ($serverPid) { Stop-Process -Id $serverPid -Force -ErrorAction SilentlyContinue }
    if ($launcherProcess) {
        $launcherProcess.WaitForExit(10000) | Out-Null
        if (-not $launcherProcess.HasExited) { Stop-Process -Id $launcherProcess.Id -Force -ErrorAction SilentlyContinue }
    }
    $serverPid = $null
    $launcherProcess = $null
    Remove-Item Env:PETROLAB_LAUNCHER_NO_BROWSER -ErrorAction SilentlyContinue

    $targetSha = if ($env:GITHUB_SHA) { $env:GITHUB_SHA } else { (git rev-parse HEAD).Trim() }
    Set-Content -LiteralPath (Join-Path $installRoot "current\.petrolab_build_sha") -Value ("0" * 40) -NoNewline -Encoding ASCII
    $env:PETROLAB_UPDATE_TARGET_SHA = $targetSha
    & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $updater -NoLaunch
    $updaterExit = $LASTEXITCODE
    Remove-Item Env:PETROLAB_UPDATE_TARGET_SHA -ErrorAction SilentlyContinue
    if ($updaterExit -ne 0) { throw "Windows PowerShell 5.1 updater smoke failed with exit code $updaterExit." }
    $updatedSha = (Get-Content -LiteralPath (Join-Path $installRoot "current\.petrolab_build_sha") -Raw).Trim()
    if ($updatedSha -ne $targetSha) { throw "Transactional updater did not activate the requested build." }
    if (-not (Test-Path -LiteralPath (Join-Path $installRoot "previous\app.py") -PathType Leaf)) {
        throw "Transactional updater did not retain a rollback application copy."
    }

    $uninstaller = Join-Path $installRoot "unins000.exe"
    if (-not (Test-Path -LiteralPath $uninstaller -PathType Leaf)) { throw "Uninstaller was not created." }
    $uninstallProcess = Start-Process -FilePath $uninstaller -ArgumentList @(
        "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART"
    ) -Wait -PassThru
    if ($uninstallProcess.ExitCode -ne 0) { throw "Silent uninstall failed with exit code $($uninstallProcess.ExitCode)." }
    if (-not (Test-Path -LiteralPath $marker -PathType Leaf)) { throw "Uninstall removed user scientific data marker." }

    Write-Host "Installed PetroLab.exe launcher, update and uninstall smoke passed."
}
finally {
    if ($serverPid) { Stop-Process -Id $serverPid -Force -ErrorAction SilentlyContinue }
    if ($launcherProcess -and -not $launcherProcess.HasExited) { Stop-Process -Id $launcherProcess.Id -Force -ErrorAction SilentlyContinue }
    Remove-Item Env:PETROLAB_LAUNCHER_NO_BROWSER -ErrorAction SilentlyContinue
    Remove-Item Env:PETROLAB_UPDATE_TARGET_SHA -ErrorAction SilentlyContinue
    Remove-Item -LiteralPath $marker -Force -ErrorAction SilentlyContinue
    Remove-Item -LiteralPath $smokeData -Recurse -Force -ErrorAction SilentlyContinue
}
