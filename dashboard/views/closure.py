"""Closure page: CHON elemental closure diagnostics (pickle-only)."""

from __future__ import annotations

import streamlit as st

from sources.base import DashboardModel


def render(model: DashboardModel) -> None:
    st.subheader("CHON Elemental Closure")

    data = model.simulation_data

    if data is None:
        st.info("CHON closure requires a simulation pickle.", icon="ℹ️")
        return

    if not model.capabilities.has_closure:
        st.info(
            "CHON closure requires the parameter set and detailed kinetic "
            "trajectories. Re-run the simulation with performance_mode=False "
            "and export with include_pickle=True.",
            icon="ℹ️",
        )
        return

    tab1, tab2, tab3 = st.tabs(["Stoichiometric", "Boundary", "Delta"])

    with tab1:
        try:
            result = data.compute_stoichiometric_closure()
            st.dataframe(
                data.build_closure_summary_df(result),
                width='stretch', hide_index=True,
            )
        except Exception as exc:  # noqa: BLE001
            st.warning(f"Stoichiometric closure unavailable: {exc}")

    with tab2:
        try:
            result = data.compute_boundary_closure()
            st.dataframe(
                data.build_closure_summary_df(result),
                width='stretch', hide_index=True,
            )
        except Exception as exc:  # noqa: BLE001
            st.warning(f"Boundary closure unavailable: {exc}")

    with tab3:
        try:
            result = data.compute_closure_delta()
            st.dataframe(data.get_closure_delta_df(result), width='stretch', hide_index=True)
        except Exception as exc:  # noqa: BLE001
            st.warning(f"Closure delta unavailable: {exc}")
