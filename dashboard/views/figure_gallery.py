"""Reusable figure-gallery view for pre-generated figure exports.

Renders SVG/PNG/HTML figures written to disk by the Method Figures and
Cross-Campaign notebooks. Figures are discovered recursively under a root
directory and grouped by subfolder.
"""

from __future__ import annotations

from pathlib import Path

import streamlit as st
import streamlit.components.v1 as components

IMAGE_EXTENSIONS = {".svg", ".png", ".jpg", ".jpeg", ".webp", ".gif"}
HTML_EXTENSIONS = {".html"}


@st.cache_data(show_spinner=False)
def discover_figures(root_dir: str, extensions: tuple[str, ...]) -> list[tuple[str, str]]:
    """Recursively find figure files under `root_dir`.

    Returns a list of (relative_path, absolute_path) tuples sorted by path.
    Cached on the directory string; bump the key by touching files.
    """
    root = Path(root_dir)
    if not root.exists():
        return []
    files = [
        p for p in root.rglob("*")
        if p.is_file() and p.suffix.lower() in extensions
    ]
    files.sort(key=lambda p: str(p.relative_to(root)).lower())
    return [(str(p.relative_to(root)), str(p)) for p in files]


def _render_figure(path: Path, height: int = 700) -> None:
    """Render a single figure file with the appropriate Streamlit element."""
    suffix = path.suffix.lower()
    if suffix in HTML_EXTENSIONS:
        # Render at natural size. CSS zoom/transform on Plotly SVG output
        # garbles axis labels and legends, so no scaling is applied.
        html = path.read_text(encoding="utf-8")
        components.html(html, height=height, scrolling=True)
    else:
        st.image(str(path), use_container_width=True)


def render_gallery(
    root_dir: Path,
    title: str,
    description: str = "",
    extensions: tuple[str, ...] = (".svg", ".png", ".html"),
    layout: str = "dropdown",
    height: int = 700,
) -> None:
    """Render a gallery page for figures under `root_dir`.

    layout="dropdown": group selectbox + figure selectbox.
    layout="tabs": one tab per figure (no dropdowns, no "show all").
    """
    st.title(title)
    if description:
        st.markdown(description)

    figures = discover_figures(str(root_dir), extensions)
    if not figures:
        st.warning(
            f"No figures found under `{root_dir}`. Generate them by running "
            "the corresponding notebooks, which export figures to this "
            "directory."
        )
        return

    st.caption(f"{len(figures)} figure(s) found under `{root_dir}`")

    if layout == "tabs":
        tabs = st.tabs([rel for rel, _ in figures])
        for tab, (_, abs_path) in zip(tabs, figures):
            with tab:
                _render_figure(Path(abs_path), height=height)
        return

    # Group by first path segment (subfolder) when present.
    groups: dict[str, list[tuple[str, str]]] = {}
    for rel, abs_path in figures:
        parts = Path(rel).parts
        group = parts[0] if len(parts) > 1 else ""
        groups.setdefault(group, []).append((rel, abs_path))

    if len(groups) > 1:
        group_labels = {g: (g if g else "root") for g in groups}
        selected_group = st.selectbox(
            "Group", list(groups.keys(), ), format_func=lambda g: group_labels[g]
        )
        group_figures = groups[selected_group]
    else:
        group_figures = figures

    labels = [rel for rel, _ in group_figures]
    selected = st.selectbox("Figure", labels)
    selected_path = dict(group_figures)[selected]
    _render_figure(Path(selected_path), height=height)

    with st.expander(f"Show all {len(group_figures)} figure(s) in this group"):
        for rel, abs_path in group_figures:
            st.markdown(f"**{rel}**")
            _render_figure(Path(abs_path), height=height)
            st.markdown("---")
