"""Human-readable labels for simulation pickle files.

Maps the raw campaign folders and operating-mode directories onto the
publication-facing cell-line names and readable mode names, so the
dashboard can present pickle files as e.g.::

    1. Fixed - Humbird (2020) Wildtype  ·  Fed-Batch  ·  fedbatch_exponential_p2_20260825_0059

Campaign 3 (dynamic stoichiometry, GFI) is a *bonus* cell line: it is not
discussed in the publication belonging to this codebase, but it is
included in this dashboard for completeness.
"""

from __future__ import annotations

import re
from pathlib import Path

__all__ = [
    "CAMPAIGN_LABELS",
    "MODE_LABELS",
    "STRATEGY_LABELS",
    "campaign_key",
    "mode_key",
    "run_strategy",
    "campaign_label",
    "mode_label",
    "describe_pickle",
]

# Campaign folder prefix -> publication cell-line label.
# NOTE: Campaign_3 is a bonus cell line included in this dashboard only;
# it is not part of the publication.
CAMPAIGN_LABELS: dict[str, str] = {
    "Campaign_1": "1. Fixed - Humbird (2020) Wildtype",
    "Campaign_2": "3. Fixed - Frohlich et al. (2025)",
    "Campaign_3": "Bonus. Growth-rate dependent - Frohlich et al. (2025)",
    "Campaign_4": "4. Substrate Dependent - Frohlich et al. (2025)",
    "Campaign_5": "5. Substrate Dependent Enhanced - Frohlich et al. (2025)",
    "Campaign_6": "2. Fixed - Humbird (2020) Enhanced",
}

# Numbered operating-mode directory prefix -> readable mode name.
MODE_LABELS: dict[str, str] = {
    "01_FedBatch": "Fed-Batch",
    "02_Batch": "Batch",
    "03_Chemostat": "Chemostat",
    "04_ConcentratedFedBatch": "Concentrated Fed-Batch",
    "05_ContinuousPerfusion": "Continuous Perfusion",
}

# Run-folder strategy abbreviations -> readable strategy names.
# Fed-batch uses feed strategies; concentrated fed-batch and continuous
# perfusion use perfusion strategies. Batch and chemostat runs carry no
# strategy token.
STRATEGY_LABELS: dict[str, str] = {
    "constant": "Constant",
    "exponential": "Exponential",
    "linear": "Linear",
    "csfr": "Cell-Specific Feed Rate (CSFR)",
    "cspr": "Cell-Specific Perfusion Rate (CSPR)",
    "gsp": "Glucose Setpoint",
    "tbs": "Toxicity-Based Step",
    "tbp": "Toxicity-Based Proportional",
}

_CAMPAIGN_RE = re.compile(r"^(Campaign_\d+)")
_MODE_RE = re.compile(r"^(\d{2}_[A-Za-z]+)")


def campaign_key(path: Path) -> str | None:
    """Return the campaign key (e.g. ``Campaign_1``) for a pickle path."""
    for part in path.parts:
        match = _CAMPAIGN_RE.match(part)
        if match:
            return match.group(1)
    return None


def mode_key(path: Path) -> str | None:
    """Return the mode directory name (e.g. ``01_FedBatch``) for a path."""
    for part in path.parts:
        match = _MODE_RE.match(part)
        if match and match.group(1) in MODE_LABELS:
            return match.group(1)
    return None


def run_strategy(path: Path) -> str | None:
    """Return the readable feed/perfusion strategy for a pickle path.

    Parses the export run folder (e.g. ``fedbatch_exponential_p2_...`` or
    ``cp_tbs_p2_...``) for a known strategy token. Returns None for modes
    without strategies (batch, chemostat) or unknown run folders.
    """
    for part in path.parts:
        tokens = part.lower().split("_")
        for token in tokens:
            if token in STRATEGY_LABELS:
                return STRATEGY_LABELS[token]
    return None


def campaign_label(path: Path) -> str | None:
    """Return the cell-line label for the campaign a pickle belongs to.

    Matches the first path part starting with ``Campaign_<n>``. Returns
    None when the path is not inside a campaign folder.
    """
    key = campaign_key(path)
    return CAMPAIGN_LABELS.get(key, key) if key else None


def mode_label(path: Path) -> str | None:
    """Return the readable operating-mode name for a pickle path.

    Matches a numbered mode directory (e.g. ``01_FedBatch``) among the
    path parts. Returns None when no mode directory is present.
    """
    key = mode_key(path)
    return MODE_LABELS[key] if key else None


def describe_pickle(path: Path, *, relative_to: Path | None = None) -> str:
    """Build a human-readable description of a simulation pickle file.

    Format: ``<Cell line>  ·  <Mode>  ·  <run folder>/<filename>``.
    Falls back to the plain (relative) path when campaign/mode cannot be
    determined from the location.
    """
    try:
        display_path = path.relative_to(relative_to) if relative_to else path
    except ValueError:
        display_path = path

    campaign = campaign_label(path)
    mode = mode_label(path)

    # Run folder + filename keep the export timestamp visible.
    tail = Path(*display_path.parts[-2:]) if len(display_path.parts) >= 2 else display_path

    if campaign and mode:
        return f"{campaign}  ·  {mode}  ·  {tail}"
    if campaign:
        return f"{campaign}  ·  {tail}"
    return str(display_path)
