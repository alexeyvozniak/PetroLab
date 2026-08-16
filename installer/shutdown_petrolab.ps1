param(
    [Parameter(Mandatory = $true)]
    [string]$InstallRoot
)

$ErrorActionPreference = "Stop"

function Normalize-Path([string]$Path) {
    if ([string]::IsNullOrWhiteSpace($Path)) { return "" }
    try { return [IO.Path]::GetFullPath($Path).TrimEnd('\') }
    catch { return $Path.TrimEnd('\') }
}

function Get-ExecutablePath([int]$ProcessId) {
    try {
        $record = Get-CimInstance Win32_Process -Filter "ProcessId = $ProcessId" -ErrorAction Stop
        if ($record -and $record.ExecutablePath) { return [string]$record.ExecutablePath }
    } catch {}
    try {
        $process = Get-Process -Id $ProcessId -ErrorAction Stop
        return [string]$process.Path
    } catch {}
    return $null
}

function Stop-ExactProcess([int]$ProcessId, [string]$ExpectedPath) {
    $actualPath = Get-ExecutablePath $ProcessId
    if ([string]::IsNullOrWhiteSpace($actualPath)) { return $false }
    if ((Normalize-Path $actualPath) -ine (Normalize-Path $ExpectedPath)) { return $false }

    Stop-Process -Id $ProcessId -Force -ErrorAction SilentlyContinue
    for ($attempt = 0; $attempt -lt 100; $attempt++) {
        if (-not (Get-Process -Id $ProcessId -ErrorAction SilentlyContinue)) { return $true }
        Start-Sleep -Milliseconds 100
    }
    throw "PetroLab process $ProcessId did not stop in time: $actualPath"
}

function Stop-AllAtPath([string]$ExecutablePath) {
    $expected = Normalize-Path $ExecutablePath
    if ([string]::IsNullOrWhiteSpace($expected)) { return }
    try {
        $records = Get-CimInstance Win32_Process -ErrorAction Stop
        foreach ($record in $records) {
            if (-not $record.ExecutablePath) { continue }
            if ((Normalize-Path ([string]$record.ExecutablePath)) -ine $expected) { continue }
            Stop-ExactProcess ([int]$record.ProcessId) $ExecutablePath | Out-Null
        }
    } catch {
        # Exact PID from the launcher state is handled separately.  Failure to enumerate
        # unrelated processes must not make a healthy upgrade impossible.
    }
}

function Wait-FileUnlocked([string]$Path) {
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) { return }
    for ($attempt = 0; $attempt -lt 150; $attempt++) {
        $stream = $null
        try {
            $stream = [IO.File]::Open($Path, [IO.FileMode]::Open, [IO.FileAccess]::ReadWrite, [IO.FileShare]::None)
            return
        } catch {
            Start-Sleep -Milliseconds 100
        } finally {
            if ($stream) { $stream.Dispose() }
        }
    }
    throw "Installed PetroLab file is still locked after shutdown: $Path"
}

$root = Normalize-Path $InstallRoot
$python = Join-Path $root "runtime\python.exe"
$launcher = Join-Path $root "PetroLab.exe"
$stateFile = Join-Path $root "petrolab-server.state"

# The launcher writes PID|port only after the embedded Streamlit server is healthy.
# Validate the executable path before terminating that PID so a stale/reused PID can
# never kill an unrelated process.
if (Test-Path -LiteralPath $stateFile -PathType Leaf) {
    try {
        $parts = ((Get-Content -LiteralPath $stateFile -Raw).Trim()) -split '\|'
        $statePid = 0
        if ($parts.Count -ge 1 -and [int]::TryParse($parts[0], [ref]$statePid)) {
            Stop-ExactProcess $statePid $python | Out-Null
        }
    } catch {
        throw "Could not stop the running PetroLab server safely. $($_.Exception.Message)"
    } finally {
        Remove-Item -LiteralPath $stateFile -Force -ErrorAction SilentlyContinue
    }
}

# Also handle an interrupted/stale launcher state: only processes whose executable
# path is exactly inside this installation are eligible for termination.
Stop-AllAtPath $python
Stop-AllAtPath $launcher

Wait-FileUnlocked $python
Wait-FileUnlocked (Join-Path $root "runtime\libcrypto-3.dll")
