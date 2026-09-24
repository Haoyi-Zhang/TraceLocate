#!/usr/bin/env python3
"""Import pinned arbiter RTL traces into the finite-language model format."""
from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
ARTIFACT = HERE.parents[1]
MANIFEST = HERE / "trace_manifest.json"
MODELS = ARTIFACT / "models"

TAPS = [
    {"name": "request0", "cost": 1}, {"name": "request1", "cost": 1},
    {"name": "request2", "cost": 1}, {"name": "request3", "cost": 1},
    {"name": "grant0", "cost": 1}, {"name": "grant1", "cost": 1},
    {"name": "grant2", "cost": 1}, {"name": "grant3", "cost": 1},
    {"name": "select0", "cost": 1}, {"name": "select1", "cost": 1},
    {"name": "active", "cost": 1}, {"name": "token0", "cost": 2},
]
CLASS_ORDER = [
    "nominal", "request-input transient", "token-state transient",
    "grant-register transient", "select-register transient",
]
WINDOWS = [16, 24, 32]


def read_trace(path: Path, tap_order: list[str]) -> list[int]:
    rows: list[int] = []
    with path.open(newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        for idx, row in enumerate(reader):
            if int(row["cycle"]) != idx:
                raise RuntimeError(f"bad cycle order in {path}")
            packed = sum(int(row[tap]) << pos for pos, tap in enumerate(tap_order))
            if row["row"].lower() != f"{packed:03x}":
                raise RuntimeError(f"row packing mismatch in {path}:{idx}")
            rows.append(packed)
    if len(rows) != 48:
        raise RuntimeError(f"bad row count in {path}")
    return rows


def main() -> None:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    tap_order = manifest["capture"]["tap_order"]
    traces = manifest["traces"]
    contexts = manifest["capture"]["contexts"]
    variants = manifest["capture"]["variant_order"]

    table: dict[str, dict[str, dict[str, Any]]] = {}
    by_variant_class: dict[str, str] = {}
    for entry in traces:
        rows = read_trace(HERE / entry["path"], tap_order)
        table.setdefault(entry["variant"], {})[entry["context"]] = {
            "next": entry["variant"],
            "rows": rows,
        }
        by_variant_class[entry["variant"]] = entry["class"]

    classes = []
    for class_name in CLASS_ORDER:
        members = [v for v in variants if by_variant_class[v] == class_name]
        classes.append({"name": class_name, "variants": members})

    model = {
        "name": "pinned-bmartini-arbiter-rtl",
        "description": "Finite synchronous row language imported from a pinned four-port Verilog arbiter at commit 782bf8f34244cc6a3f279f2dbac8b5bf3f044132.",
        "source_manifest": "rtl/bmartini-arbiter/trace_manifest.json",
        "taps": TAPS,
        "contexts": contexts,
        "variants": [{"name": v, "initial": v} for v in variants],
        "classes": classes,
        "table": table,
    }

    cases = []
    for horizon in WINDOWS:
        for loss in (0, 1):
            cases.append({
                "id": f"arbiter-all-h{horizon}-d{loss}",
                "model": "models/arbiter-rtl.json",
                "horizon": horizon,
                "loss": loss,
                "contexts": contexts,
                "classes": CLASS_ORDER,
                "note": "All three request contexts and all five declaration classes.",
            })
        for context in contexts:
            for loss in (0, 1):
                cases.append({
                    "id": f"arbiter-{context}-h{horizon}-d{loss}",
                    "model": "models/arbiter-rtl.json",
                    "horizon": horizon,
                    "loss": loss,
                    "contexts": [context],
                    "classes": CLASS_ORDER,
                    "note": "Context-restricted exact interface-selection control.",
                })

    campaign = {
        "name": "pinned-bmartini-arbiter-rtl-campaign",
        "description": "Exact coverage tasks over imported public arbiter RTL traces.",
        "cases": cases,
    }
    MODELS.mkdir(exist_ok=True)
    (MODELS / "arbiter-rtl.json").write_text(json.dumps(model, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (MODELS / "arbiter-rtl-campaign.json").write_text(json.dumps(campaign, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"model": model["name"], "cases": len(cases), "traces": len(traces)}, sort_keys=True))


if __name__ == "__main__":
    main()
