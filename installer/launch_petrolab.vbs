Option Explicit

Dim fso, shell, rootDir, launcherExe, currentDir, pythonExe, appFile, dataDir, command
Set fso = CreateObject("Scripting.FileSystemObject")
Set shell = CreateObject("WScript.Shell")

rootDir = fso.GetParentFolderName(WScript.ScriptFullName)
launcherExe = fso.BuildPath(rootDir, "PetroLab.exe")

' New installations use the native launcher. Keep this script only as a
' compatibility bridge for updater shortcuts from older installations.
If fso.FileExists(launcherExe) Then
    shell.Run Chr(34) & launcherExe & Chr(34), 0, False
    WScript.Quit 0
End If

' Legacy fallback for installations created before the native launcher existed.
currentDir = fso.BuildPath(rootDir, "current")
pythonExe = fso.BuildPath(rootDir, "runtime\pythonw.exe")
appFile = fso.BuildPath(currentDir, "app.py")
dataDir = fso.BuildPath(shell.SpecialFolders("MyDocuments"), "PetroLab Data")

If Not fso.FileExists(pythonExe) Then
    MsgBox "Не найден встроенный Python PetroLab. Запустите 'Диагностика PetroLab' или переустановите программу.", 16, "PetroLab"
    WScript.Quit 1
End If

If Not fso.FileExists(appFile) Then
    MsgBox "Не найден app.py. Запустите 'Диагностика PetroLab' или переустановите программу.", 16, "PetroLab"
    WScript.Quit 1
End If

If Not fso.FolderExists(dataDir) Then
    fso.CreateFolder(dataDir)
End If

shell.Environment("PROCESS")("PETROLAB_DATA_DIR") = dataDir
shell.CurrentDirectory = currentDir

command = Chr(34) & pythonExe & Chr(34) & _
          " -m streamlit run " & Chr(34) & appFile & Chr(34) & _
          " --server.headless=false --browser.gatherUsageStats=false"

shell.Run command, 0, False
