"""
Simulation Script

Runs a simulation for this campaign, optimizes key parameters using differential
evolution, and exports all results (Excel + pickle + parameter set) to the
local export/ directory.

Template: copy this file, rename it to match the simulation ID in
campaign_config.yaml, and it will automatically pick up the correct settings.

Sections:
    1. Setup & Imports
    2. Load Campaign Config & Parameters
    3. Baseline Simulation
    4. Optimization
    5. Performance Comparison
    6. Final Simulation Check
    7. Export Results
"""

# ==============================================================================
# 1. Setup & Imports
# ==============================================================================
import yaml
from copy import deepcopy
from pathlib import Path

# ── Resolve paths ──────────────────────────────────────────────────────────────
SCRIPT_DIR     = Path(__file__).resolve().parent   # e.g. 01_Batch/
CAMPAIGN_DIR   = SCRIPT_DIR.parent                 # Campaign_..._.../
PARAMS_DIR     = CAMPAIGN_DIR / "parameters"       # campaign parameters
OPT_CONFIG_DIR = CAMPAIGN_DIR / "optimization_config"  # campaign opt configs
CONFIG_FILE_NAME = "campaign_config.yaml"
NORM_FILE_NAME = "campaign_normalization.yaml"


def load_campaign_config(campaign_dir: Path, config_filename: str) -> dict:
    """Load the campaign YAML configuration file."""
    with open(campaign_dir / config_filename, encoding="utf-8") as file:
        campaign_config = yaml.safe_load(file)

    if not isinstance(campaign_config, dict):
        raise ValueError("Campaign config must be a mapping.")

    return campaign_config


def resolve_simulation_config(campaign_config: dict, sim_id: str) -> dict:
    """Merge campaign defaults, mode defaults, and simulation overrides."""
    simulations = campaign_config.get("simulations", [])
    sim_entry = next((entry for entry in simulations if entry.get("id") == sim_id), None)
    if sim_entry is None:
        raise KeyError(f"Simulation '{sim_id}' was not found in the campaign config.")

    merged_config = {}
    defaults = campaign_config.get("simulation_defaults", {})
    mode_defaults = campaign_config.get("mode_defaults", {}).get(sim_entry.get("mode"), {})

    for layer in (defaults, mode_defaults, sim_entry):
        merged_config = merge_config_layer(merged_config, layer)

    return merged_config


def merge_config_layer(base: dict, override: dict) -> dict:
    """Merge one config layer into another."""
    result = deepcopy(base)

    for key, value in override.items():
        if key == "parameter_sets":
            existing = result.get(key, []) or []
            additions = deepcopy(value) if value else []
            result[key] = [*existing, *additions]
        elif isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = merge_config_layer(result[key], value)
        else:
            result[key] = deepcopy(value)

    return result

# ── AnimaKinetica imports ──────────────────────────────────────────────────────
from animakinetica.core.simulation       import CellCultureSimulation
from animakinetica.core.parameters       import SimulationParameters
from animakinetica.models.kinetics       import Kinetics
from animakinetica.models.odesystems     import OperatingMode
from animakinetica.models.feed_strategies import FeedStrategy
from animakinetica.models.perfusion_strategies import PerfusionStrategy
from animakinetica.models.gas_controllers import GasController
from animakinetica.analysis.optimization import OptimizationManager

