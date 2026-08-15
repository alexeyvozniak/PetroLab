#ifndef MyAppVersion
  #define MyAppVersion "0.0.0"
#endif

#define MyAppName "PetroLab"
#define MyAppPublisher "PetroLab"
#define MyAppExeName "PetroLab.exe"

[Setup]
AppId={{8C86AB42-817E-4B50-A3F0-6F966BA0D8E1}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={localappdata}\Programs\PetroLab
DefaultGroupName=PetroLab
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir=..\dist
OutputBaseFilename=PetroLab-Setup-x64
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
CloseApplications=yes
RestartApplications=no
UninstallDisplayName=PetroLab
UninstallDisplayIcon={app}\PetroLab.exe
SetupIconFile=..\dist\PetroLab-Installer.ico
SetupLogging=yes

[Tasks]
Name: "desktopicon"; Description: "Создать ярлык на рабочем столе"; GroupDescription: "Ярлыки:"; Flags: checkedonce

[Dirs]
Name: "{userdocs}\PetroLab Data"
Name: "{app}\logs"

[Files]
Source: "..\dist\payload\current\*"; DestDir: "{app}\current"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "..\dist\payload\runtime\*"; DestDir: "{app}\runtime"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "..\dist\PetroLab.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\dist\PetroLab.ico"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\dist\PetroLab-Installer.ico"; DestDir: "{app}"; Flags: ignoreversion
Source: "launch_petrolab.vbs"; DestDir: "{app}"; Flags: ignoreversion
Source: "update_petrolab.ps1"; DestDir: "{app}"; Flags: ignoreversion
Source: "update_petrolab.cmd"; DestDir: "{app}"; Flags: ignoreversion
Source: "diagnose_petrolab.cmd"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{autoprograms}\PetroLab"; Filename: "{app}\PetroLab.exe"; WorkingDir: "{app}\current"; IconFilename: "{app}\PetroLab.exe"
Name: "{autoprograms}\Обновить PetroLab"; Filename: "{app}\update_petrolab.cmd"; WorkingDir: "{app}"; IconFilename: "{app}\PetroLab.exe"
Name: "{autoprograms}\Диагностика PetroLab"; Filename: "{app}\diagnose_petrolab.cmd"; WorkingDir: "{app}"; IconFilename: "{app}\PetroLab.exe"
Name: "{autodesktop}\PetroLab"; Filename: "{app}\PetroLab.exe"; WorkingDir: "{app}\current"; IconFilename: "{app}\PetroLab.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\PetroLab.exe"; Description: "Запустить PetroLab"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
; Intentionally only remove installer-owned cache/rollback directories.
; User scientific data live in {userdocs}\PetroLab Data and are never listed here.
Type: filesandordirs; Name: "{app}\previous"
Type: filesandordirs; Name: "{app}\runtime.previous"
Type: filesandordirs; Name: "{app}\update-staging"
Type: filesandordirs; Name: "{app}\logs"
Type: files; Name: "{app}\petrolab-server.state"
