param(
    [Parameter(Mandatory = $true)]
    [string]$InstallRoot,
    [int]$TimeoutSeconds = 20
)

$ErrorActionPreference = "Stop"

function Normalize-Path([string]$Path) {
    if ([string]::IsNullOrWhiteSpace($Path)) { return "" }
    try { return [System.IO.Path]::GetFullPath($Path).TrimEnd('\') } catch { return $Path.TrimEnd('\') }
}

function Same-Path([string]$Left, [string]$Right) {
    return [string]::Equals((Normalize-Path $Left), (Normalize-Path $Right), [System.StringComparison]::OrdinalIgnoreCase)
}

function Process-ExecutablePath([int]$ProcessId) {
    try {
        $process = Get-CimInstance Win32_Process -Filter "ProcessId=$ProcessId" -ErrorAction Stop
        return [string]$process.ExecutablePath
    } catch {
        try {
            return [string](Get-Process -Id $ProcessId -ErrorAction Stop).Path
        } catch {
            return ""
        }
    }
}

function Stop-ExactProcess([int]$ProcessId, [string]$ExpectedExecutable) {
    if ($ProcessId -le 0) { return $false }
    $actual = Process-ExecutablePath $ProcessId
    if (-not $actual -or -not (Same-Path $actual $ExpectedExecutable)) { return $false }
    try {
        Stop-Process -Id $ProcessId -Force -ErrorAction Stop
        return $true
    } catch {
        return $false
    }
}

function Test-FileUnlocked([string]$Path) {
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) { return $true }
    try {
        $stream = [System.IO.File]::Open($Path, 'Open', 'ReadWrite', 'None')
        $stream.Dispose()
        return $true
    } catch {
        return $false
    }
}

$InstallRoot = Normalize-Path $InstallRoot
$runtimePython = Join-Path $InstallRoot "runtime\python.exe"
$stateFile = Join-Path $InstallRoot "petrolab-server.state"
$lockProbe = Join-Path $InstallRoot "runtime\libcrypto-3.dll"

# Preferred path: stop only the PID PetroLab itself recorded and only if that PID
# really points at this installation's embedded runtime. A recycled PID can never
# kill an unrelated process because executable-path validation fails.
if (Test-Path -LiteralPath $stateFile -PathType Leaf) {
    try {
        $text = (Get-Content -LiteralPath $stateFile -Raw -ErrorAction Stop).Trim()
        $parts = $text -split '\|'
        if ($parts.Count -ge 1) {
            $pidFromState = 0
            if ([int]::TryParse($parts[0], [ref]$pidFromState)) {
                [void](Stop-ExactProcess $pidFromState $runtimePython)
            }
        }
    } catch {}
}

# A stale/missing state file must not make upgrades fail forever. Enumerate python
# processes, but terminate only an executable whose path is exactly this install's
# runtime\python.exe. Other Python sessions on the user's machine are untouched.
try {
    foreach ($process in Get-CimInstance Win32_Process -Filter "Name='python.exe' OR Name='pythonw.exe'") {
        $path = [string]$process.ExecutablePath
        if ($path -and (Same-Path $path $runtimePython)) {
            try { Stop-Process -Id ([int]$process.ProcessId) -Force -ErrorAction SilentlyContinue } catch {}
        }
    }
} catch {
    try {
        foreach ($process in Get-Process python, pythonw -ErrorAction SilentlyContinue) {
            $path = ""
            try { $path = [string]$process.Path } catch {}
            if ($path -and (Same-Path $path $runtimePython)) {
                try { Stop-Process -Id $process.Id -Force -ErrorAction SilentlyContinue } catch {}
            }
        }
    } catch {}
}

$deadline = [DateTime]::UtcNow.AddSeconds([Math]::Max(1, $TimeoutSeconds))
do {
    $runtimeProcessAlive = $false
    try {
        foreach ($process in Get-CimInstance Win32_Process -Filter "Name='python.exe' OR Name='pythonw.exe'") {
            $path = [string]$process.ExecutablePath
            if ($path -and (Same-Path $path $runtimePython)) {
                $runtimeProcessAlive = $true
                break
            }
        }
    } catch {}

    if (-not $runtimeProcessAlive -and (Test-FileUnlocked $lockProbe)) {
        Remove-Item -LiteralPath $stateFile -Force -ErrorAction SilentlyContinue
        exit 0
    }
    Start-Sleep -Milliseconds 200
} while ([DateTime]::UtcNow -lt $deadline)

Write-Error "PetroLab is still running or runtime files are locked. Close PetroLab and retry the update."
exit 1
