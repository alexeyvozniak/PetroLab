from __future__ import annotations

import inspect

from petrolab.ui.pages.object_workspace import _secondary_selection_actions


def main() -> None:
    source = inspect.getsource(_secondary_selection_actions)
    assert 'key="workspace_selection_plot"' in source
    assert 'seed_plot_handoff(' in source
    assert 'dataset_ids=dataset_ids' in source
    assert 'analysis_ids=ids' in source
    assert 'navigate("plots")' in source
    assert source.index('seed_plot_handoff(') < source.index('navigate("plots")')
    print("PetroLab v0.16 workspace exact plot handoff: OK")


if __name__ == "__main__":
    main()
