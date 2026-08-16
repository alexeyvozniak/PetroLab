from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parent
WORKFLOW = ROOT / ".github" / "workflows" / "windows-installer.yml"


def main() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")
    wait_pos = text.index("Wait for full Windows verification and UI acceptance")
    publish_pos = text.index("Publish rolling Windows installer")
    assert wait_pos < publish_pos
    assert '"Windows verification", "v0.15.9 acceptance audit"' in text
    assert "All release verification gates passed" in text
    assert "gh run list --workflow $workflowName --commit $env:GITHUB_SHA" in text
    assert "git tag -f windows-latest $env:GITHUB_SHA" in text[publish_pos:]
    print("PetroLab 0.15.9 rolling release waits for science/UI acceptance: OK")


if __name__ == "__main__":
    main()
