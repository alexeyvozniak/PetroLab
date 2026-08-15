#ifndef MyAppVersion
  #define MyAppVersion "0.0.0"
#endif

#define MyAppName "PetroLab"
#define MyAppPublisher "PetroLab"
#define MyAppExeName "launch_petrolab.vbs"

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
SetupLogging=yes

[Tasks]
Name: "desktopicon"; Description: "Создать ярлык на рабочем столе"; GroupDescription: "Ярлыки:"; Flags: checkedonce

[Dirs]
Name: "{userdocs}\PetroLab Data"

[Files]
Source: "..\dist\payload\current\*"; DestDir: "{app}\current"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "..\dist\payload\runtime\*"; DestDir: "{app}\runtime"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "launch_petrolab.vbs"; DestDir: "{app}"; Flags: ignoreversion
Source: "update_petrolab.ps1"; DestDir: "{app}"; Flags: ignoreversion
Source: "update_petrolab.cmd"; DestDir: "{app}"; Flags: ignoreversion
Source: "diagnose_petrolab.cmd"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{autoprograms}\PetroLab"; Filename: "{sys}\wscript.exe"; Parameters: """{app}\launch_petrolab.vbs"""; WorkingDir: "{app}\current"
Name: "{autoprograms}\Обновить PetroLab"; Filename: "{app}\update_petrolab.cmd"; WorkingDir: "{app}"
Name: "{autoprograms}\Диагностика PetroLab"; Filename: "{app}\diagnose_petrolab.cmd"; WorkingDir: "{app}"
Name: "{autodesktop}\PetroLab"; Filename: "{sys}\wscript.exe"; Parameters: """{app}\launch_petrolab.vbs"""; WorkingDir: "{app}\current"; Tasks: desktopicon

[Run]
Filename: "{sys}\wscript.exe"; Parameters: """{app}\launch_petrolab.vbs"""; Description: "Запустить PetroLab"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
; Intentionally only remove installer-owned cache/rollback directories.
; User scientific data live in {userdocs}\PetroLab Data and are never listed here.
Type: filesandordirs; Name: "{app}\previous"
Type: filesandordirs; Name: "{app}\runtime.previous"
Type: filesandordirs; Name: "{app}\update-staging"
