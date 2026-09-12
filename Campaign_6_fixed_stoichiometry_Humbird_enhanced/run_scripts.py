"""
Script to automatically execute all simulation scripts (*.py) in the
Campaign folder. Discovers files recursively and supports an exclude list.
Parallel execution via multiprocessing for faster processing. Child-script
output is streamed live, including differential-evolution iteration updates.

Usage:
        python run_scripts.py

Configuration:
        - EXCLUDE: list of filenames (e.g. "batch.py") or relative folder/path
            patterns (e.g. "06_Scenarios", "05_ContinuousPerfusion/cp_cspr.py")
            to skip during execution. Matching is case-insensitive.
        - SETTINGS: timeouts, parallelism, and logging options.
"""

import json
import multiprocessing
import os
import subprocess
import sys
import threading
import time
from concurrent.futures import FIRST_COMPLETED, ProcessPoolExecutor, wait
from datetime import datetime
from pathlib import Path

# ==================== CONFIGURATION ====================

# Scripts / folders to skip.
# Each entry can be:
#   - A script filename:           "batch_E.py"
#   - A relative path to script:   "05_ContinuousPerfusion/cp_cspr_E.py"
#   - A folder name / path prefix: "06_Scenarios"
# Matching is case-insensitive.
EXCLUDE: list[str] = [
    # "01_FedBatch",
    # "01_FedBatch\\fedbatch_constant.py",
    # "01_FedBatch\\fedbatch_csfr.py",
    # "01_FedBatch\\fedbatch_exponential.py",
    # "01_FedBatch\\fedbatch_gsp.py",
    # "01_FedBatch\\fedbatch_linear.py",
    # "02_Batch",
    # "03_Chemostat",
    # "04_ConcentratedFedBatch",
    # "04_ConcentratedFedBatch\\cf_constant.py",
    # "04_ConcentratedFedBatch\\cf_cspr.py",
    # "04_ConcentratedFedBatch\\cf_tbp.py",
    # "04_ConcentratedFedBatch\\cf_tbs.py",
    # "04_ConcentratedFedBatch\\cf_gsp.py",
    # "05_ContinuousPerfusion",
    # "05_ContinuousPerfusion\\cp_constant.py",
    # "05_ContinuousPerfusion\\cp_cspr.py",
    # "05_ContinuousPerfusion\\cp_tbp.py",
    # "05_ContinuousPerfusion\\cp_tbs.py",
    # "05_ContinuousPerfusion\\cp_gsp.py",
    "06_Scenarios",
    "06_Analysis",
]

# Child-output lines to hide from the live console. These LSODA wrapper
# diagnostics are retained in a failed script's output tail for debugging.
SUPPRESSED_OUTPUT_SUBSTRINGS = (
    "capi_return is NULL",
    "Call-back cb_f_in_lsoda__user__routines failed",
)

SETTINGS = {
    "timeout": 60 * 60 * 24,   # Timeout per script in seconds (1 day)
    "stop_on_error": False,     # Continue even if a script fails
    "create_log": True,         # Write a JSON execution log to logs/
    "max_workers": 1,           # Parallel worker processes.  Keep LOW: each script
                                # spawns its own internal optimisation workers, so
                                # outer × inner processes multiply quickly.
                                # Set to None to use all CPU cores (not recommended).
    "status_interval": 300,      # Seconds between live progress prints
}
# =======================================================


def execute_script(script_path, timeout):
    """Execute a Python script via subprocess.

    The script's parent directory is used as the working directory so that
    relative paths inside the script resolve correctly. Output is relayed as
    it is produced so optimization progress is visible from the runner.
    """
    script_path = Path(script_path)
    try:
        env = os.environ.copy()
        env["PYTHONIOENCODING"] = "utf-8"
        env["PYTHONUNBUFFERED"] = "1"
        # Keep live optimizer generation updates, but suppress per-call timing
        # diagnostics from package decorators during batch execution.
        env["ANIMAKINETICA_TIMING_OUTPUT"] = "0"
        process = subprocess.Popen(
            [sys.executable, "-u", str(script_path)],
            cwd=str(script_path.parent),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
            env=env,
        )
        output_tail = ""

        def relay_output() -> None:
            """Relay child output while retaining failure context.

            Known LSODA wrapper diagnostics are omitted from the live console,
            but remain in ``output_tail`` if the child script fails.
            """
            nonlocal output_tail
            assert process.stdout is not None
            for line in process.stdout:
                output_tail = (output_tail + line)[-2000:]
                if any(message in line for message in SUPPRESSED_OUTPUT_SUBSTRINGS):
                    continue
                print(f"[{script_path.name}] {line}", end="", flush=True)

        output_thread = threading.Thread(target=relay_output, daemon=True)
        output_thread.start()
        try:
            return_code = process.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
            output_thread.join()
            return {
                "status": "timeout",
                "script": str(script_path),
                "message": f"✗ Timeout executing: {script_path.name}",
                "error": output_tail,
            }

        output_thread.join()
        if return_code == 0:
            return {
                "status": "success",
                "script": str(script_path),
                "message": f"✓ Successfully executed: {script_path.name}",
            }

        return {
            "status": "failed",
            "script": str(script_path),
            "message": f"✗ Script error in: {script_path.name}",
            "error": output_tail,
        }
    except Exception as e:
        return {
            "status": "error",
            "script": str(script_path),
            "message": f"✗ Error executing {script_path.name}: {e}",
            "error": str(e),
        }


