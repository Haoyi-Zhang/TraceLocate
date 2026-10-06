"""Bounded finite/retained-data checks; no simulator, network, or RTL execution.

Run from the standalone artifact repository. Raw attempts, mutation fixtures,
regenerated packets, and subprocess output are retained in a new --out path.
This does not perform source-level resimulation or build/inspect the paper PDF.
"""
from __future__ import annotations
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from _reproduce_core import compare_campaign, compare_summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--seconds", type=float, default=900)
    args = parser.parse_args()
    if not 0 < args.seconds <= 900:
        parser.error("whole-run budget must be in (0,900] seconds")
    out = args.out.resolve()
    if out == ROOT or ROOT in out.parents:
        parser.error("--out must be outside this artifact repository")
    out.mkdir(parents=True, exist_ok=False)
    started = time.perf_counter()
    attempts = []

    def run(label: str, script: str, *arguments: str, cwd: Path = ROOT) -> None:
        remaining = args.seconds - (time.perf_counter() - started)
        if remaining <= 0:
            raise TimeoutError("whole-run time budget exhausted")
        command = [sys.executable, "-B", str(ROOT / script), *map(str, arguments)]
        begin = time.perf_counter()
        record = {"label": label, "command": command, "cwd": str(cwd)}
        with (out / f"{label}.log").open("w", encoding="utf-8") as log:
            try:
                proc = subprocess.run(command, cwd=cwd, stdout=log,
                                      stderr=subprocess.STDOUT, timeout=remaining,
                                      env={**os.environ, "PYTHONUTF8": "1",
                                           "PYTHONDONTWRITEBYTECODE": "1"})
                record["returncode"] = proc.returncode
            except subprocess.TimeoutExpired:
                record["timeout"] = True
                raise
            finally:
                record["wall_seconds"] = time.perf_counter() - begin
                attempts.append(record)
                (out / "attempts.json").write_text(json.dumps(attempts, indent=2) + "\n",
                                                   encoding="utf-8")
        if proc.returncode:
            raise RuntimeError(f"{label} failed ({proc.returncode}); see retained log")

    run("syntax", ".github/scripts/check_repository.py")
    run("bridge", "src/check_rtl_bridge.py", "--out", out / "bridge.json")
    run("bridge-mutations", "tests/test_rtl_bridge.py", out / "bridge-mutations.json",
        "--fixtures", out / "bridge-fixtures")
    run("uart-regressions", "tests/test_uart_regressions.py", "--out", out / "uart-regressions.json")
    comparisons = {}
    for name, instance, retained, expected in (
        ("finite", "models/campaign.json", "results/campaign", (432, 85, 347, 327)),
        ("uart", "models/rtl-campaign.json", "results/rtl-campaign", (28, 12, 16, 8)),
    ):
        run(f"{name}-campaign", "src/run_campaign.py", "--root", ROOT,
            "--instance", ROOT / instance, "--out", out / name / "campaign", "--seconds", "900")
        run(f"{name}-summary", "src/summarize.py", "--root", ROOT,
            "--instance", ROOT / instance, "--results", out / name / "campaign",
            "--out", out / name / "summary")
        checked = compare_campaign(ROOT / instance, ROOT / retained, out / name / "campaign")
        expected_summary = dict(zip(("cases", "feasible", "infeasible", "zero_loss_infeasible"), expected))
        if any(checked[k] != v for k, v in expected_summary.items()):
            raise AssertionError(f"{name}: unexpected scientific outcomes: {checked}")
        compare_summary(ROOT / ("results/summary/summary.json" if name == "finite"
                               else "results/rtl-summary/summary.json"),
                        out / name / "summary/summary.json")
        comparisons[name] = checked
    math = out / "math"
    (math / "results").mkdir(parents=True)
    run("pilot", "tests/pilot.py", cwd=math)
    run("kernel", "tests/kernel_pilot.py", cwd=math)
    run("contract", "tests/test_contract.py", math / "contract.json")
    run("exhaustive", "tests/exhaustive_small.py", "--out", math / "exhaustive.json")
    run("independent", "src/independent_math_validation.py", "--out", math / "independent.json")
    run("alias", "src/check_alias.py", "--model", ROOT / "models/lfsr.json",
        "--certificate", ROOT / "models/alias-witness.json", "--out", math / "alias.json")

    def load(path: Path):
        return json.loads(path.read_text(encoding="utf-8"))
    mutations = load(out / "bridge-mutations.json")
    contract = load(math / "contract.json")
    if mutations["status"] != "passed" or mutations["mutations_rejected"] != 10:
        raise AssertionError("bridge mutation count/status")
    if contract["result"] != "all assertions passed" or len(contract["invalid_mutations"]) != 24:
        raise AssertionError("certificate mutation count/status")
    if load(math / "exhaustive.json")["status"] != "passed" or load(math / "independent.json")["status"] != "pass":
        raise AssertionError("independent finite oracle status")
    summary = {"scope": "finite models and passive retained UART data only",
               "campaigns": comparisons, "bridge_mutations_rejected": 10,
               "certificate_mutations_rejected": 24, "source_resimulation": False,
               "pdf_build_or_visual_qa": False, "wall_seconds": time.perf_counter() - started}
    if summary["wall_seconds"] > args.seconds:
        raise TimeoutError("whole-run time budget exceeded")
    (out / "scientific-results.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