if __name__ == "__main__":
    print("✓ Imports successful")
    print(f"  Script dir    : {SCRIPT_DIR}")
    print(f"  Parameters dir: {PARAMS_DIR}")
    print(f"  Opt config dir: {OPT_CONFIG_DIR}")

    # ==============================================================================
    # 2. Load Campaign Config & Parameters
    #
    # SIM_ID is derived from the filename — rename this file to change the
    # simulation. All other settings are read from campaign_config.yaml.
    # ==============================================================================
    SIM_ID = Path(__file__).stem  # e.g. "batch_S"
    print(f"\n Simulation ID: {SIM_ID}")

    # ── Load campaign configuration ────────────────────────────────────────────────
    campaign_config = load_campaign_config(CAMPAIGN_DIR, CONFIG_FILE_NAME)

    # Resolve campaign defaults, mode defaults, and simulation overrides.
    sim_config   = resolve_simulation_config(campaign_config, SIM_ID)
    opt_settings = campaign_config["optimization_settings"]
    profiles = opt_settings.get("profiles")
    if profiles is None:
        # Backward compatibility for pre-profile campaign configurations.
        ACTIVE_PROFILE_NAME = "legacy_optimization_settings"
        optimization_profile = opt_settings
    else:
        ACTIVE_PROFILE_NAME = opt_settings.get("active_profile")
        if ACTIVE_PROFILE_NAME not in profiles:
            raise KeyError(
                f"Active optimization profile '{ACTIVE_PROFILE_NAME}' was not found. "
                f"Available profiles: {list(profiles)}"
            )
        optimization_profile = profiles[ACTIVE_PROFILE_NAME]

    # ── Simulation settings ────────────────────────────────────────────────────────
    # Convert string names from YAML to enum objects using EnumClass["NAME"] lookup.
    # Optional strategies (null in YAML → None in Python) are handled with a conditional.
    MODE               = OperatingMode[sim_config["mode"]]
    KINETICS           = Kinetics[sim_config["kinetics"]]
    FEED_STRATEGY      = FeedStrategy[sim_config["feed_strategy"]]       if sim_config["feed_strategy"]      else None
    PERFUSION_STRATEGY = PerfusionStrategy[sim_config["perfusion_strategy"]] if sim_config["perfusion_strategy"] else None
    SOLVER_METHOD = sim_config.get("solver_method", "LSODA")

    # ── Parameter file paths ───────────────────────────────────────────────────────
    PARAM_FILES = [PARAMS_DIR / Path(entry).with_suffix(".yaml")
                   for entry in sim_config["parameter_sets"]]
    INITIAL_PARAMETER_PATCH = optimization_profile.get("initial_parameter_patch")
    if INITIAL_PARAMETER_PATCH:
        initial_patch_path = PARAMS_DIR / Path(
            INITIAL_PARAMETER_PATCH.replace("{simulation_id}", SIM_ID)
        ).with_suffix(".yaml")
        if not initial_patch_path.is_file():
            raise FileNotFoundError(
                f"Initial parameter patch for profile '{ACTIVE_PROFILE_NAME}' was not found: "
                f"{initial_patch_path}. Run and promote the matching sweep-1 result first."
            )
        PARAM_FILES.append(initial_patch_path)

    # ── Optimization settings ──────────────────────────────────────────────────────
    if sim_config["optimize"]:
        OBJECTIVES      = optimization_profile["objectives"]
        WEIGHTS         = [optimization_profile["objective_weights"][obj] for obj in OBJECTIVES]
        SCORING_MODE    = optimization_profile.get("scoring_mode", "campaign_normalized")
        DESIRABILITY_CONFIG = optimization_profile.get("desirability")
        SEED            = opt_settings["seed"]
        WORKERS         = opt_settings["workers"]
        TIMEOUT         = opt_settings.get("timeout", 5.0)
        OPT_CONFIG_FILE = OPT_CONFIG_DIR / f"{sim_config['opt_config']}_optimization.yaml"

    # ── Export filename ────────────────────────────────────────────────────────────
    EXPORT_FILENAME = optimization_profile.get("filename", opt_settings["filename"]).replace("{simulation_id}", SIM_ID)

    # ── Scoring configuration ──────────────────────────────────────────────────────
    campaign_norm = None
    if SCORING_MODE == "campaign_normalized":
        NORM_FILE = CAMPAIGN_DIR / NORM_FILE_NAME
        if NORM_FILE.exists():
            with open(NORM_FILE) as f:
                campaign_norm = yaml.safe_load(f)
            print(f"✓ Loaded campaign normalization from {NORM_FILE.name}")
            for obj, val in campaign_norm.items():
                if isinstance(val, (int, float)):
                    print(f"  {obj}: {val:.4g}")
        else:
            print("  ⚠ campaign_normalization.yaml not found; run create_normalization_values.ipynb first.")
            print("    Falling back to per-simulation baseline normalization.")
    elif SCORING_MODE == "engineering_desirability":
        if DESIRABILITY_CONFIG is None:
            raise ValueError(f"Profile '{ACTIVE_PROFILE_NAME}' requires a desirability configuration.")
        print("✓ Using engineering desirability scoring")
    else:
        raise ValueError(
            f"Unsupported scoring_mode '{SCORING_MODE}' in profile '{ACTIVE_PROFILE_NAME}'."
        )

    print(f"✓ Campaign config loaded: {SIM_ID} — {sim_config['label']}")
    print(f"  Mode               : {MODE}")
    print(f"  Kinetics           : {KINETICS}")
    print(f"  Feed strategy      : {FEED_STRATEGY}")
    print(f"  Perfusion strategy : {PERFUSION_STRATEGY}")
    print(f"  Solver method      : {SOLVER_METHOD}")
    print(f"  Optimize           : {sim_config['optimize']}")
    if sim_config["optimize"]:
        print(f"  Opt config         : {OPT_CONFIG_FILE.name}")
        print(f"  Objectives         : {OBJECTIVES}")
        print(f"  Weights            : {WEIGHTS}")
        print(f"  Scoring profile    : {ACTIVE_PROFILE_NAME} ({SCORING_MODE})")
        if INITIAL_PARAMETER_PATCH:
            print(f"  Initial patch      : {initial_patch_path.relative_to(PARAMS_DIR)}")
        print(f"  Seed / Workers     : {SEED} / {WORKERS}")
    print(f"  Export file        : {EXPORT_FILENAME}")

    # ── Load parameters ────────────────────────────────────────────────────────────
    params = SimulationParameters.load_parameters([str(p) for p in PARAM_FILES])
    print("\n✓ Parameters loaded successfully")
    print("  Files:")
    for p in PARAM_FILES:
        print(f"    {p.relative_to(PARAMS_DIR)}")

    # ==============================================================================
    # 3. Baseline Simulation
    # ==============================================================================
    sim_kwargs = {
        "parameters": params,
        "kinetics": KINETICS,
        "operating_mode": MODE,
        "feed_strategy": FEED_STRATEGY,
        "perfusion_strategy": PERFUSION_STRATEGY,
        "solver_method": SOLVER_METHOD,
        "gas_controller": GasController.CASCADE_N_FG_XO2,
    }

    baseline_sim = CellCultureSimulation(
        **sim_kwargs,
    )

    baseline_result = baseline_sim.run_simulation()

    print("\n✓ Baseline simulation completed")
    print("\nBaseline Performance Metrics:")
    for key, value in baseline_sim.data.summary_stats.items():
        if isinstance(value, float):
            print(f"  {key}: {value:.4f}")
        else:
            print(f"  {key}: {value}")

    # ==============================================================================
    # 4. Optimization
    #
    # Multi-objective optimization using differential evolution. Objectives, weights,
    # seed, and workers are all read from campaign4_config.yaml → optimization_settings.
    # The optimization parameter bounds come from the opt_config file resolved above.
    # ==============================================================================
    opt_manager = OptimizationManager(
        simulation=baseline_sim,
        opt_config_file=str(OPT_CONFIG_FILE),
    )

    print(f"\n✓ OptimizationManager initialized")
    print(f"  Config     : {OPT_CONFIG_FILE.name}")
    print(f"  Parameters : {len(opt_manager.opt_config)}")
    print("\nParameters to optimize:")
    for param, cfg in opt_manager.opt_config.items():
        print(f"  {param}: bounds={cfg['bounds']}")

    opt_manager.optimize_parameters(
        objectives=OBJECTIVES,
        weights=WEIGHTS,
        workers=WORKERS,
        seed=SEED,
        timeout=TIMEOUT,
        verbose=True,
        normalization_values=campaign_norm,
        desirability_config=DESIRABILITY_CONFIG,
        scoring_profile=ACTIVE_PROFILE_NAME,
        debug_rejections=False,
        evaluate_baseline=True,
        seed_baseline=True,
    )

    print("\n✓ Optimization completed")
    print("\nOptimal parameters found:")
    for param_name, value in opt_manager.optimal_parameters.items():
        cfg = opt_manager.opt_config[param_name]
        print(f"  {param_name}: {value:.6g} {cfg['unit']}")

    # ==============================================================================
    # 5. Performance Comparison
    # ==============================================================================
    comparison_df = opt_manager.compare_performance(verbose=True)

    # ==============================================================================
    # 6. Final Simulation Check
    # ==============================================================================
    final_sim = opt_manager.optimized_simulation

    print("\nFinal Performance Metrics:")
    for key, value in final_sim.data.summary_stats.items():
        if isinstance(value, float):
            print(f"  {key}: {value:.4f}")
        else:
            print(f"  {key}: {value}")

    # ==============================================================================
    # 7. Export Results
    #
    # Three outputs saved to the local export/ directory:
    #   c{CAMPAIGN_NO}_{SIM_ID}_opt_{timestamp}.xlsx         — full Excel export
    #   c{CAMPAIGN_NO}_{SIM_ID}_opt_{timestamp}.pkl          — complete simulation state (pickle)
    #   c{CAMPAIGN_NO}_{SIM_ID}_opt_{timestamp}.parameters.yaml — optimized parameter set
    # ==============================================================================
    EXPORT_DIR = SCRIPT_DIR / "export"
    EXPORT_DIR.mkdir(parents=True, exist_ok=True)

    final_sim.save(
        filename=EXPORT_FILENAME,
        file_format="excel",
        include_metadata=True,
        include_summary_stats=True,
        include_cultivation_summary=True,
        include_batch_data=True,
        include_parameters=False,
        include_pickle=True,
        include_opt_parameters=True,
        overwrite=True,
        export_dir=EXPORT_DIR,
    )

    PROMOTED_PARAMETER_PATCH = optimization_profile.get("promoted_parameter_patch")
    if PROMOTED_PARAMETER_PATCH:
        promoted_patch_path = PARAMS_DIR / Path(
            PROMOTED_PARAMETER_PATCH.replace("{simulation_id}", SIM_ID)
        ).with_suffix(".yaml")
        promoted_patch_path.parent.mkdir(parents=True, exist_ok=True)
        opt_manager.save_opt_parameters(promoted_patch_path, overwrite=True)
        print(f"✓ Promoted sweep-1 parameter patch: {promoted_patch_path.relative_to(PARAMS_DIR)}")

    print(f"\n✓ Export complete")
    print(f"  Directory : {EXPORT_DIR}")
    print("  Files written:")
    for f in sorted(EXPORT_DIR.rglob("*")):
        if f.is_file():
            print(f"    {f.relative_to(EXPORT_DIR)}  ({f.stat().st_size / 1024:.1f} KB)")
