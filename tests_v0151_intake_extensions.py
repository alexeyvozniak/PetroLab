from __future__ import annotations

from petrolab.services.image_service import ImageAssignment, ImagePayload, ImageScope, SCOPE_DATASET
from petrolab.ui.universal_intake_extensions import _group_assignments_by_dataset


def test_image_assignments_can_span_phase_datasets_in_one_batch():
    a = ImageAssignment(ImagePayload("a.png", b"a"), ImageScope(SCOPE_DATASET), "BSE", "a")
    b = ImageAssignment(ImagePayload("b.png", b"b"), ImageScope(SCOPE_DATASET), "EDS", "b")
    c = ImageAssignment(ImagePayload("c.png", b"c"), ImageScope(SCOPE_DATASET), "BSE", "c")
    grouped = _group_assignments_by_dataset([(10, a), (11, b), (10, c)])
    assert list(grouped) == [10, 11]
    assert grouped[10] == [a, c]
    assert grouped[11] == [b]


if __name__ == "__main__":
    test_image_assignments_can_span_phase_datasets_in_one_batch()
    print("v0.15.1 intake extension tests: OK")
