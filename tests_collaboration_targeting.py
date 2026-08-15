from __future__ import annotations

import json
import tempfile
import unittest
import zipfile
from pathlib import Path

from petrolab.collaboration_targeting import (
    normalize_project_key,
    preferred_project_id,
    read_archive_context_hint,
    suggested_project_ids,
)


class CollaborationTargetingTests(unittest.TestCase):
    def test_unique_existing_kandalaksha_is_suggested_but_only_as_destination(self):
        projects = [
            {"id": 1, "name": "Ковдор"},
            {"id": 2, "name": "Кандалакша"},
        ]
        self.assertEqual(suggested_project_ids(projects, "Кандалакша"), (2,))
        self.assertEqual(preferred_project_id(projects, "Кандалакша", active_project_id=1), 2)

    def test_separator_variants_are_only_a_conservative_suggestion(self):
        projects = [
            {"id": 3, "name": "Kandalaksha dykes"},
            {"id": 4, "name": "Other"},
        ]
        self.assertEqual(normalize_project_key("Kandalaksha-dykes"), normalize_project_key("Kandalaksha dykes"))
        self.assertEqual(suggested_project_ids(projects, "Kandalaksha-dykes"), (3,))

    def test_ambiguous_matches_do_not_override_active_project(self):
        projects = [
            {"id": 5, "name": "Kandalaksha-dykes"},
            {"id": 6, "name": "Kandalaksha dykes"},
            {"id": 7, "name": "Current work"},
        ]
        self.assertEqual(suggested_project_ids(projects, "Kandalaksha_dykes"), (5, 6))
        self.assertEqual(preferred_project_id(projects, "Kandalaksha_dykes", active_project_id=7), 7)

    def test_manifest_context_is_read_without_importing_the_database(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "sample_fragment.petrolab"
            manifest = {
                "format": "petrolab-portable-archive",
                "format_version": 3,
                "payload_kind": "fragment",
                "project": {"id": 10, "name": "Кандалакша"},
            }
            with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as archive:
                archive.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False))
            self.assertEqual(read_archive_context_hint(path), ("Кандалакша", "fragment"))


if __name__ == "__main__":
    unittest.main()
