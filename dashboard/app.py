"""AnimaKinetica Data Dashboard — Streamlit entry point (navigation router).

Run from the repository root:

    streamlit run dashboard/app.py

The dashboard is a standalone consumer of the `animakinetica` package
(public API only). Pages are wired explicitly via `st.navigation`:

    home.py                            — landing page
    pages/1_Simulation_Explorer.py     — browse & inspect single simulation files
    pages/2_Method_Figures.py          — gallery of Method Figures exports
    pages/3_Cross_Campaign_Figures.py  — gallery of Cross-Campaign exports
"""

from __future__ import annotations

import sys
from pathlib import Path

import streamlit as st

# Make `sources` / `views` importable from pages as well.
DASHBOARD_DIR = Path(__file__).resolve().parent
REPO_ROOT = DASHBOARD_DIR.parent
if str(DASHBOARD_DIR) not in sys.path:
    sys.path.insert(0, str(DASHBOARD_DIR))

st.set_page_config(page_title="AnimaKinetica Dashboard", layout="wide")

page = st.navigation(
    [
        st.Page("home.py", title="Home", icon=":material/home:"),
        st.Page(
            "pages/1_Simulation_Explorer.py",
            title="Simulation Explorer",
            icon=":material/science:",
        ),
        st.Page(
            "pages/2_Method_Figures.py",
            title="Method Figures",
            icon=":material/insert_chart:",
        ),
        st.Page(
            "pages/3_Cross_Campaign_Figures.py",
            title="Cross-Campaign Figures",
            icon=":material/compare:",
        ),
    ]
)

page.run()
