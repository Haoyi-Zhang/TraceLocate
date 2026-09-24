#!/usr/bin/env python3
"""Independent consumer for the pinned arbiter RTL-to-language bridge."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

TAP_ORDER = [
    "request0", "request1", "request2", "request3",
    "grant0", "grant1", "grant2", "grant3",
    "select0", "select1", "active", "token0",
]
CONTEXTS = ["rotating", "contention", "bursty"]
VARIANTS = [
    ("nominal", "nominal", None),
    ("request_early", "request-input transient", 8),
    ("request_late", "request-input transient", 22),
    ("token_early", "token-state transient", 8),
    ("token_late", "token-state transient", 22),
    ("grant_early", "grant-register transient", 8),
    ("grant_late", "grant-register transient", 22),
    ("select_early", "select-register transient", 8),
    ("select_late", "select-register transient", 22),
]
CLASSES = [
    "nominal", "request-input transient", "token-state transient",
    "grant-register transient", "select-register transient",
]
TAPS = [
    {"name": "request0", "cost": 1}, {"name": "request1", "cost": 1},
    {"name": "request2", "cost": 1}, {"name": "request3", "cost": 1},
    {"name": "grant0", "cost": 1}, {"name": "grant1", "cost": 1},
    {"name": "grant2", "cost": 1}, {"name": "grant3", "cost": 1},
    {"name": "select0", "cost": 1}, {"name": "select1", "cost": 1},
    {"name": "active", "cost": 1}, {"name": "token0", "cost": 2},
]


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def git_blob_sha1(data: bytes) -> str:
    return hashlib.sha1(f"blob {len(data)}\0".encode() + data).hexdigest()


def read_rows(path: Path) -> tuple[list[int], int]:
    packed_rows: list[int] = []
    with path.open(newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        if reader.fieldnames != ["cycle", *TAP_ORDER, "row"]:
            raise AssertionError(f"unexpected CSV header in {path}")
        for idx, row in enumerate(reader):
            if int(row["cycle"]) != idx:
                raise AssertionError(f"cycle discontinuity in {path}")
            bits = [row[tap] for tap in TAP_ORDER]
            if any(bit not in {"0", "1"} for bit in bits):
                raise AssertionError(f"non-binary observation in {path}:{idx}")
            packed = sum(int(bit) << pos for pos, bit in enumerate(bits))
            if row["row"].lower() != f"{packed:03x}":
                raise AssertionError(f"packed row mismatch in {path}:{idx}")
            packed_rows.append(packed)
    if len(packed_rows) != 48:
        raise AssertionError(f"wrong row count in {path}")
    return packed_rows, len(packed_rows)


def expected_campaign() -> dict[str, Any]:
    cases = []
    for horizon in (16, 24, 32):
        for loss in (0, 1):
            cases.append({
                "id": f"arbiter-all-h{horizon}-d{loss}",
                "model": "models/arbiter-rtl.json", "horizon": horizon,
                "loss": loss, "contexts": CONTEXTS, "classes": CLASSES,
                "note": "All three request contexts and all five declaration classes.",
            })
        for context in CONTEXTS:
            for loss in (0, 1):
                cases.append({
                    "id": f"arbiter-{context}-h{horizon}-d{loss}",
                    "model": "models/arbiter-rtl.json", "horizon": horizon,
                    "loss": loss, "contexts": [context], "classes": CLASSES,
                    "note": "Context-restricted exact interface-selection control.",
                })
    return {
        "name": "pinned-bmartini-arbiter-rtl-campaign",
        "description": "Exact coverage tasks over imported public arbiter RTL traces.",
        "cases": cases,
    }


def check(root: Path, iverilog: Path | None = None) -> dict[str, Any]:
    bridge = root / "rtl" / "bmartini-arbiter"
    upstream = bridge / "upstream"
    source = json.loads((upstream / "SOURCE.json").read_text(encoding="utf-8"))
    if source["commit"] != "782bf8f34244cc6a3f279f2dbac8b5bf3f044132":
        raise AssertionError("unexpected pinned commit")
    for name, record in source["files"].items():
        data = (upstream / name).read_bytes()
        if len(data) != record["bytes"] or sha256_bytes(data) != record["sha256"] or git_blob_sha1(data) != record["git_blob_sha1"]:
            raise AssertionError(f"pinned upstream file mismatch: {name}")

    manifest = json.loads((bridge / "trace_manifest.json").read_text(encoding="utf-8"))
    if manifest["schema"] != "coverage-certified-arbiter-traces-v1":
        raise AssertionError("unexpected manifest schema")
    capture = manifest["capture"]
    if capture["rows_per_trace"] != 48 or capture["tap_order"] != TAP_ORDER or capture["contexts"] != CONTEXTS:
        raise AssertionError("capture contract mismatch")
    if capture["variant_order"] != [v[0] for v in VARIANTS]:
        raise AssertionError("variant order mismatch")
    if len(manifest["traces"]) != len(CONTEXTS) * len(VARIANTS):
        raise AssertionError("trace manifest cardinality mismatch")

    expected_entries: dict[tuple[str, str], tuple[str, int | None, int]] = {}
    rows_by_variant: dict[str, dict[str, dict[str, Any]]] = {v[0]: {} for v in VARIANTS}
    for context in CONTEXTS:
        for variant, fault_class, fault_cycle in VARIANTS:
            expected_entries[(context, variant)] = (fault_class, fault_cycle, 0 if variant == "nominal" else 1)

    seen = set()
    raw_cells = 0
    for entry in manifest["traces"]:
        key = (entry["context"], entry["variant"])
        if key not in expected_entries or key in seen:
            raise AssertionError(f"unexpected or duplicate trace entry: {key}")
        seen.add(key)
        exp_class, exp_cycle, exp_fired = expected_entries[key]
        if entry["class"] != exp_class or entry["fault_cycle"] != exp_cycle or entry["fault_fired"] != exp_fired:
            raise AssertionError(f"fault declaration mismatch: {key}")
        path = bridge / entry["path"]
        data = path.read_bytes()
        if sha256_bytes(data) != entry["sha256"]:
            raise AssertionError(f"raw trace hash mismatch: {key}")
        rows, count = read_rows(path)
        if count != entry["rows"] or f"FAULT_FIRED={exp_fired}" not in entry["stdout"] or "ROWS=48" not in entry["stdout"]:
            raise AssertionError(f"simulator evidence mismatch: {key}")
        rows_by_variant[entry["variant"]][entry["context"]] = {"next": entry["variant"], "rows": rows}
        raw_cells += len(rows)
    if seen != set(expected_entries):
        raise AssertionError("missing trace entries")

    model = json.loads((root / "models" / "arbiter-rtl.json").read_text(encoding="utf-8"))
    expected_classes = []
    for class_name in CLASSES:
        expected_classes.append({"name": class_name, "variants": [v for v, c, _ in VARIANTS if c == class_name]})
    expected_model = {
        "name": "pinned-bmartini-arbiter-rtl",
        "description": "Finite synchronous row language imported from a pinned four-port Verilog arbiter at commit 782bf8f34244cc6a3f279f2dbac8b5bf3f044132.",
        "source_manifest": "rtl/bmartini-arbiter/trace_manifest.json",
        "taps": TAPS,
        "contexts": CONTEXTS,
        "variants": [{"name": v, "initial": v} for v, _, _ in VARIANTS],
        "classes": expected_classes,
        "table": rows_by_variant,
    }
    if model != expected_model:
        raise AssertionError("arbiter finite model is not the exact raw-trace import")

    campaign = json.loads((root / "models" / "arbiter-rtl-campaign.json").read_text(encoding="utf-8"))
    if campaign != expected_campaign():
        raise AssertionError("arbiter campaign mismatch")
    combined = json.loads((root / "models" / "rtl-campaign.json").read_text(encoding="utf-8"))
    combined_cases = {case["id"]: case for case in combined["cases"]}
    for case in campaign["cases"]:
        if combined_cases.get(case["id"]) != case:
            raise AssertionError(f"combined campaign omitted or altered {case['id']}")
    if len(combined["cases"]) != len({case["id"] for case in combined["cases"]}):
        raise AssertionError("duplicate combined campaign case ids")

    resimulated = False
    if iverilog is not None:
        if not iverilog.is_file():
            raise AssertionError(f"iverilog not found: {iverilog}")
        with tempfile.TemporaryDirectory(prefix="arbiter-resim-") as tmp_name:
            tmp = Path(tmp_name) / "bmartini-arbiter"
            shutil.copytree(bridge, tmp, ignore=shutil.ignore_patterns("generated", "raw", "trace_manifest.json", "__pycache__"))
            subprocess.run([sys.executable, str(tmp / "rebuild.py"), "--iverilog", str(iverilog), "--skip-import"], check=True, capture_output=True, text=True)
            regenerated = json.loads((tmp / "trace_manifest.json").read_text(encoding="utf-8"))
            retained_by_key = {(e["context"], e["variant"]): e for e in manifest["traces"]}
            for entry in regenerated["traces"]:
                key = (entry["context"], entry["variant"])
                if entry["sha256"] != retained_by_key[key]["sha256"]:
                    raise AssertionError(f"resimulated raw trace mismatch: {key}")
                if (tmp / entry["path"]).read_bytes() != (bridge / retained_by_key[key]["path"]).read_bytes():
                    raise AssertionError(f"resimulated bytes mismatch: {key}")
        resimulated = True

    return {
        "status": "passed",
        "pinned_files": len(source["files"]),
        "traces": len(manifest["traces"]),
        "raw_rows": raw_cells,
        "raw_scalar_observations": raw_cells * len(TAP_ORDER),
        "campaign_cases": len(campaign["cases"]),
        "combined_cases": len(combined["cases"]),
        "resimulated": resimulated,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--iverilog", type=Path)
    parser.add_argument("--json-out", type=Path)
    args = parser.parse_args()
    result = check(args.root.resolve(), args.iverilog.resolve() if args.iverilog else None)
    text = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.json_out:
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(text, encoding="utf-8")
    print(text, end="")


if __name__ == "__main__":
    main()
