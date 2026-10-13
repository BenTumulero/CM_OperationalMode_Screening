"""Reusable figure-gallery view for pre-generated figure exports.

Renders SVG/PNG/HTML figures written to disk by the Method Figures and
Cross-Campaign notebooks. Figures are discovered recursively under a root
directory and grouped by subfolder.
"""

from __future__ import annotations

from pathlib import Path

import streamlit as st

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


def _format_default_title(filename: str) -> str:
    """Format a filename into a human-readable title if not explicitly mapped."""
    stem = Path(filename).stem
    # Replace underscores and clean up common abbreviations
    words = stem.replace("_", " ").split()
    return " ".join(word.capitalize() for word in words)


def _render_categorized_grid(
    figures: list[tuple[str, str]],
    categories: dict[str, list[str]],
    figure_titles: dict[str, str],
    columns: int = 2,
    height: int = 700,
) -> None:
    """Render figures grouped into category tabs, with each figure in a bordered container in an n-column grid."""
    # Build lookup map: normalized filename/relative_path -> (rel, abs_path)
    figure_map: dict[str, tuple[str, str]] = {}
    for rel, abs_path in figures:
        p = Path(rel)
        figure_map[p.name.lower()] = (rel, abs_path)
        figure_map[rel.lower().replace("\\", "/")] = (rel, abs_path)

    matched_keys: set[str] = set()
    category_grouped_figs: dict[str, list[tuple[str, str, str]]] = {}

    for cat_name, file_patterns in categories.items():
        cat_figs: list[tuple[str, str, str]] = []
        for pattern in file_patterns:
            pat_lower = pattern.lower().replace("\\", "/")
            # 1. Exact match on filename
            matched = False
            for k, (rel, abs_path) in figure_map.items():
                if k == pat_lower or Path(k).name == Path(pat_lower).name:
                    display_title = figure_titles.get(pattern) or figure_titles.get(Path(abs_path).name) or _format_default_title(Path(abs_path).name)
                    item = (display_title, rel, abs_path)
                    if item not in cat_figs:
                        cat_figs.append(item)
                    matched_keys.add(abs_path)
                    matched = True

            # 2. Substring/prefix pattern match if not exact
            if not matched:
                for k, (rel, abs_path) in figure_map.items():
                    if pat_lower in k:
                        display_title = figure_titles.get(Path(abs_path).name) or _format_default_title(Path(abs_path).name)
                        item = (display_title, rel, abs_path)
                        if item not in cat_figs:
                            cat_figs.append(item)
                        matched_keys.add(abs_path)

        if cat_figs:
            category_grouped_figs[cat_name] = cat_figs

    # Collect any unmatched figures under an "Other Figures" tab
    unmatched: list[tuple[str, str, str]] = []
    for rel, abs_path in figures:
        if abs_path not in matched_keys:
            display_title = figure_titles.get(Path(abs_path).name) or _format_default_title(Path(abs_path).name)
            unmatched.append((display_title, rel, abs_path))

    if unmatched:
        category_grouped_figs["Other Figures"] = unmatched

    if not category_grouped_figs:
        st.info("No figures matched the specified categories.")
        return

    # Use a selectbox for category navigation instead of tabs to enable lazy loading.
    # st.tabs renders all content upfront (including background tabs), which causes
    # iframe-based Plotly figures to render incorrectly when loaded in the background.
    cat_names = list(category_grouped_figs.keys())
    selected_cat = st.selectbox(
        "Category",
        cat_names,
        index=0,
        key="gallery_category_select",
    )

    cat_figs = category_grouped_figs[selected_cat]
    num_figs = len(cat_figs)
    st.caption(f"{num_figs} figure(s) in {selected_cat}")

    if columns <= 1:
        # Vertical stack: one bordered container per figure
        for display_title, rel, abs_path in cat_figs:
            with st.container(border=True):
                st.markdown(f"**{display_title}**")
                _render_figure(Path(abs_path), height=height)
    else:
        # Multi-column grid
        col_count = columns
        for i in range(0, num_figs, col_count):
            row_items = cat_figs[i : i + col_count]
            cols = st.columns(col_count)
            for col_idx, (display_title, rel, abs_path) in enumerate(row_items):
                with cols[col_idx]:
                    with st.container(border=True):
                        st.markdown(f"**{display_title}**")
                        _render_figure(Path(abs_path), height=height)


def _render_figure(path: Path, height: int = 700) -> None:
    """Render a single figure file with the appropriate Streamlit element."""
    suffix = path.suffix.lower()
    if suffix in HTML_EXTENSIONS:
        # Render at natural size. CSS zoom/transform on Plotly SVG output
        # garbles axis labels and legends, so no scaling is applied.
        st.iframe(path, height=height)
    else:
        st.image(str(path), use_container_width=True)


def render_gallery(
    root_dir: Path,
    title: str,
    description: str = "",
    extensions: tuple[str, ...] = (".svg", ".png", ".html"),
    layout: str = "dropdown",
    height: int = 700,
    categories: dict[str, list[str]] | None = None,
    figure_titles: dict[str, str] | None = None,
    columns: int = 1,
) -> None:
    """Render a gallery page for figures under `root_dir`.

    layout="dropdown": group selectbox + figure selectbox.
    layout="tabs": one tab per figure (legacy single-figure tabs) or categorized tabs when `categories` is provided.
    layout="category_grid": one tab per category; within each tab, figures are rendered in bordered containers arranged in a grid.
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

    # If categories are provided or layout is category_grid, organize figures by category tabs
    if categories is not None or layout == "category_grid":
        _render_categorized_grid(
            figures=figures,
            categories=categories or {},
            figure_titles=figure_titles or {},
            columns=columns,
            height=height,
        )
        return

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
