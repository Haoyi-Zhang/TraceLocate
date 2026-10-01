#!/usr/bin/env python3
"""One-command, fail-closed reproduction for the supported evidence scope.

Supported scope: 432 finite-model tasks plus the 28-case pinned UART bridge.
The excluded arbiter and PicoRV32 drafts are not called, counted, or treated as
scientific evidence.  A full run requires an Icarus Verilog executable; an
explicit retained-only mode is available for environments without a simulator
and is labelled accordingly rather than reported as a full replay.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))
from output_safety import create_new_output

DROP_KEY_PARTS = (
    "elapsed", "wall", "runtime", "seconds", "duration", "cpu_time",
    "peak_rss", "rss_kib", "timestamp", "generated_at", "hostname",
    "absolute_path", "command_line",
)


def run(command: list[str], *, cwd: Path = ROOT, log: Path | None = None) -> str:
    proc = subprocess.run(command, cwd=cwd, text=True, stdout=subprocess.PIPE,
                          stderr=subprocess.STDOUT, check=False)
    if log is not None:
        log.parent.mkdir(parents=True, exist_ok=True)
        log.write_text(proc.stdout, encoding="utf-8")
    if proc.returncode:
        raise RuntimeError(f"command failed ({proc.returncode}): {' '.join(command)}\n{proc.stdout}")
    return proc.stdout


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for block in iter(lambda: fh.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def normalize(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: normalize(item)
            for key, item in value.items()
            if not any(part in str(key).lower() for part in DROP_KEY_PARTS)
        }
    if isinstance(value, list):
        return [normalize(item) for item in value]
    if isinstance(value, str):
        return value.replace(str(ROOT), "<ROOT>")
    return value


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def campaign_ids(instance: Path) -> list[str]:
    obj = load_json(instance)
    ids = [case["id"] for case in obj["cases"]]
    if len(ids) != len(set(ids)):
        raise AssertionError(f"duplicate case identifiers in {instance}")
    return ids


def compare_campaign(instance: Path, retained: Path, regenerated: Path) -> dict[str, Any]:
    ids = campaign_ids(instance)
    expected = set(ids)
    report: dict[str, Any] = {"cases": len(ids), "certificates": len(ids)}
    for leaf in ("cases", "certificates"):
        rset = {p.stem for p in (retained / leaf).glob("*.json")}
        gset = {p.stem for p in (regenerated / leaf).glob("*.json")}
        if rset != expected or gset != expected:
            raise AssertionError({"leaf": leaf, "retained": sorted(rset ^ expected),
                                  "regenerated": sorted(gset ^ expected)})
    feasible = infeasible = zero_loss = 0
    for ident in ids:
        rc = retained / "certificates" / f"{ident}.json"
        gc = regenerated / "certificates" / f"{ident}.json"
        if rc.read_bytes() != gc.read_bytes():
            raise AssertionError(f"certificate differs: {ident}")
        rr = normalize(load_json(retained / "cases" / f"{ident}.json"))
        gr = normalize(load_json(regenerated / "cases" / f"{ident}.json"))
        if rr != gr:
            raise AssertionError(f"deterministic case fields differ: {ident}")
        if gr["status"] == "feasible":
            feasible += 1
        elif gr["status"] == "infeasible":
            infeasible += 1
        else:
            raise AssertionError(f"unexpected status: {ident}: {gr['status']}")
        zero_loss += int(gr["full_minimum_loss"] == 0)
    report.update(feasible=feasible, infeasible=infeasible, zero_loss_infeasible=zero_loss)
    return report


def compare_summary(retained: Path, regenerated: Path) -> None:
    if normalize(load_json(retained)) != normalize(load_json(regenerated)):
        raise AssertionError(f"scientific summary mismatch: {retained} vs {regenerated}")


def compare_uart_rebuild(candidate: Path) -> dict[str, int]:
    retained_bridge = ROOT / "rtl/ben-marshall-uart"
    candidate_bridge = candidate / "rtl/ben-marshall-uart"
    relative_files = [
        Path("trace_manifest.json"), Path("import_report.json"),
        Path("generated/manifest.json"), Path("generated/compile.log"),
        Path("generated/uart_tx.v"), Path("generated/uart_rx.v"),
    ]
    relative_files.extend(p.relative_to(retained_bridge)
                          for p in sorted((retained_bridge / "traces").rglob("*.csv")))
    checked = 0
    for rel in relative_files:
        left, right = retained_bridge / rel, candidate_bridge / rel
        if left.read_bytes() != right.read_bytes():
            raise AssertionError(f"UART rebuild differs: {rel}")
        checked += 1
    for rel in (Path("models/uart-loopback-rtl.json"), Path("models/rtl-campaign.json")):
        if (ROOT / rel).read_bytes() != (candidate / rel).read_bytes():
            raise AssertionError(f"UART imported input differs: {rel}")
        checked += 1
    return {"byte_identical_files": checked, "traces": 33}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=Path("reproductions/run"),
                        help="new path under artifact/reproductions/; existing paths are refused")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--iverilog", type=Path,
                      help="Icarus Verilog executable for full source-level UART replay")
    mode.add_argument("--retained-only", action="store_true",
                      help="validate retained UART traces without recompilation; not a full replay")
    args = parser.parse_args()

    out = create_new_output(ROOT, args.out)
    logs = out / "logs"
    started = time.perf_counter()

    # Safety is tested only in disposable temporary fixtures.
    run([sys.executable, str(ROOT / "tests/test_output_safety.py"),
         "--out", str(out / "output-safety.json")], log=logs / "output-safety.log")

    # Stage 1: regenerate and independently consume all 432 finite-model tasks.
    finite = out / "finite"
    run([sys.executable, str(ROOT / "src/run_campaign.py"), "--root", str(ROOT),
         "--instance", str(ROOT / "models/campaign.json"),
         "--out", str(finite / "campaign"), "--seconds", "2700"],
        log=logs / "finite-campaign.log")
    run([sys.executable, str(ROOT / "src/summarize.py"), "--root", str(ROOT),
         "--instance", str(ROOT / "models/campaign.json"),
         "--results", str(finite / "campaign"), "--out", str(finite / "summary")],
        log=logs / "finite-summary.log")
    finite_compare = compare_campaign(ROOT / "models/campaign.json",
                                      ROOT / "results/campaign", finite / "campaign")
    compare_summary(ROOT / "results/summary/summary.json", finite / "summary/summary.json")
    if finite_compare != {"cases": 432, "certificates": 432, "feasible": 85,
                           "infeasible": 347, "zero_loss_infeasible": 327}:
        raise AssertionError(f"unexpected finite matrix: {finite_compare}")

    # Stage 2: validate the retained UART source-to-language bridge.  A full
    # run additionally rebuilds in an isolated temporary copy and requires
    # byte-identical traces, model and 28-case campaign.
    uart = out / "uart"
    run([sys.executable, str(ROOT / "src/check_rtl_bridge.py"), "--root", str(ROOT),
         "--out", str(uart / "bridge-retained.json")], log=logs / "uart-bridge-retained.log")
    replay: dict[str, Any] = {"source_level_resimulation": False}
    if args.iverilog:
        iv = args.iverilog.resolve(strict=True)
        if not (iv.is_file() and iv.with_name("vvp").is_file()):
            raise SystemExit("--iverilog must name an executable with a sibling vvp")
        with tempfile.TemporaryDirectory(prefix="coverage-uart-rebuild-") as td:
            candidate = Path(td) / "artifact"
            (candidate / "rtl").mkdir(parents=True)
            shutil.copytree(ROOT / "rtl/ben-marshall-uart", candidate / "rtl/ben-marshall-uart")
            (candidate / "models").mkdir()
            for name in ("uart-loopback-rtl.json", "rtl-campaign.json"):
                shutil.copy2(ROOT / "models" / name, candidate / "models" / name)
            run([sys.executable, str(candidate / "rtl/ben-marshall-uart/rebuild.py"),
                 "--iverilog", str(iv)], cwd=candidate,
                log=logs / "uart-source-rebuild.log")
            run([sys.executable, str(ROOT / "src/check_rtl_bridge.py"), "--root", str(candidate),
                 "--out", str(uart / "bridge-rebuilt.json")],
                log=logs / "uart-bridge-rebuilt.log")
            replay = {"source_level_resimulation": True, **compare_uart_rebuild(candidate)}

    # Stage 3: regenerate the authoritative 28-case UART campaign.
    run([sys.executable, str(ROOT / "src/run_campaign.py"), "--root", str(ROOT),
         "--instance", str(ROOT / "models/rtl-campaign.json"),
         "--out", str(uart / "campaign"), "--seconds", "2700"],
        log=logs / "uart-campaign.log")
    run([sys.executable, str(ROOT / "src/summarize.py"), "--root", str(ROOT),
         "--instance", str(ROOT / "models/rtl-campaign.json"),
         "--results", str(uart / "campaign"), "--out", str(uart / "summary")],
        log=logs / "uart-summary.log")
    uart_compare = compare_campaign(ROOT / "models/rtl-campaign.json",
                                    ROOT / "results/rtl-campaign", uart / "campaign")
    compare_summary(ROOT / "results/rtl-summary/summary.json", uart / "summary/summary.json")
    if uart_compare != {"cases": 28, "certificates": 28, "feasible": 12,
                         "infeasible": 16, "zero_loss_infeasible": 8}:
        raise AssertionError(f"unexpected UART matrix: {uart_compare}")
    run([sys.executable, str(ROOT / "tests/test_rtl_bridge.py"),
         str(uart / "bridge-mutations.json")], log=logs / "uart-bridge-mutations.log")
    run([sys.executable, str(ROOT / "tests/test_uart_regressions.py"),
         "--out", str(uart / "regressions.json")], log=logs / "uart-regressions.log")

    # Stage 4: independent finite checks, certificate mutations and timing-only
    # microbenchmarks.  Pilot scripts run with an output-local working directory.
    math = out / "math"
    (math / "results").mkdir(parents=True)
    run([sys.executable, str(ROOT / "tests/pilot.py")], cwd=math,
        log=logs / "subsequence-pilot.log")
    run([sys.executable, str(ROOT / "tests/kernel_pilot.py")], cwd=math,
        log=logs / "frontier-pilot.log")
    run([sys.executable, str(ROOT / "tests/test_contract.py"),
         str(math / "contract-tests.json")], log=logs / "contract-tests.log")
    run([sys.executable, str(ROOT / "tests/exhaustive_small.py"),
         "--out", str(math / "exhaustive-small.json")], log=logs / "exhaustive-small.log")
    run([sys.executable, str(ROOT / "src/independent_math_validation.py"),
         "--out", str(math / "independent-math-validation.json")],
        log=logs / "independent-math-validation.log")
    run([sys.executable, str(ROOT / "src/check_alias.py"),
         "--model", str(ROOT / "models/lfsr.json"),
         "--certificate", str(ROOT / "models/alias-witness.json"),
         "--out", str(math / "alias-check.json")], log=logs / "alias-check.log")
    run([sys.executable, str(ROOT / "src/microbenchmark.py"),
         "--out", str(out / "microbenchmark")], log=logs / "microbenchmark.log")

    bridge_mutations = load_json(uart / "bridge-mutations.json")
    uart_regressions = load_json(uart / "regressions.json")
    contract = load_json(math / "contract-tests.json")
    independent = load_json(math / "independent-math-validation.json")
    exhaustive = load_json(math / "exhaustive-small.json")
    if bridge_mutations.get("status") != "passed" or bridge_mutations.get("mutations_rejected") != 8:
        raise AssertionError("UART bridge mutation suite did not reject all eight directed changes")
    if uart_regressions.get("status") != "passed":
        raise AssertionError("UART mask/fault regression suite failed")
    if contract.get("result") != "all assertions passed" or len(contract.get("invalid_mutations", [])) != 24:
        raise AssertionError("certificate mutation suite did not reject all 24 directed changes")
    if independent.get("status") != "pass" or exhaustive.get("status") != "passed":
        raise AssertionError("independent finite oracle failed")

    full = bool(args.iverilog)
    summary = {
        "schema": "coverage-certified-reproduction-v3",
        "status": "passed" if full else "passed-retained-only",
        "supported_scope": "432 finite-model tasks plus 28 UART tasks",
        "unsupported_additions_excluded": ["24-case arbiter draft", "PicoRV32 draft"],
        "finite": finite_compare,
        "uart": uart_compare,
        "uart_bridge": load_json(uart / "bridge-retained.json"),
        "uart_replay": replay,
        "uart_bridge_mutations_rejected": bridge_mutations["mutations_rejected"],
        "certificate_mutations_rejected": len(contract["invalid_mutations"]),
        "uart_regressions": uart_regressions,
        "independent_math_validation": independent,
        "exhaustive_small": exhaustive,
        "bounded_resources": {"workers": 1, "cpu_only": True},
        "wall_seconds": time.perf_counter() - started,
    }
    (out / "summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")
    print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
