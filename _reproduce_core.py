#!/usr/bin/env python3
"""Clean, bounded reproduction entry point for the complete artifact.

The wrapper retains the previously validated finite-model/UART pipeline as a
compatibility stage, then independently rebuilds and compares the two-system
public-RTL campaign, the second RTL bridge, directed mutations, and a
standalone exhaustive small-instance oracle.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any, Iterable

ROOT = Path(__file__).resolve().parent
DROP_KEY_PARTS = (
    "elapsed", "wall", "runtime", "seconds", "duration", "cpu_time",
    "peak_rss", "rss_kib", "timestamp", "generated_at", "hostname",
    "absolute_path", "command_line",
)


def run(command: list[str], *, cwd: Path = ROOT, stdout_path: Path | None = None) -> subprocess.CompletedProcess[str]:
    proc = subprocess.run(command, cwd=cwd, text=True, capture_output=True, check=False)
    if stdout_path is not None:
        stdout_path.parent.mkdir(parents=True, exist_ok=True)
        stdout_path.write_text(proc.stdout + proc.stderr, encoding="utf-8")
    if proc.returncode:
        raise RuntimeError(
            "command failed (exit %d): %s\n%s%s" %
            (proc.returncode, " ".join(command), proc.stdout, proc.stderr)
        )
    return proc


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for block in iter(lambda: fh.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def normalize(value: Any, roots: Iterable[Path]) -> Any:
    roots_s = [str(root.resolve()) for root in roots]
    if isinstance(value, dict):
        result = {}
        for key, item in value.items():
            lower = str(key).lower()
            if any(part in lower for part in DROP_KEY_PARTS):
                continue
            result[key] = normalize(item, roots)
        return result
    if isinstance(value, list):
        return [normalize(item, roots) for item in value]
    if isinstance(value, str):
        text = value
        for root in roots_s:
            text = text.replace(root, "<ROOT>")
        return text
    return value


def normalize_csv(path: Path, roots: Iterable[Path]) -> tuple[tuple[str, ...], tuple[tuple[str, ...], ...]]:
    with path.open(newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        fields = [f for f in (reader.fieldnames or []) if not any(part in f.lower() for part in DROP_KEY_PARTS)]
        rows = []
        for row in reader:
            cooked = []
            for field in fields:
                value: Any = row.get(field, "")
                for root in roots:
                    value = str(value).replace(str(root.resolve()), "<ROOT>")
                cooked.append(str(value))
            rows.append(tuple(cooked))
    return tuple(fields), tuple(rows)


def compare_structured_dirs(retained: Path, regenerated: Path) -> dict[str, int]:
    retained_files = {p.relative_to(retained) for p in retained.rglob("*") if p.is_file()}
    regenerated_files = {p.relative_to(regenerated) for p in regenerated.rglob("*") if p.is_file()}
    # Logs and explicit timing summaries are evidence but not deterministic outputs.
    def deterministic(paths: set[Path]) -> set[Path]:
        return {p for p in paths if p.suffix not in {".log"} and "timing" not in p.name.lower()}
    rset, gset = deterministic(retained_files), deterministic(regenerated_files)
    if rset != gset:
        raise AssertionError({"retained_only": sorted(map(str, rset-gset)), "regenerated_only": sorted(map(str, gset-rset))})
    checked = 0
    for rel in sorted(rset):
        left, right = retained / rel, regenerated / rel
        if rel.suffix == ".json":
            a = normalize(json.loads(left.read_text(encoding="utf-8")), [retained, regenerated, ROOT])
            b = normalize(json.loads(right.read_text(encoding="utf-8")), [retained, regenerated, ROOT])
            if a != b:
                raise AssertionError(f"normalized JSON mismatch: {rel}")
        elif rel.suffix == ".csv":
            if normalize_csv(left, [retained, regenerated, ROOT]) != normalize_csv(right, [retained, regenerated, ROOT]):
                raise AssertionError(f"normalized CSV mismatch: {rel}")
        else:
            if left.read_bytes() != right.read_bytes():
                raise AssertionError(f"deterministic file mismatch: {rel}")
        checked += 1
    return {"files": checked}


def compare_certificate_dirs(retained: Path, regenerated: Path, expected: int) -> dict[str, int]:
    left = {p.name: p for p in retained.glob("*.json")}
    right = {p.name: p for p in regenerated.glob("*.json")}
    if len(left) != expected or left.keys() != right.keys():
        raise AssertionError(f"certificate inventory mismatch: {len(left)} retained, {len(right)} regenerated")
    for name in sorted(left):
        if left[name].read_bytes() != right[name].read_bytes():
            raise AssertionError(f"certificate bytes differ: {name}")
    return {"certificates": len(left)}


def status_from_certificate(obj: Any) -> bool:
    if not isinstance(obj, dict):
        raise AssertionError("certificate is not a JSON object")
    preferred = ["feasible", "covered", "coverage", "success"]
    for key in preferred:
        if key in obj and isinstance(obj[key], bool):
            return obj[key]
    for key in ("status", "result", "verdict"):
        if key in obj and isinstance(obj[key], str):
            value = obj[key].strip().lower().replace("_", "-")
            if value in {"feasible", "covered", "covering", "passed", "success", "sat", "satisfiable"}:
                return True
            if value in {"infeasible", "uncovered", "impossible", "failed", "unsat", "unsatisfiable", "zero-loss-alias"}:
                return False
    # Producer certificates use a selected interface for feasible cases and a
    # complete-interface collision witness for impossible cases.
    if any(key in obj for key in ("selected_mask", "selected_taps", "interface")):
        for key in ("collision", "collision_witness", "full_interface_collision"):
            if obj.get(key):
                return False
        return True
    raise AssertionError(f"cannot infer certificate status from keys: {sorted(obj)}")


def count_statuses(directory: Path) -> dict[str, int]:
    feasible = infeasible = 0
    for path in sorted(directory.glob("*.json")):
        if status_from_certificate(json.loads(path.read_text(encoding="utf-8"))):
            feasible += 1
        else:
            infeasible += 1
    return {"feasible": feasible, "infeasible": infeasible, "total": feasible + infeasible}


def inventory_digest(root: Path) -> dict[str, Any]:
    records = []
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        rel = path.relative_to(root)
        if any(part == "__pycache__" for part in rel.parts) or path.suffix == ".pyc":
            continue
        records.append({"path": str(rel), "bytes": path.stat().st_size, "sha256": sha256(path)})
    digest = hashlib.sha256(
        "".join(f"{r['path']}\0{r['bytes']}\0{r['sha256']}\n" for r in records).encode()
    ).hexdigest()
    return {"files": len(records), "sha256": digest}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--iverilog", type=Path)
    args = parser.parse_args()
    out = args.out.resolve()
    if out == ROOT or ROOT in out.parents and out == ROOT.parent:
        raise SystemExit("refusing unsafe output directory")
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)
    started = time.perf_counter()

    # Stage 1: execute the established 432-case finite campaign and the first
    # public-RTL bridge in a clean copy configured with its retained 28-case
    # UART baseline. This preserves the already audited implementation path.
    with tempfile.TemporaryDirectory(prefix="coverage-certified-legacy-") as td:
        copy_root = Path(td) / "artifact"
        shutil.copytree(ROOT, copy_root, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
        shutil.copy2(copy_root / "models/uart-rtl-campaign.json", copy_root / "models/rtl-campaign.json")
        shutil.rmtree(copy_root / "results/rtl")
        shutil.copytree(copy_root / "results/uart-baseline", copy_root / "results/rtl")
        shutil.rmtree(copy_root / "certificates/rtl")
        shutil.copytree(copy_root / "certificates/uart-baseline", copy_root / "certificates/rtl")
        legacy_out = copy_root / "results/wrapper-legacy-reproduction"
        command = [sys.executable, str(copy_root / "reproduce_legacy.py"), "--out", str(legacy_out)]
        if args.iverilog:
            command.extend(["--iverilog", str(args.iverilog.resolve())])
        run(command, cwd=copy_root, stdout_path=out / "legacy-core.log")
        shutil.copytree(legacy_out, out / "legacy-core")

    # Stage 2: independently regenerate the complete 52-case, two-system RTL
    # campaign and compare all deterministic outputs and certificates.
    combined = out / "combined-rtl"
    regenerated_results = combined / "results"
    regenerated_certs = combined / "certificates"
    run([
        sys.executable, str(ROOT / "src/run_campaign.py"),
        "--campaign", str(ROOT / "models/rtl-campaign.json"),
        "--out", str(regenerated_results),
        "--cert-dir", str(regenerated_certs),
    ], stdout_path=combined / "run.log")
    result_compare = compare_structured_dirs(ROOT / "results/rtl", regenerated_results)
    certificate_compare = compare_certificate_dirs(ROOT / "certificates/rtl", regenerated_certs, 52)

    # Stage 3: consume the second RTL bridge independently, optionally
    # re-simulating its 27 traces from the pinned Verilog source.
    bridge_command = [
        sys.executable, str(ROOT / "src/check_arbiter_bridge.py"),
        "--root", str(ROOT), "--json-out", str(out / "arbiter-bridge.json")
    ]
    if args.iverilog:
        bridge_command.extend(["--iverilog", str(args.iverilog.resolve())])
    run(bridge_command, stdout_path=out / "arbiter-bridge.log")
    run([
        sys.executable, str(ROOT / "tests/test_arbiter_bridge.py"),
        "--root", str(ROOT), "--out", str(out / "arbiter-mutations.json")
    ], stdout_path=out / "arbiter-mutations.log")

    # Stage 4: execute the implementation-independent exhaustive oracle.
    run([
        sys.executable, str(ROOT / "tests/exhaustive_small.py"),
        "--out", str(out / "exhaustive-small.json")
    ], stdout_path=out / "exhaustive-small.log")

    bridge = json.loads((out / "arbiter-bridge.json").read_text(encoding="utf-8"))
    mutations = json.loads((out / "arbiter-mutations.json").read_text(encoding="utf-8"))
    oracle = json.loads((out / "exhaustive-small.json").read_text(encoding="utf-8"))
    rtl_status = count_statuses(ROOT / "certificates/rtl")
    # These values are predeclared consequences of the retained matrices; an
    # unexpected change is a scientific result, not something to hide.
    if rtl_status != {"feasible": 20, "infeasible": 32, "total": 52}:
        raise AssertionError(f"unexpected two-system RTL matrix: {rtl_status}")
    if bridge != {
        "status": "passed", "pinned_files": 2, "traces": 27,
        "raw_rows": 1296, "raw_scalar_observations": 15552,
        "campaign_cases": 24, "combined_cases": 52,
        "resimulated": bool(args.iverilog),
    }:
        raise AssertionError(f"unexpected bridge summary: {bridge}")
    if mutations.get("rejected") != 6 or oracle.get("status") != "passed":
        raise AssertionError("mutation or exhaustive-oracle stage failed")

    summary = {
        "schema": "coverage-certified-reproduction-v2",
        "status": "passed",
        "bounded_resources": {"worker_processes": 1, "required_cpu_only": True},
        "retained_matrix": {
            "finite_cases": 432,
            "public_rtl_cases": 52,
            "total_cases": 484,
            "public_rtl_feasible": rtl_status["feasible"],
            "public_rtl_infeasible": rtl_status["infeasible"],
        },
        "legacy_core": "passed",
        "combined_rtl_result_comparison": result_compare,
        "combined_rtl_certificate_comparison": certificate_compare,
        "arbiter_bridge": bridge,
        "arbiter_mutations_rejected": mutations["rejected"],
        "exhaustive_small": oracle,
        "artifact_inventory": inventory_digest(ROOT),
        "wall_seconds": time.perf_counter() - started,
    }
    (out / "summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