def is_excluded(script_path: Path, base_path: Path, exclude: list[str]) -> bool:
    """Return True if *script_path* matches any entry in *exclude*."""
    rel = script_path.relative_to(base_path).as_posix().lower()
    for pattern in exclude:
        p = pattern.replace("\\", "/").lower().strip("/")
        if script_path.name.lower() == p or rel == p or rel.startswith(p + "/"):
            return True
    return False


class ScriptRunner:
    """Manages parallel execution of Python simulation scripts."""

    def __init__(self, base_path: Path, exclude: list[str], settings: dict):
        self.base_path = Path(base_path)
        self.exclude = exclude
        self.settings = settings
        self.results = {
            "executed": [],
            "failed": [],
            "skipped": [],
            "start_time": datetime.now(),
        }

    def discover_scripts(self) -> list[Path]:
        """Recursively find all .py files, excluding this runner and the exclude list."""
        runner_script = (self.base_path / "run_scripts.py").resolve()
        all_scripts = sorted(
            f for f in self.base_path.rglob("*.py")
            if f.resolve() != runner_script
        )

        scripts, skipped = [], []
        for s in all_scripts:
            (skipped if is_excluded(s, self.base_path, self.exclude) else scripts).append(s)

        self.results["skipped"] = [str(s) for s in skipped]
        return scripts

    @staticmethod
    def _fmt_elapsed(seconds: float) -> str:
        """Format seconds as HH:MM:SS."""
        h, rem = divmod(int(seconds), 3600)
        m, s = divmod(rem, 60)
        return f"{h:02d}:{m:02d}:{s:02d}"

    def _monitor_progress(
        self,
        running_status: dict,
        queued_status: list,
        status_lock: threading.Lock,
        done_event: threading.Event,
        total: int,
        interval: int,
    ) -> None:
        """Background thread: print a live status table every *interval* seconds."""
        while not done_event.wait(timeout=interval):
            now = time.monotonic()
            with status_lock:
                running = [
                    (status["script"], status["started_at"])
                    for status in running_status.values()
                ]
                queued = [
                    (status["script"], status["queued_at"])
                    for status in queued_status
                ]

            if not running and not queued:
                break

            completed_count = total - len(running) - len(queued)
            print(f"\n⏳  Progress: {completed_count}/{total} done  "
                  f"— {len(running)} running, {len(queued)} queued")

            status_rows = running + queued
            width = max(len(s.name) for s, _ in status_rows)

            if running:
                print("   Running:")
                for s, t0 in sorted(running, key=lambda x: x[1]):
                    print(f"   › {s.name:<{width}}  {self._fmt_elapsed(now - t0)}")

            if queued:
                print("   Queued:")
                for s, t0 in sorted(queued, key=lambda x: x[1]):
                    print(f"   · {s.name:<{width}}  queued for {self._fmt_elapsed(now - t0)}")

    def run_all(self) -> None:
        """Execute all discovered scripts in parallel."""
        scripts = self.discover_scripts()

        if not scripts:
            print("No scripts found to execute based on current configuration.")
            return

        max_workers = self.settings.get("max_workers") or multiprocessing.cpu_count()
        status_interval = self.settings.get("status_interval", 30)
        timeout = self.settings["timeout"]

        print(f"\nFound {len(scripts)} script(s) to execute:")
        for s in scripts:
            print(f"  - {s.relative_to(self.base_path)}")

        print(f"\nUsing {max_workers} parallel workers")
        print(f"Status update every {status_interval}s")
        print(f"Starting at {self.results['start_time'].strftime('%Y-%m-%d %H:%M:%S')}")
        print("=" * 80)

        with ProcessPoolExecutor(max_workers=max_workers) as executor:
            status_lock = threading.Lock()
            running_status: dict = {}
            queued_status = [
                {"script": s, "queued_at": time.monotonic()}
                for s in scripts
            ]
            future_to_script: dict = {}

            def submit_next_script():
                with status_lock:
                    if not queued_status:
                        return None
                    queued_item = queued_status.pop(0)

                s = queued_item["script"]
                fut = executor.submit(execute_script, s, timeout)

                with status_lock:
                    running_status[fut] = {
                        "script": s,
                        "started_at": time.monotonic(),
                    }

                future_to_script[fut] = s
                print(f"  → Started: {s.relative_to(self.base_path)}")
                return fut

            pending_futures = set()
            for _ in range(min(max_workers, len(scripts))):
                fut = submit_next_script()
                if fut is not None:
                    pending_futures.add(fut)

            with status_lock:
                remaining_queued = [item["script"] for item in queued_status]

            for s in remaining_queued:
                print(f"  → Queued : {s.relative_to(self.base_path)}")

            print(f"\n{'─' * 80}")

            done_event = threading.Event()
            monitor = threading.Thread(
                target=self._monitor_progress,
                args=(running_status, queued_status, status_lock, done_event, len(scripts), status_interval),
                daemon=True,
            )
            monitor.start()

            completed = 0
            stop_requested = False
            while pending_futures:
                done_futures, _ = wait(pending_futures, return_when=FIRST_COMPLETED)
                for future in done_futures:
                    pending_futures.remove(future)
                    completed += 1
                    result = future.result()

                    with status_lock:
                        status = running_status.pop(future)

                    s = status["script"]
                    elapsed = self._fmt_elapsed(time.monotonic() - status["started_at"])

                    print(f"\n[{completed}/{len(scripts)}] {result['message']}  (elapsed: {elapsed})")

                    if result["status"] == "success":
                        self.results["executed"].append(result["script"])
                    else:
                        suffix = f" ({result.get('error', result['status'])})" if "error" in result else f" ({result['status']})"
                        self.results["failed"].append(result["script"] + suffix)

                        if self.settings["stop_on_error"]:
                            print("\nStopping execution due to error (stop_on_error=True)")
                            stop_requested = True
                            done_event.set()
                            executor.shutdown(wait=False, cancel_futures=True)
                            break

                    next_future = submit_next_script()
                    if next_future is not None:
                        pending_futures.add(next_future)

                if stop_requested:
                    break

            done_event.set()
            monitor.join()

        self._print_summary()
        if self.settings["create_log"]:
            self._save_log()

    def _print_summary(self) -> None:
        """Print execution summary."""
        end_time = datetime.now()
        print("\n" + "=" * 80)
        print("EXECUTION SUMMARY")
        print("=" * 80)
        print(f"Start time:  {self.results['start_time'].strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"End time:    {end_time.strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"Duration:    {end_time - self.results['start_time']}")
        total = len(self.results["executed"]) + len(self.results["failed"])
        print(f"\nTotal scripts: {total}")
        print(f"  ✓ Successful:  {len(self.results['executed'])}")
        print(f"  ✗ Failed:      {len(self.results['failed'])}")
        print(f"  ⊘ Skipped:     {len(self.results['skipped'])}")
        if self.results["failed"]:
            print("\nFailed scripts:")
            for s in self.results["failed"]:
                print(f"  - {s}")

    def _save_log(self) -> None:
        """Save a JSON execution log to logs/."""
        log_dir = self.base_path / "logs"
        log_dir.mkdir(exist_ok=True)
        log_file = log_dir / f"execution_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        log_data = {
            "start_time": self.results["start_time"].isoformat(),
            "end_time": datetime.now().isoformat(),
            "exclude": self.exclude,
            "settings": self.settings,
            "results": {
                "executed": self.results["executed"],
                "failed": self.results["failed"],
                "skipped": self.results["skipped"],
            },
        }
        with open(log_file, "w") as f:
            json.dump(log_data, f, indent=2)
        print(f"\nLog saved to: {log_file}")


