"""Overview page: metadata, DCM/WCM KPI callouts, and summary statistics."""

from __future__ import annotations

import streamlit as st

from sources.base import DashboardModel

# Metric metadata (label / unit / description) is sourced from the package
# registry so it stays in sync with `animakinetica`. Fall back to an empty
# registry if the private symbol is unavailable; unknown keys then degrade
# gracefully to the raw key name.
try:  # noqa: SIM105
    from animakinetica.core.simulation_data import (
        _EXPLICIT_METRIC_SPECS as _METRIC_SPECS,
    )
except Exception:  # noqa: BLE001
    _METRIC_SPECS = {}

# Ordered DCM-basis metrics for the left column.
DCM_KEYS = [
    "STY_kg_m3_day",
    "total_DCM_harvested_kg",
    # "total_DCM_harvested_cmmol",
    "feed_conversion_efficiency_kg_kg",
    "medium_conversion_efficiency_m3_kg",
    # "protein_conversion_efficiency_kg_kg",
    "total_DCM_kg",
    # "total_DCM_lost_kg",
    # "total_DCM_lost_cmmol",
    # "total_DCM_in_kg",
    # "total_DCM_out_kg",
    # "total_DCM_produced_kg",
    # "simulated_total_DCM_kg",
]

# Ordered WCM-basis metrics for the right column.
WCM_KEYS = [
    "STY_WCM_kg_m3_day",
    "total_WCM_harvested_kg",
    "feed_conversion_efficiency_kg_kg_WCM",
    "medium_conversion_efficiency_m3_kg_WCM",
]

# Legacy/alias DCM keys that may appear in older exports.
_DCM_ALIASES = {"total_biomass_kg", "total_DCM_cmol"}


def _format_value(value) -> str:
    if value is None:
        return "—"
    try:
        return f"{float(value):.4g}"
    except (TypeError, ValueError):
        return str(value)


def _metric_info(key: str) -> tuple[str, str, str]:
    """Return (label, unit, description) for a summary-stat key."""
    spec = _METRIC_SPECS.get(key, {})
    label = spec.get("label", key)
    unit = spec.get("unit", "")
    description = spec.get("description", key)
    return label, unit, description


def _render_callout(stats: dict, key: str) -> None:
    """Render one summary statistic as a callout number.

    The unit is shown in the title; the description is shown in the
    information popup.
    """
    label, unit, description = _metric_info(key)
    title = f"{label} [{unit}]" if unit else label
    st.metric(title, _format_value(stats.get(key)), help=description)


def _render_callout_column(stats: dict, keys: list[str]) -> None:
    """Render all available metrics from `keys` as stacked callouts."""
    available = [k for k in keys if stats.get(k) is not None]
    if not available:
        st.info("No metrics on this basis are available for this result.",
                icon="ℹ️")
        return
    for key in available:
        _render_callout(stats, key)


def _render_shared_stats(stats: dict, shown_keys: set[str]) -> None:
    """Render remaining summary statistics as callouts in a grid."""
    remaining = {
        k: v for k, v in stats.items()
        if k not in shown_keys and v is not None
    }
    scalars: dict[str, object] = {}
    nonscalars: dict[str, object] = {}
    for k, v in remaining.items():
        if isinstance(v, (dict, list, tuple)):
            nonscalars[k] = v
        else:
            scalars[k] = v

    if scalars:
        n_cols = 3
        keys = list(scalars)
        for start in range(0, len(keys), n_cols):
            cols = st.columns(n_cols)
            for col, key in zip(cols, keys[start:start + n_cols]):
                with col:
                    _render_callout(scalars, key)

    if nonscalars:
        with st.expander("Phase runtimes & other structured statistics"):
            st.json(nonscalars)


def render(model: DashboardModel) -> None:
    st.subheader("Simulation Overview")

    meta = model.metadata
    st.caption(
        f"**Type:** {meta.get('simulation_type', '—')}  |  "
        f"**Batches:** {model.n_batches}  |  "
        f"**Feed:** {meta.get('feed_strategy', 'NA')}  |  "
        f"**Perfusion:** {meta.get('perfusion_strategy', 'NA')}  |  "
        f"**Timestamp:** {meta.get('timestamp', '—')}"
    )

    if not model.capabilities.has_summary_stats:
        st.info("Summary statistics are not available for this result.", icon="ℹ️")
        return

    stats = dict(model.summary_stats)

    # ------------------------------------------------------------------
    # Two-column KPI comparison: DCM basis (left) vs WCM basis (right).
    # ------------------------------------------------------------------
    col_dcm, col_wcm = st.columns(2)
    with col_dcm:
        st.markdown("#### Dry Cell Mass (DCM) basis")
        _render_callout_column(stats, DCM_KEYS)
    with col_wcm:
        st.markdown("#### Wet Cell Mass (WCM) basis")
        _render_callout_column(stats, WCM_KEYS)

    # ------------------------------------------------------------------
    # Remaining summary statistics as callouts in a responsive grid.
    # ------------------------------------------------------------------
    shown = set(DCM_KEYS) | set(WCM_KEYS) | _DCM_ALIASES | {"number_of_batches"}
    st.markdown("#### Other summary statistics")
    _render_shared_stats(stats, shown)

