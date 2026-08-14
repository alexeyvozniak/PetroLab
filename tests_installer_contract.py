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

    def test_launcher_uses_embedded_runtime_and_explicit_data_directory(self):
        launcher = (INSTALLER / "launch_petrolab.vbs").read_text(encoding="utf-8")
        self.assertIn(r'"runtime\pythonw.exe"', launcher)
        self.assertIn('shell.SpecialFolders("MyDocuments")', launcher)
        self.assertIn('shell.Environment("PROCESS")("PETROLAB_DATA_DIR") = dataDir', launcher)
        self.assertIn("shell.Run command, 0, False", launcher)

    def test_updater_is_transactional_and_does_not_touch_user_data(self):
        updater = (INSTALLER / "update_petrolab.ps1").read_text(encoding="utf-8")
        self.assertIn('Invoke-RestMethod -Uri "$RepoApi/commits/main"', updater)
        self.assertIn('"$RepoZipBase/$remoteSha.zip"', updater)
        self.assertIn('Test-StagedApp', updater)
        self.assertIn('Move-Item -LiteralPath $Current -Destination $Previous', updater)
        self.assertIn('Move-Item -LiteralPath $Previous -Destination $Current', updater)
        self.assertNotIn("PetroLab Data", updater)
        self.assertNotIn("Remove-Item $env:PETROLAB_DATA_DIR", updater)

    def test_runtime_changes_are_staged_before_swap(self):
        updater = (INSTALLER / "update_petrolab.ps1").read_text(encoding="utf-8")
        self.assertIn('$requirementsChanged', updater)
        self.assertIn('Copy-Item -LiteralPath $Runtime -Destination $runtimeStage -Recurse -Force', updater)
        self.assertIn('& $pythonForTest -m pip check', updater)
        self.assertIn('Move-Item -LiteralPath $Runtime -Destination $RuntimePrevious', updater)

    def test_installer_ci_builds_self_contained_runtime(self):
        workflow = (ROOT / ".github" / "workflows" / "windows-installer.yml").read_text(encoding="utf-8")
        self.assertIn("python-3.12.10-embed-amd64.zip", workflow)
        self.assertIn("Lib\\site-packages", workflow)
        self.assertIn("PetroLab-Setup-x64.exe", workflow)
        self.assertIn("actions/upload-artifact@v4", workflow)
        self.assertIn("windows-latest", workflow)


if __name__ == "__main__":
    unittest.main(verbosity=2)
