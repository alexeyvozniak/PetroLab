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

    def test_launcher_uses_embedded_runtime_and_explicit_data_directory(self):
        launcher = (INSTALLER / "launch_petrolab.vbs").read_text(encoding="utf-8")
        self.assertIn(r'"runtime\pythonw.exe"', launcher)
        self.assertIn('shell.SpecialFolders("MyDocuments")', launcher)
        self.assertIn('shell.Environment("PROCESS")("PETROLAB_DATA_DIR") = dataDir', launcher)
        self.assertIn("shell.Run command, 0, False", launcher)

    def test_updater_is_transactional_and_does_not_touch_user_data(self):
        updater = (INSTALLER / "update_petrolab.ps1").read_text(encoding="utf-8")
        self.assertIn('$VerifiedRefUrl = "$RepoApi/git/ref/tags/windows-latest"', updater)
        self.assertIn('Resolve-VerifiedBuildSha', updater)
        self.assertIn('"$RepoZipBase/$remoteSha.zip"', updater)
        self.assertIn('Test-StagedApp', updater)
        self.assertIn('Move-Item -LiteralPath $Current -Destination $Previous', updater)
        self.assertIn('Move-Item -LiteralPath $Previous -Destination $Current', updater)
        self.assertNotIn("PetroLab Data", updater)
        self.assertNotIn("Remove-Item $env:PETROLAB_DATA_DIR", updater)

    def test_updater_only_defaults_to_verified_channel(self):
        updater = (INSTALLER / "update_petrolab.ps1").read_text(encoding="utf-8")
        self.assertIn("PETROLAB_UPDATE_TARGET_SHA", updater)
        self.assertIn("Invoke-RestMethod -Uri $VerifiedRefUrl", updater)
        self.assertNotIn('Invoke-RestMethod -Uri "$RepoApi/commits/main"', updater)

    def test_updater_is_compatible_with_windows_powershell_process_matching(self):
        updater = (INSTALLER / "update_petrolab.ps1").read_text(encoding="utf-8")
        self.assertIn(".IndexOf($appPath, [System.StringComparison]::OrdinalIgnoreCase) -ge 0", updater)
        self.assertNotIn(".Contains((Join-Path $Current", updater)
        self.assertIn('if (-not $NoLaunch)', updater)

    def test_runtime_changes_are_staged_before_swap(self):
        updater = (INSTALLER / "update_petrolab.ps1").read_text(encoding="utf-8")
        self.assertIn('$requirementsChanged', updater)
        self.assertIn('Copy-Item -LiteralPath $Runtime -Destination $runtimeStage -Recurse -Force', updater)
        self.assertIn('& $pythonForTest -m pip check', updater)
        self.assertIn('Move-Item -LiteralPath $Runtime -Destination $RuntimePrevious', updater)

    def test_rollback_becomes_armed_immediately_after_backup_moves(self):
        updater = (INSTALLER / "update_petrolab.ps1").read_text(encoding="utf-8")
        runtime_move = updater.index('Move-Item -LiteralPath $Runtime -Destination $RuntimePrevious')
        runtime_arm = updater.index('$runtimeBackupCreated = $true', runtime_move)
        runtime_install = updater.index('Move-Item -LiteralPath $runtimeStage -Destination $Runtime', runtime_move)
        self.assertLess(runtime_move, runtime_arm)
        self.assertLess(runtime_arm, runtime_install)

        code_move = updater.index('Move-Item -LiteralPath $Current -Destination $Previous')
        code_arm = updater.index('$codeBackupCreated = $true', code_move)
        code_install = updater.index('Move-Item -LiteralPath $appStage -Destination $Current', code_move)
        self.assertLess(code_move, code_arm)
        self.assertLess(code_arm, code_install)
        self.assertIn('if ($codeBackupCreated -and (Test-Path -LiteralPath $Previous))', updater)
        self.assertIn('if ($runtimeBackupCreated -and (Test-Path -LiteralPath $RuntimePrevious))', updater)

    def test_installer_ci_builds_and_smokes_self_contained_installation(self):
        workflow = (ROOT / ".github" / "workflows" / "windows-installer.yml").read_text(encoding="utf-8")
        self.assertIn("python-3.12.10-embed-amd64.zip", workflow)
        self.assertIn("Lib\\site-packages", workflow)
        self.assertIn("PetroLab-Setup-x64.exe", workflow)
        self.assertIn("/VERYSILENT /SUPPRESSMSGBOXES /NORESTART", workflow)
        self.assertIn("/_stcore/health", workflow)
        self.assertIn("powershell.exe -NoProfile -ExecutionPolicy Bypass", workflow)
        self.assertIn("installer-preservation-marker-", workflow)
        self.assertIn("PETROLAB_UPDATE_TARGET_SHA", workflow)
        self.assertIn('Value ("0" * 40)', workflow)
        self.assertIn("previous\\app.py", workflow)
        self.assertIn("Wait for full Windows verification", workflow)
        self.assertIn('git tag -f windows-latest $env:GITHUB_SHA', workflow)
        self.assertIn("actions/upload-artifact@v4", workflow)


if __name__ == "__main__":
    unittest.main(verbosity=2)