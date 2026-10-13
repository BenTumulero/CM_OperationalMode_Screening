"""Shared Streamlit UI helpers for dashboard pages."""

from __future__ import annotations

from typing import Any, Callable, Optional

import streamlit as st

from sources.base import CapabilityFlags, DashboardModel

def show_placeholder(message: str) -> None:
    """Render an informative placeholder for unavailable data."""
    st.info(message, icon="ℹ️")


def guarded(
    capabilities: CapabilityFlags,
    capability: str,
    unavailable_message: str,
) -> Callable:
    """Decorator: render a placeholder instead of the page body when a
    capability is missing. Usage:

        @guarded(model.capabilities, "has_kinetic_traces", "...")
        def render(model): ...
    """

    def decorator(render_fn: Callable[[DashboardModel], None]) -> Callable:
        def wrapper(model: DashboardModel) -> None:
            if not getattr(capabilities, capability, False):
                show_placeholder(unavailable_message)
                return
            render_fn(model)

        return wrapper

    return decorator


def render_figure(fig: Optional[Any], key_hint: str = "") -> None:
    """Render a Plotly figure if present, else a placeholder."""
    if fig is None:
        show_placeholder(f"No figure available{f' ({key_hint})' if key_hint else ''}.")
        return
    st.plotly_chart(fig, width='stretch')


def batch_selector(model: DashboardModel, key_prefix: str = "batch") -> int:
    """One-based batch selector widget shared by all batch pages."""
    options = [b.batch_number for b in model.batches]
    if not options:
        show_placeholder("This result contains no batches.")
        return 1
    default_index = 0
    return st.selectbox(
        "Batch",
        options,
        index=default_index,
        key=f"{key_prefix}_selector",
        format_func=lambda n: f"Batch {n}",
    )
