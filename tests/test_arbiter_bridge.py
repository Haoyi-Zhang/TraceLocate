#!/usr/bin/env python3
"""Directed mutation tests for the independent arbiter bridge consumer."""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Callable

MUTATIONS: list[tuple[str, Callable[[Path], None]]] = []

def mutation(name: str):
    def register(fn: Callable[[Path], None]):
        MUTATIONS.append((name, fn)); return fn
    return register

@mutation("pinned-source-byte")
def mutate_source(root: Path) -> None:
    p = root / "rtl/bmartini-arbiter/upstream/arbiter.v"
    p.write_text(p.read_text().replace("look ahead", "look  ahead", 1))

@mutation("raw-trace-bit")
def mutate_raw(root: Path) -> None:
    p = root / "rtl/bmartini-arbiter/raw/rotating__nominal.csv"
    lines = p.read_text().splitlines()
    fields = lines[2].split(","); fields[1] = "1" if fields[1] == "0" else "0"; lines[2] = ",".join(fields)
    p.write_text("\n".join(lines) + "\n")

@mutation("fault-declaration")
def mutate_manifest(root: Path) -> None:
    p = root / "rtl/bmartini-arbiter/trace_manifest.json"
    x = json.loads(p.read_text()); x["traces"][1]["fault_fired"] = 0; p.write_text(json.dumps(x, indent=2, sort_keys=True)+"\n")

@mutation("imported-model-cell")
def mutate_model(root: Path) -> None:
    p = root / "models/arbiter-rtl.json"; x = json.loads(p.read_text())
    x["table"]["nominal"]["rotating"]["rows"][0] ^= 1
    p.write_text(json.dumps(x, indent=2, sort_keys=True)+"\n")

@mutation("arbiter-campaign-member")
def mutate_fragment(root: Path) -> None:
    p = root / "models/arbiter-rtl-campaign.json"; x = json.loads(p.read_text())
    x["cases"][0]["horizon"] += 1
    p.write_text(json.dumps(x, indent=2, sort_keys=True)+"\n")

@mutation("combined-campaign-member")
def mutate_combined(root: Path) -> None:
    p = root / "models/rtl-campaign.json"; x = json.loads(p.read_text())
    x["cases"] = [c for c in x["cases"] if c["id"] != "arbiter-all-h16-d0"]
    p.write_text(json.dumps(x, indent=2, sort_keys=True)+"\n")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    root = args.root.resolve()
    outcomes = []
    for name, apply in MUTATIONS:
        with tempfile.TemporaryDirectory(prefix=f"arbiter-mutation-{name}-") as td:
            copy = Path(td) / "artifact"
            shutil.copytree(root, copy, ignore=shutil.ignore_patterns("results", "certificates", "__pycache__", "*.pyc", "generated"))
            apply(copy)
            run = subprocess.run([sys.executable, str(copy / "src/check_arbiter_bridge.py"), "--root", str(copy)], capture_output=True, text=True)
            rejected = run.returncode != 0
            outcomes.append({"mutation": name, "rejected": rejected})
            if not rejected:
                raise AssertionError(f"checker accepted mutation: {name}")
    result = {"status": "passed", "mutations": outcomes, "rejected": sum(x["rejected"] for x in outcomes)}
    text = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True); args.out.write_text(text)
    print(text, end="")

if __name__ == "__main__":
    main()
