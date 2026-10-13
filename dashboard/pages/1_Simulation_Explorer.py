"""Simulation Explorer — browse and inspect individual simulation files.

This page contains the original single-file explorer: sidebar data-source
selection (cascading cell-line → operating mode → strategy selectors over
the repository root), file discovery, and the capability-gated tabs
(Overview, Single Batch, Full Cultivation, Parameters, Optimization).
"""

from __future__ import annotations

import sys
from pathlib import Path

import streamlit as st

DASHBOARD_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = DASHBOARD_DIR.parent
if str(DASHBOARD_DIR) not in sys.path:
    sys.path.insert(0, str(DASHBOARD_DIR))

from sources import DashboardModel, PickleSource  # noqa: E402
from sources.labels import (  # noqa: E402
    CAMPAIGN_LABELS,
    MODE_LABELS,
    campaign_key,
    mode_key,
    run_strategy,
)

SEARCH_DIR = REPO_ROOT


@st.cache_resource(show_spinner=False)
def load_model(path_str: str) -> DashboardModel:
    """Load a result file through the pickle backend (cached per path)."""
    return PickleSource().load(Path(path_str))


def discover_files(search_dir: Path) -> list[Path]:
    return PickleSource().discover(search_dir)


def main() -> None:
    with st.sidebar:
        st.title("AnimaKinetica Data Dashboard")
        st.header("Data source")

        files = discover_files(SEARCH_DIR)
        if not files:
            st.warning(
                f"No .pkl files found under {SEARCH_DIR}. Run a simulation "
                "and export with `sim.data.save(...)` first."
            )
            st.stop()

        # --- 1. Cell line (campaign) selector ---
        campaign_keys = sorted(
            {key for f in files if (key := campaign_key(f))},
            key=lambda k: CAMPAIGN_LABELS.get(k, k),
        )
        if not campaign_keys:
            st.warning("No campaign-organized .pkl files found.")
            st.stop()

        selected_campaign = st.selectbox(
            "Cell line",
            campaign_keys,
            format_func=lambda k: CAMPAIGN_LABELS.get(k, k),
        )

        # --- 2. Operating mode selector (filtered by cell line) ---
        campaign_files = [f for f in files if campaign_key(f) == selected_campaign]
        mode_keys = sorted(
            {key for f in campaign_files if (key := mode_key(f))},
            key=lambda k: MODE_LABELS.get(k, k),
        )
        if not mode_keys:
            st.warning("No operating modes found for this cell line.")
            st.stop()

        selected_mode = st.selectbox(
            "Operating mode",
            mode_keys,
            format_func=lambda k: MODE_LABELS.get(k, k),
        )

        # --- 3. Feed/perfusion strategy selector (when available) ---
        mode_files = [f for f in campaign_files if mode_key(f) == selected_mode]
        strategies = sorted({s for f in mode_files if (s := run_strategy(f))})
        if strategies:
            selected_strategy = st.selectbox("Feed/perfusion strategy", strategies)
            strategy_files = [
                f for f in mode_files if run_strategy(f) == selected_strategy
            ]
        else:
            strategy_files = mode_files

        # --- 4. Run selector (only when multiple runs remain) ---
        if len(strategy_files) > 1:
            selected_file = st.selectbox(
                "Run",
                strategy_files,
                format_func=lambda p: p.parent.name,
            )
        else:
            selected_file = strategy_files[0]

    try:
        model = load_model(str(selected_file))
    except Exception as exc:  # noqa: BLE001 - surface load errors clearly
        st.error(f"Failed to load result file: {exc}")
        st.stop()

    # Loaded-file info and metadata, pinned to the bottom of the sidebar.
    with st.sidebar:
        st.markdown("---")
        st.caption(
            f"Loaded **{model.name}** ({model.n_batches} batches) from "
            f"`{model.source_path}`"
        )

        # Object type caption
        obj_type = model.metadata.get("pickle_object_type")
        st.caption(
            f"Pickle object type: **{obj_type or 'unknown'}**. "
        )

        # Metadata line: date, operating mode/strategy, and optimization
        # status (only knowable for full simulation pickles).
        meta = model.metadata
        timestamp = meta.get("timestamp")
        date_str = timestamp[:16].replace("T", " ") if timestamp else "unknown date"
        parts = [f"📅 {date_str}", f"Mode: {meta.get('simulation_type') or 'Unknown'}"]
        if meta.get("feed_strategy", "NA") != "NA":
            parts.append(f"Feed: {meta['feed_strategy']}")
        if meta.get("perfusion_strategy", "NA") != "NA":
            parts.append(f"Perfusion: {meta['perfusion_strategy']}")
        st.caption("  ·  ".join(parts))

        # Capability summary: which gated tabs have data for this result.
        caps = model.capabilities
        cap_parts = []
        cap_parts.append("✅ Parameters" if caps.has_parameters
                         else "🚫 Parameters")
        cap_parts.append("✅ Optimization" if caps.has_optimization
                         else "🚫 Optimization")
        st.caption(" · ".join(cap_parts))


    import views.overview as pg_overview
    import views.batch_profiles as pg_profiles
    import views.gas_ph as pg_gas_ph
    import views.kinetics as pg_kinetics
    import views.stoichiometry as pg_stoichiometry
    import views.process as pg_process
    import views.closure as pg_closure
    import views.parameters as pg_parameters
    import views.optimization as pg_optimization
    from views._ui import batch_selector

    # ------------------------------------------------------------------
    # Top-level tabs: Overview | Single Batch | Full Cultivation |
    #                 Parameters | Optimization
    # ------------------------------------------------------------------
    tabs = st.tabs(
        ["Overview", "Single Batch", "Full Cultivation", "Parameters",
         "Optimization"]
    )
    tab_overview, tab_single_batch, tab_cumulative_batch, tab_params, tab_opt = tabs

    with tab_overview:
        pg_overview.render(model)

    # ------------------------------------------------------------------
    # Single Batch: shared batch selector + per-topic sub-tabs
    # ------------------------------------------------------------------
    with tab_single_batch:
        st.subheader("Single Batch")
        batch_number = batch_selector(model, key_prefix="single_batch")

        subtabs = st.tabs(
            ["Biomass & Metabolites", "Volume and Feed", "Gas", "pH",
             "Kinetics", "Stoichiometry"]
        )
        (sub_biomass, sub_volume, sub_gas, sub_ph, sub_kinetics,
         sub_stoich) = subtabs

        with sub_biomass:
            pg_profiles.render_biomass_metabolites(model, batch_number)
        with sub_volume:
            pg_profiles.render_volume_feed(model, batch_number)
        with sub_gas:
            pg_gas_ph.render_gas(model, batch_number)
        with sub_ph:
            pg_gas_ph.render_ph(model, batch_number)
        with sub_kinetics:
            pg_kinetics.render(model, batch_number)
        with sub_stoich:
            pg_stoichiometry.render(model, batch_number)

    # ------------------------------------------------------------------
    # Full Cultivation: process-level sub-tabs
    # ------------------------------------------------------------------
    with tab_cumulative_batch:
        st.subheader("Full Cultivation")
        max_batches = pg_process.max_batches_selector(model)

        subtabs = st.tabs(
            ["Cultivation Summary", "Concatenated Profiles", "Harvest",
             "Medium use", "Base use", "Gas use", "CHON Closure"]
        )
        (sub_cult, sub_profiles, sub_harvest, sub_medium, sub_base,
         sub_gasuse, sub_closure) = subtabs

        with sub_cult:
            pg_process.render_cultivation_summary(model)
        with sub_profiles:
            pg_process.render_concatenated_profiles(model, max_batches)
        with sub_harvest:
            pg_process.render_harvest(model, max_batches)
        with sub_medium:
            pg_process.render_medium_use(model, max_batches)
        with sub_base:
            pg_process.render_base_use(model, max_batches)
        with sub_gasuse:
            pg_process.render_gas_use(model, max_batches)
        with sub_closure:
            pg_closure.render(model)

    # ------------------------------------------------------------------
    # Parameters & Optimization: capability-gated views that degrade to
    # an explanatory message when the loaded result cannot provide them.
    # ------------------------------------------------------------------
    with tab_params:
        pg_parameters.render(model)

    with tab_opt:
        pg_optimization.render(model)


if __name__ == "__main__":
    main()
