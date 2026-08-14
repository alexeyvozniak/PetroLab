param(
    [switch]$NoLaunch
)

$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12

$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$Current = Join-Path $Root "current"
$Previous = Join-Path $Root "previous"
$Runtime = Join-Path $Root "runtime"
$RuntimePrevious = Join-Path $Root "runtime.previous"
$BuildFile = Join-Path $Current ".petrolab_build_sha"
$RepoApi = "https://api.github.com/repos/alexeyvozniak/PetroLab"
$RepoZipBase = "https://github.com/alexeyvozniak/PetroLab/archive"
$VerifiedRefUrl = "$RepoApi/git/ref/tags/windows-latest"
$Headers = @{
    "User-Agent" = "PetroLab-Updater"
    "Accept" = "application/vnd.github+json"
}

function Write-Stage([string]$Text) {
    Write-Host ""
    Write-Host "  $Text" -ForegroundColor Cyan
}

function Require-File([string]$Path, [string]$Label) {
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) {
        throw "$Label not found: $Path"
    }
}

function Get-FileHashText([string]$Path) {
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) {
        return ""
    }
    return (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash
}

function Resolve-VerifiedBuildSha {
    # CI may supply an exact target SHA to exercise Windows PowerShell 5.1 without
    # moving the public verified-update channel. Normal user runs never set this.
    if (-not [string]::IsNullOrWhiteSpace($env:PETROLAB_UPDATE_TARGET_SHA)) {
        return $env:PETROLAB_UPDATE_TARGET_SHA.Trim()
    }

    try {
        $verifiedRef = Invoke-RestMethod -Uri $VerifiedRefUrl -Headers $Headers
    }
    catch {
        throw "No verified Windows update is available yet. Try again later or reinstall from the latest PetroLab Windows release."
    }
    $sha = [string]$verifiedRef.object.sha
    if ([string]::IsNullOrWhiteSpace($sha)) {
        throw "The verified Windows update channel did not return a commit SHA."
    }
    return $sha.Trim()
}

function Copy-AppPayload([string]$SourceRoot, [string]$DestinationRoot, [string]$BuildSha) {
    New-Item -ItemType Directory -Force -Path $DestinationRoot | Out-Null
    foreach ($name in @("app.py", "requirements.txt", "README.md")) {
        $sourcePath = Join-Path $SourceRoot $name
        if (Test-Path -LiteralPath $sourcePath) {
            Copy-Item -LiteralPath $sourcePath -Destination (Join-Path $DestinationRoot $name) -Force
        }
    }
    foreach ($name in @("petrolab", ".streamlit", "docs")) {
        $sourcePath = Join-Path $SourceRoot $name
        if (Test-Path -LiteralPath $sourcePath) {
            Copy-Item -LiteralPath $sourcePath -Destination (Join-Path $DestinationRoot $name) -Recurse -Force
        }
    }
    Set-Content -LiteralPath (Join-Path $DestinationRoot ".petrolab_build_sha") -Value $BuildSha -NoNewline -Encoding ASCII
}

function Test-StagedApp([string]$PythonExe, [string]$SourceRoot, [string]$TempData) {
    Require-File $PythonExe "PetroLab Python"
    Require-File (Join-Path $SourceRoot "app.py") "PetroLab app"
    Require-File (Join-Path $SourceRoot "requirements.txt") "PetroLab requirements"

    New-Item -ItemType Directory -Force -Path $TempData | Out-Null
    $oldData = $env:PETROLAB_DATA_DIR
    try {
        $env:PETROLAB_DATA_DIR = $TempData
        $escaped = $SourceRoot.Replace("'", "''")
        & $PythonExe -c "import sys; sys.path.insert(0, r'$escaped'); import petrolab; from petrolab.storage import ensure_storage; ensure_storage(); import pandas, numpy, streamlit; print('PetroLab', petrolab.__version__, 'smoke OK')"
        if ($LASTEXITCODE -ne 0) {
            throw "The staged PetroLab smoke test failed."
        }
    }
    finally {
        if ($null -eq $oldData) {
            Remove-Item Env:PETROLAB_DATA_DIR -ErrorAction SilentlyContinue
        }
        else {
            $env:PETROLAB_DATA_DIR = $oldData
        }
    }
}

