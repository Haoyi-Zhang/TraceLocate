#!/usr/bin/env python3
"""Combine deterministic public-RTL campaign fragments."""
from __future__ import annotations
import argparse, json
from pathlib import Path


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    p.add_argument("--out", type=Path)
    args = p.parse_args()
    root = args.root.resolve()
    out = args.out or (root / "models" / "rtl-campaign.json")
    fragments = [root / "models" / "uart-rtl-campaign.json", root / "models" / "arbiter-rtl-campaign.json"]
    cases = []
    sources = []
    seen = set()
    for path in fragments:
        obj = json.loads(path.read_text(encoding="utf-8"))
        sources.append({"path": str(path.relative_to(root)), "name": obj["name"], "cases": len(obj["cases"])})
        for case in obj["cases"]:
            if case["id"] in seen:
                raise RuntimeError(f"duplicate case id: {case['id']}")
            seen.add(case["id"])
            cases.append(case)
    combined = {
        "name": "two-system-public-rtl-campaign",
        "description": "Exact finite-language coverage tasks imported from two unrelated pinned public Verilog systems.",
        "sources": sources,
        "cases": cases,
    }
    out.write_text(json.dumps(combined, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"status": "passed", "cases": len(cases), "sources": len(sources)}, sort_keys=True))

if __name__ == "__main__":
    main()
