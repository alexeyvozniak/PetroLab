from __future__ import annotations

import streamlit as st


_SCOPE_ACTION_CSS = """
<style>
/*
 * The exact-scope action lives inside the compact data rail. Streamlit may make
 * its grid column narrower than the Russian label itself; keep this one action
 * readable instead of wrapping it into a vertical stack of letters.
 */
.st-key-quick_plot_release_exact_scope,
[class~="st-key-quick_plot_release_exact_scope"] {
    min-width: 7.2rem !important;
    overflow: visible !important;
}
.st-key-quick_plot_release_exact_scope button,
[class~="st-key-quick_plot_release_exact_scope"] button {
    width: max-content !important;
    min-width: 7.2rem !important;
    white-space: nowrap !important;
}
.st-key-quick_plot_release_exact_scope button p,
[class~="st-key-quick_plot_release_exact_scope"] button p {
    white-space: nowrap !important;
}
</style>
"""

_SCROLL_TO_TOP_SCRIPT = """
<script>
(() => {
  const reset = () => {
    const main = document.querySelector('[data-testid="stMain"]');
    if (main) {
      main.scrollTop = 0;
      main.scrollLeft = 0;
    }
    window.scrollTo(0, 0);
  };
  requestAnimationFrame(() => {
    reset();
    setTimeout(reset, 60);
  });
})();
</script>
"""


def reset_route_scroll_if_pending() -> None:
    """Apply route-level UI guards and reset the viewport after navigation."""
    st.html(_SCOPE_ACTION_CSS)
    if not bool(st.session_state.pop("_scroll_to_top_pending", False)):
        return
    # Streamlit 1.60 supports trusted inline JavaScript through st.html. Keep the
    # script constant and local: no user-provided content is interpolated here.
    st.html(_SCROLL_TO_TOP_SCRIPT, unsafe_allow_javascript=True)
