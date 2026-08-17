from __future__ import annotations

import streamlit as st
import streamlit.components.v1 as components


def reset_route_scroll_if_pending() -> None:
    """Reset the visible Streamlit viewport once after navigating to another route."""
    if not bool(st.session_state.pop("_scroll_to_top_pending", False)):
        return
    components.html(
        """
        <script>
        (() => {
          const reset = () => {
            const parentWindow = window.parent;
            const doc = parentWindow.document;
            const main = doc.querySelector('[data-testid="stMain"]');
            if (main) {
              main.scrollTop = 0;
              main.scrollLeft = 0;
            }
            parentWindow.scrollTo(0, 0);
          };
          requestAnimationFrame(() => {
            reset();
            setTimeout(reset, 60);
          });
        })();
        </script>
        """,
        height=0,
        scrolling=False,
    )