def main() -> None:
    base_path = Path(__file__).parent
    runner_script = (base_path / "run_scripts.py").resolve()

    print("=" * 80)
    print("PARALLEL SCRIPT EXECUTION RUNNER")
    print("=" * 80)
    print(f"Base path: {base_path}")
    print(f"Available CPU cores: {multiprocessing.cpu_count()}")

    all_scripts = sorted(
        f for f in base_path.rglob("*.py")
        if f.resolve() != runner_script
    )
    included = [s for s in all_scripts if not is_excluded(s, base_path, EXCLUDE)]
    excluded = [s for s in all_scripts if is_excluded(s, base_path, EXCLUDE)]

    print(f"\nScripts discovered: {len(all_scripts)}")
    print(f"  Will run:  {len(included)}")
    print(f"  Excluded:  {len(excluded)}")

    if included:
        print("\nScripts to execute:")
        for s in included:
            print(f"  + {s.relative_to(base_path)}")

    if excluded:
        print("\nExcluded:")
        for s in excluded:
            print(f"  - {s.relative_to(base_path)}")

    print("\nSettings:")
    for key, value in SETTINGS.items():
        if key == "max_workers" and value is None:
            value = f"None (will use all {multiprocessing.cpu_count()} cores)"
        print(f"  {key:.<40} {value}")

    print("\n" + "=" * 80)
    if input("Proceed with execution? (y/n): ").strip().lower() != "y":
        print("Execution cancelled.")
        return

    ScriptRunner(base_path, EXCLUDE, SETTINGS).run_all()


if __name__ == "__main__":
    main()