Write-Host ""
Write-Host "  +-----------------------------------------------+" -ForegroundColor DarkCyan
Write-Host "  |              PETROLAB UPDATE                 |" -ForegroundColor DarkCyan
Write-Host "  +-----------------------------------------------+" -ForegroundColor DarkCyan
Write-Host "  Scientific data, Excel files and images are not modified."

$tempRoot = Join-Path $env:TEMP ("PetroLab-update-" + [guid]::NewGuid().ToString("N"))
$zipPath = Join-Path $tempRoot "petrolab.zip"
$extractRoot = Join-Path $tempRoot "source"
$appStage = Join-Path $tempRoot "current.new"
$runtimeStage = Join-Path $tempRoot "runtime.new"
$tempData = Join-Path $tempRoot "smoke-data"
$codeSwapped = $false
$runtimeSwapped = $false

try {
    Require-File (Join-Path $Runtime "python.exe") "Embedded Python runtime"
    Require-File (Join-Path $Current "app.py") "Current PetroLab app"

    $appPath = Join-Path $Current "app.py"
    $running = Get-CimInstance Win32_Process -ErrorAction SilentlyContinue | Where-Object {
        $_.CommandLine -and ($_.CommandLine.IndexOf($appPath, [System.StringComparison]::OrdinalIgnoreCase) -ge 0)
    }
    if ($running) {
        Write-Host ""
        Write-Host "  PetroLab is currently running." -ForegroundColor Yellow
        Write-Host "  Close the PetroLab browser/server and run the updater again."
        if (-not $NoLaunch) {
            Read-Host "  Press Enter to close"
        }
        exit 2
    }

    Write-Stage "Checking the verified Windows build..."
    $remoteSha = Resolve-VerifiedBuildSha

    $localSha = ""
    if (Test-Path -LiteralPath $BuildFile) {
        $localSha = (Get-Content -LiteralPath $BuildFile -Raw).Trim()
    }

    if ($localSha -eq $remoteSha) {
        Write-Host ""
        Write-Host "  PetroLab is already up to date." -ForegroundColor Green
        if (-not $NoLaunch) {
            $answer = Read-Host "  Start PetroLab now? [Y/N]"
            if ($answer -match "^[Yy]") {
                Start-Process "wscript.exe" -ArgumentList ('"' + (Join-Path $Root "launch_petrolab.vbs") + '"')
            }
        }
        exit 0
    }

    New-Item -ItemType Directory -Force -Path $tempRoot, $extractRoot | Out-Null
    Write-Stage "Downloading verified source $($remoteSha.Substring(0, 12))..."
    Invoke-WebRequest -Uri "$RepoZipBase/$remoteSha.zip" -Headers $Headers -OutFile $zipPath
    Expand-Archive -LiteralPath $zipPath -DestinationPath $extractRoot -Force
    $sourceRoot = (Get-ChildItem -LiteralPath $extractRoot -Directory | Select-Object -First 1).FullName
    if ([string]::IsNullOrWhiteSpace($sourceRoot)) {
        throw "Downloaded archive did not contain the PetroLab source directory."
    }

    Require-File (Join-Path $sourceRoot "app.py") "Downloaded PetroLab app"
    Require-File (Join-Path $sourceRoot "requirements.txt") "Downloaded requirements"

    $currentRequirements = Join-Path $Current "requirements.txt"
    $newRequirements = Join-Path $sourceRoot "requirements.txt"
    $requirementsChanged = (Get-FileHashText $currentRequirements) -ne (Get-FileHashText $newRequirements)
    $pythonForTest = Join-Path $Runtime "python.exe"

    if ($requirementsChanged) {
        Write-Stage "Python requirements changed; preparing a transactional runtime update..."
        Copy-Item -LiteralPath $Runtime -Destination $runtimeStage -Recurse -Force
        $pythonForTest = Join-Path $runtimeStage "python.exe"
        & $pythonForTest -m pip install --disable-pip-version-check --upgrade -r $newRequirements
        if ($LASTEXITCODE -ne 0) {
            throw "Could not install the new PetroLab Python requirements."
        }
        & $pythonForTest -m pip check
        if ($LASTEXITCODE -ne 0) {
            throw "The updated Python runtime failed pip check."
        }
    }

    Write-Stage "Testing the new build before replacing the installed copy..."
    Test-StagedApp -PythonExe $pythonForTest -SourceRoot $sourceRoot -TempData $tempData
    Copy-AppPayload -SourceRoot $sourceRoot -DestinationRoot $appStage -BuildSha $remoteSha

    Write-Stage "Creating a rollback point and switching builds..."
    if (Test-Path -LiteralPath $Previous) {
        Remove-Item -LiteralPath $Previous -Recurse -Force
    }
    if (Test-Path -LiteralPath $RuntimePrevious) {
        Remove-Item -LiteralPath $RuntimePrevious -Recurse -Force
    }

    if ($requirementsChanged) {
        Move-Item -LiteralPath $Runtime -Destination $RuntimePrevious
        Move-Item -LiteralPath $runtimeStage -Destination $Runtime
        $runtimeSwapped = $true
    }

    Move-Item -LiteralPath $Current -Destination $Previous
    Move-Item -LiteralPath $appStage -Destination $Current
    $codeSwapped = $true

    # Refresh installer-owned helpers when a newer version is present in the source tree.
    $installerSource = Join-Path $sourceRoot "installer"
    foreach ($helper in @("launch_petrolab.vbs", "update_petrolab.cmd", "diagnose_petrolab.cmd")) {
        $candidate = Join-Path $installerSource $helper
        if (Test-Path -LiteralPath $candidate) {
            Copy-Item -LiteralPath $candidate -Destination (Join-Path $Root $helper) -Force
        }
    }
    $selfCandidate = Join-Path $installerSource "update_petrolab.ps1"
    if (Test-Path -LiteralPath $selfCandidate) {
        Copy-Item -LiteralPath $selfCandidate -Destination (Join-Path $Root "update_petrolab.ps1") -Force
    }

    Write-Host ""
    Write-Host "  ------------------------------------------------" -ForegroundColor Green
    Write-Host "  PetroLab updated successfully." -ForegroundColor Green
    Write-Host "  Build: $($remoteSha.Substring(0, 12))" -ForegroundColor Green
    Write-Host "  Previous application build is kept for rollback." -ForegroundColor Green
    Write-Host "  Your data folder was not touched." -ForegroundColor Green
    Write-Host "  ------------------------------------------------" -ForegroundColor Green

    if (-not $NoLaunch) {
        $answer = Read-Host "  Start PetroLab now? [Y/N]"
        if ($answer -match "^[Yy]") {
            Start-Process "wscript.exe" -ArgumentList ('"' + (Join-Path $Root "launch_petrolab.vbs") + '"')
        }
    }
}
catch {
    Write-Host ""
    Write-Host "  Update failed: $($_.Exception.Message)" -ForegroundColor Red
    Write-Host "  Attempting rollback..." -ForegroundColor Yellow

    try {
        if ($codeSwapped -and (Test-Path -LiteralPath $Previous)) {
            if (Test-Path -LiteralPath $Current) {
                Remove-Item -LiteralPath $Current -Recurse -Force
            }
            Move-Item -LiteralPath $Previous -Destination $Current
        }
        if ($runtimeSwapped -and (Test-Path -LiteralPath $RuntimePrevious)) {
            if (Test-Path -LiteralPath $Runtime) {
                Remove-Item -LiteralPath $Runtime -Recurse -Force
            }
            Move-Item -LiteralPath $RuntimePrevious -Destination $Runtime
        }
        Write-Host "  The previous PetroLab installation remains available." -ForegroundColor Yellow
    }
    catch {
        Write-Host "  Automatic rollback also failed. Run PetroLab Diagnostics." -ForegroundColor Red
    }

    if (-not $NoLaunch) {
        Read-Host "  Press Enter to close"
    }
    exit 1
}
finally {
    if (Test-Path -LiteralPath $tempRoot) {
        Remove-Item -LiteralPath $tempRoot -Recurse -Force -ErrorAction SilentlyContinue
    }
}
