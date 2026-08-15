from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent
INSTALLER = ROOT / "installer"


class WindowsInstallerContractTests(unittest.TestCase):
    def test_installer_separates_program_files_from_scientific_data(self):
        iss = (INSTALLER / "PetroLab.iss").read_text(encoding="utf-8")
        self.assertIn(r"DefaultDirName={localappdata}\Programs\PetroLab", iss)
        self.assertIn(r'Name: "{userdocs}\PetroLab Data"', iss)
        uninstall_section = iss.split("[UninstallDelete]", 1)[1]
        active_uninstall_lines = "\n".join(
            line for line in uninstall_section.splitlines() if not line.lstrip().startswith(";")
        )
        self.assertNotIn(r"{userdocs}\PetroLab Data", active_uninstall_lines)
        self.assertIn(r'Type: filesandordirs; Name: "{app}\runtime.previous"', active_uninstall_lines)

    def test_shortcuts_use_real_petrolab_exe_and_distinct_installer_icon(self):
        iss = (INSTALLER / "PetroLab.iss").read_text(encoding="utf-8")
        self.assertIn('#define MyAppExeName "PetroLab.exe"', iss)
        self.assertIn(r"SetupIconFile=..\dist\PetroLab-Installer.ico", iss)
        self.assertIn(r"UninstallDisplayIcon={app}\PetroLab.exe", iss)
        self.assertIn(r'Source: "..\dist\PetroLab.ico"; DestDir: "{app}"', iss)
        self.assertIn(r'Source: "..\dist\PetroLab-Installer.ico"; DestDir: "{app}"', iss)
        self.assertIn(r'Filename: "{app}\PetroLab.exe"', iss)
        self.assertIn(r'IconFilename: "{app}\PetroLab.exe"', iss)
        self.assertNotIn(r'Filename: "{sys}\wscript.exe"', iss)
        self.assertTrue((INSTALLER / "petrolab-icon.svg").is_file())
        self.assertTrue((INSTALLER / "petrolab-installer-icon.svg").is_file())

    def test_native_launcher_has_health_check_logging_and_single_start_guard(self):
        launcher = (INSTALLER / "PetroLabLauncher.cs").read_text(encoding="utf-8")
        for marker in [
            'Path.Combine(root, "runtime", "python.exe")',
            'Path.Combine(current, "app.py")',
            'Environment.GetEnvironmentVariable("PETROLAB_DATA_DIR")',
            '"/_stcore/health"',
            'Path.Combine(root, "petrolab-server.state")',
            'PETROLAB_LAUNCHER_NO_BROWSER',
            'browser.UseShellExecute = true',
            'server.BeginErrorReadLine()',
            'Path.Combine(logDir, "launcher.log")',
            '@"Local\\PetroLab-Native-Launcher"',
            'TryExistingServer',
            'FindFreePort',
        ]:
            self.assertIn(marker, launcher)
        self.assertIn("Another PetroLab launcher is starting", launcher)
        self.assertIn("launchMutex.WaitOne", launcher)

    def test_legacy_vbs_is_only_a_compatibility_bridge(self):
        launcher = (INSTALLER / "launch_petrolab.vbs").read_text(encoding="utf-8")
        self.assertIn('launcherExe = fso.BuildPath(rootDir, "PetroLab.exe")', launcher)
        self.assertIn("If fso.FileExists(launcherExe) Then", launcher)
        self.assertIn(r'"runtime\pythonw.exe"', launcher)

    def test_build_script_generates_two_multiresolution_icons_and_versioned_launcher(self):
        build = (INSTALLER / "build_windows_package.ps1").read_text(encoding="utf-8")
        self.assertIn("petrolab-icon.svg", build)
        self.assertIn("petrolab-installer-icon.svg", build)
        self.assertIn("PetroLab.ico", build)
        self.assertIn("PetroLab-Installer.ico", build)
        self.assertGreaterEqual(build.count("icon:auto-resize=256,128,64,48,32,24,16"), 2)
        self.assertIn("PetroLabLauncher.cs", build)
        self.assertIn("/target:winexe", build)
        self.assertIn("/win32icon:$appIcon", build)
        self.assertIn("AssemblyFileVersion", build)
        self.assertIn("python-3.12.10-embed-amd64.zip", build)
        self.assertIn("Lib\\site-packages", build)
        self.assertIn("iscc", build)

    def test_installed_smoke_launches_the_actual_exe_twice(self):
        smoke = (INSTALLER / "smoke_windows_install.ps1").read_text(encoding="utf-8")
        self.assertIn('Join-Path $installRoot "PetroLab.exe"', smoke)
        self.assertIn("PETROLAB_LAUNCHER_NO_BROWSER", smoke)
        self.assertIn("petrolab-server.state", smoke)
        self.assertIn("launcher.log", smoke)
        self.assertIn("/_stcore/health", smoke)
        self.assertGreaterEqual(smoke.count("Start-Process -FilePath $launcherExe"), 2)
        self.assertIn("Second PetroLab.exe launch started a different server", smoke)
        self.assertIn("PETROLAB_UPDATE_TARGET_SHA", smoke)
        self.assertIn("previous\\app.py", smoke)
        self.assertIn("installer-preservation-marker-", smoke)

    def test_updater_is_transactional_and_does_not_touch_user_data(self):
        updater = (INSTALLER / "update_petrolab.ps1").read_text(encoding="utf-8")
        self.assertIn('$VerifiedRefUrl = "$RepoApi/git/ref/tags/windows-latest"', updater)
        self.assertIn("Resolve-VerifiedBuildSha", updater)
        self.assertIn('"$RepoZipBase/$remoteSha.zip"', updater)
        self.assertIn("Test-StagedApp", updater)
        self.assertIn("Move-Item -LiteralPath $Current -Destination $Previous", updater)
        self.assertIn("Move-Item -LiteralPath $Previous -Destination $Current", updater)
        self.assertNotIn("PetroLab Data", updater)
        self.assertNotIn("Remove-Item $env:PETROLAB_DATA_DIR", updater)

    def test_updater_only_defaults_to_verified_channel(self):
        updater = (INSTALLER / "update_petrolab.ps1").read_text(encoding="utf-8")
        self.assertIn("PETROLAB_UPDATE_TARGET_SHA", updater)
        self.assertIn("Invoke-RestMethod -Uri $VerifiedRefUrl", updater)
        self.assertNotIn('Invoke-RestMethod -Uri "$RepoApi/commits/main"', updater)

    def test_runtime_changes_are_staged_before_swap(self):
        updater = (INSTALLER / "update_petrolab.ps1").read_text(encoding="utf-8")
        self.assertIn("$requirementsChanged", updater)
        self.assertIn("Copy-Item -LiteralPath $Runtime -Destination $runtimeStage -Recurse -Force", updater)
        self.assertIn("& $pythonForTest -m pip check", updater)
        self.assertIn("Move-Item -LiteralPath $Runtime -Destination $RuntimePrevious", updater)

    def test_rollback_becomes_armed_immediately_after_backup_moves(self):
        updater = (INSTALLER / "update_petrolab.ps1").read_text(encoding="utf-8")
        runtime_move = updater.index("Move-Item -LiteralPath $Runtime -Destination $RuntimePrevious")
        runtime_arm = updater.index("$runtimeBackupCreated = $true", runtime_move)
        runtime_install = updater.index("Move-Item -LiteralPath $runtimeStage -Destination $Runtime", runtime_move)
        self.assertLess(runtime_move, runtime_arm)
        self.assertLess(runtime_arm, runtime_install)

        code_move = updater.index("Move-Item -LiteralPath $Current -Destination $Previous")
        code_arm = updater.index("$codeBackupCreated = $true", code_move)
        code_install = updater.index("Move-Item -LiteralPath $appStage -Destination $Current", code_move)
        self.assertLess(code_move, code_arm)
        self.assertLess(code_arm, code_install)

    def test_workflow_delegates_to_real_package_and_installed_smoke_scripts(self):
        workflow = (ROOT / ".github" / "workflows" / "windows-installer.yml").read_text(encoding="utf-8")
        self.assertIn("build_windows_package.ps1", workflow)
        self.assertIn("smoke_windows_install.ps1", workflow)
        self.assertIn("PetroLab-Setup-x64.exe", workflow)
        self.assertIn("PetroLab.exe", workflow)
        self.assertIn("PetroLab.ico", workflow)
        self.assertIn("PetroLab-Installer.ico", workflow)
        self.assertIn("Wait for full Windows verification", workflow)
        self.assertIn('git tag -f windows-latest $env:GITHUB_SHA', workflow)
        self.assertIn("actions/upload-artifact@v4", workflow)
        self.assertIn("gh release upload windows-latest", workflow)


if __name__ == "__main__":
    unittest.main(verbosity=2)
