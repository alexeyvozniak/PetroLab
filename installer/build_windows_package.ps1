$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"

$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
Set-Location $RepoRoot

$Dist = Join-Path $RepoRoot "dist"
$Payload = Join-Path $Dist "payload"
$Current = Join-Path $Payload "current"
$Runtime = Join-Path $Payload "runtime"

if (Test-Path -LiteralPath $Dist) {
    Remove-Item -LiteralPath $Dist -Recurse -Force
}
New-Item -ItemType Directory -Force -Path $Current, $Runtime | Out-Null

Copy-Item app.py, requirements.txt, README.md -Destination $Current
Copy-Item petrolab, .streamlit, docs -Destination $Current -Recurse
$buildSha = if ($env:GITHUB_SHA) { $env:GITHUB_SHA } else { "local-build" }
Set-Content -LiteralPath (Join-Path $Current ".petrolab_build_sha") -Value $buildSha -NoNewline -Encoding ASCII

$pythonZip = Join-Path $Dist "python-embed.zip"
$pythonUrl = "https://www.python.org/ftp/python/3.12.10/python-3.12.10-embed-amd64.zip"
Invoke-WebRequest -Uri $pythonUrl -OutFile $pythonZip
Expand-Archive -LiteralPath $pythonZip -DestinationPath $Runtime -Force

$pth = Get-ChildItem -LiteralPath $Runtime -Filter "python*._pth" | Select-Object -First 1
if (-not $pth) { throw "Embedded Python _pth file was not found." }
$lines = Get-Content -LiteralPath $pth.FullName
$lines = $lines | ForEach-Object { if ($_ -eq "#import site") { "import site" } else { $_ } }
if ($lines -notcontains "Lib\site-packages") { $lines += "Lib\site-packages" }
Set-Content -LiteralPath $pth.FullName -Value $lines -Encoding ASCII
New-Item -ItemType Directory -Force -Path (Join-Path $Runtime "Lib\site-packages") | Out-Null

python -m pip install --disable-pip-version-check --target (Join-Path $Runtime "Lib\site-packages") pip
python -m pip install --disable-pip-version-check --target (Join-Path $Runtime "Lib\site-packages") -r requirements.txt

$runtimePython = Join-Path $Runtime "python.exe"
& $runtimePython -m pip check
if ($LASTEXITCODE -ne 0) { throw "Embedded runtime pip check failed." }
& $runtimePython -c "import streamlit,pandas,numpy,matplotlib,plotly,openpyxl,sklearn; print('portable runtime OK')"
if ($LASTEXITCODE -ne 0) { throw "Embedded runtime import smoke failed." }

$env:PETROLAB_DATA_DIR = Join-Path $env:TEMP "petrolab-installer-build-smoke-data"
if (Test-Path $env:PETROLAB_DATA_DIR) { Remove-Item $env:PETROLAB_DATA_DIR -Recurse -Force }
& $runtimePython -c "import sys; sys.path.insert(0, r'$Current'); import petrolab; from petrolab.storage import ensure_storage; ensure_storage(); print('PetroLab', petrolab.__version__, 'installer payload OK')"
if ($LASTEXITCODE -ne 0) { throw "PetroLab installer payload smoke failed." }

$versionLine = Select-String -Path petrolab\__init__.py -Pattern '^__version__\s*=\s*"([^"]+)"'
if (-not $versionLine.Matches.Count) { throw "Could not determine PetroLab version." }
$version = $versionLine.Matches[0].Groups[1].Value
if ($env:GITHUB_ENV) {
    "PETROLAB_VERSION=$version" | Out-File -FilePath $env:GITHUB_ENV -Encoding utf8 -Append
}

$appIcon = Join-Path $Dist "PetroLab.ico"
$installerIcon = Join-Path $Dist "PetroLab-Installer.ico"
$launcher = Join-Path $Dist "PetroLab.exe"

magick -background none installer\petrolab-icon.svg -define icon:auto-resize=256,128,64,48,32,24,16 $appIcon
if ($LASTEXITCODE -ne 0 -or -not (Test-Path -LiteralPath $appIcon -PathType Leaf)) {
    throw "Could not build PetroLab.ico."
}
magick -background none installer\petrolab-installer-icon.svg -define icon:auto-resize=256,128,64,48,32,24,16 $installerIcon
if ($LASTEXITCODE -ne 0 -or -not (Test-Path -LiteralPath $installerIcon -PathType Leaf)) {
    throw "Could not build PetroLab-Installer.ico."
}

# Keep Windows file metadata synchronized with the Python application version.
$versionParts = $version.Split('.')
while ($versionParts.Count -lt 4) { $versionParts += "0" }
$assemblyVersion = ($versionParts[0..3] -join '.')
$assemblyInfo = Join-Path $Dist "LauncherVersion.cs"
@"
using System.Reflection;
[assembly: AssemblyTitle("PetroLab")]
[assembly: AssemblyProduct("PetroLab")]
[assembly: AssemblyDescription("PetroLab petrology and geochemistry workspace")]
[assembly: AssemblyCompany("PetroLab")]
[assembly: AssemblyVersion("$assemblyVersion")]
[assembly: AssemblyFileVersion("$assemblyVersion")]
[assembly: AssemblyInformationalVersion("$version")]
"@ | Set-Content -LiteralPath $assemblyInfo -Encoding UTF8

$csc = Join-Path $env:WINDIR "Microsoft.NET\Framework64\v4.0.30319\csc.exe"
if (-not (Test-Path -LiteralPath $csc -PathType Leaf)) {
    throw "The .NET Framework C# compiler required for PetroLab.exe was not found."
}
& $csc /nologo /target:winexe /platform:x64 /optimize+ "/win32icon:$appIcon" "/out:$launcher" /reference:System.dll /reference:System.Windows.Forms.dll installer\PetroLabLauncher.cs $assemblyInfo
if ($LASTEXITCODE -ne 0 -or -not (Test-Path -LiteralPath $launcher -PathType Leaf)) {
    throw "Native PetroLab launcher compilation failed."
}

iscc "/DMyAppVersion=$version" installer\PetroLab.iss
if ($LASTEXITCODE -ne 0) { throw "Inno Setup compilation failed." }
$installer = Join-Path $Dist "PetroLab-Setup-x64.exe"
if (-not (Test-Path -LiteralPath $installer -PathType Leaf)) { throw "Installer output was not created." }
$hash = (Get-FileHash -LiteralPath $installer -Algorithm SHA256).Hash.ToLowerInvariant()
"$hash  PetroLab-Setup-x64.exe" | Set-Content -LiteralPath (Join-Path $Dist "PetroLab-Setup-x64.sha256") -Encoding ASCII

Write-Host "Built PetroLab $version Windows package with native launcher and branded icons."
