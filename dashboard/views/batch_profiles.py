"""Single-batch sub-tabs: biomass/metabolites and volume/feed per batch."""

from __future__ import annotations

import streamlit as st

from views._ui import render_figure
from sources.base import DashboardModel


def render_biomass_metabolites(model: DashboardModel, batch_number: int) -> None:
    """Biomass & metabolites trajectories for one batch."""
    st.subheader("Biomass & Metabolites")

    if not model.capabilities.has_batch_state_trajectories:
        st.info(
            "State trajectories are not available from this source.",
            icon="ℹ️",
        )
        return

    data = model.simulation_data
    if data is None:
        st.info("This sub-tab requires a simulation pickle.", icon="ℹ️")
        return

    render_figure(data.plot_biomass_metabolites(batch_number=batch_number))


def render_volume_feed(model: DashboardModel, batch_number: int) -> None:
    """Volume & feed trajectories for one batch."""
    st.subheader("Volume & Feed")

    if not model.capabilities.has_batch_state_trajectories:
        st.info(
            "State trajectories are not available from this source.",
            icon="ℹ️",
        )
        return

    data = model.simulation_data
    if data is None:
        st.info("This sub-tab requires a simulation pickle.", icon="ℹ️")
        return

    render_figure(data.plot_volume_feed(batch_number=batch_number))
