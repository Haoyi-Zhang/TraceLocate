#!/usr/bin/env python3
"""Translate retained UART RTL cycle traces into a finite table-language model."""
from __future__ import annotations
import argparse, csv, hashlib, json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
EXPECTED_HEADER = [
    "cycle", "txd", "tx_busy", "tx_fsm0", "tx_fsm1", "tx_bit0",
    "tx_bit1", "tx_data0", "rxd", "rx_valid", "rx_fsm0", "rx_fsm1",
    "rx_sample", "row",
]
TAPS = [
    {"name": "txd", "cost": 1, "kind": "port"},
    {"name": "tx_busy", "cost": 1, "kind": "port"},
    {"name": "tx_fsm[0]", "cost": 2, "kind": "internal"},
    {"name": "tx_fsm[1]", "cost": 2, "kind": "internal"},
    {"name": "tx_bit_count[0]", "cost": 2, "kind": "internal"},
    {"name": "tx_bit_count[1]", "cost": 2, "kind": "internal"},
    {"name": "tx_payload_shift[0]", "cost": 3, "kind": "internal"},
    {"name": "rxd", "cost": 1, "kind": "interconnect"},
    {"name": "rx_valid", "cost": 1, "kind": "port"},
    {"name": "rx_fsm[0]", "cost": 2, "kind": "internal"},
    {"name": "rx_fsm[1]", "cost": 2, "kind": "internal"},
    {"name": "rx_sample", "cost": 2, "kind": "internal"},
]
CLASS_VARIANTS = {
    "nominal": ["nominal"],
    "serial_interconnect_transient": ["line_early", "line_late"],
    "tx_control_state_transient": ["tx_state_idle", "tx_state_stop"],
    "tx_payload_state_transient": ["tx_data_early", "tx_data_late"],
    "rx_control_state_transient": ["rx_state_idle", "rx_state_stop"],
    "rx_sample_state_transient": ["rx_sample_early", "rx_sample_late"],
}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_trace(path: Path, rows: int) -> list[int]:
    with path.open(newline="") as f:
        reader = csv.DictReader(f)
        if reader.fieldnames != EXPECTED_HEADER:
            raise ValueError(f"unexpected trace header: {path}")
        data = list(reader)
    if len(data) != rows:
        raise ValueError(f"row count: {path}: {len(data)} != {rows}")
    words: list[int] = []
    tap_names = EXPECTED_HEADER[1:13]
    for expected_cycle, record in enumerate(data):
        if int(record["cycle"]) != expected_cycle:
            raise ValueError(f"cycle sequence: {path}")
        bits = []
        for name in tap_names:
            if record[name] not in ("0", "1"):
                raise ValueError(f"non-binary tap {name}: {path}")
            bits.append(int(record[name]))
        packed = sum(bit << p for p, bit in enumerate(bits))
        if int(record["row"]) != packed or not 0 <= packed < (1 << len(TAPS)):
            raise ValueError(f"packed row mismatch: {path}:{expected_cycle}")
        words.append(packed)
    return words


def build(trace_root: Path, manifest_path: Path) -> tuple[dict, dict, dict]:
    manifest = json.loads(manifest_path.read_text())
    rows = manifest["capture"]["rows"]
    contexts = manifest["contexts"]
    traces: dict[str, dict[str, list[int]]] = {}
    for context in contexts:
        cname = context["name"]
        traces[cname] = {}
        for variant in manifest["variant_order"]:
            entry = manifest["traces"][cname][variant]
            path = trace_root / entry["file"]
            if sha256(path) != entry["sha256"]:
                raise ValueError(f"trace digest mismatch: {path}")
            traces[cname][variant] = read_trace(path, rows)

    variant_tables = {}
    alpha = len(contexts)
    for variant in manifest["variant_order"]:
        table = []
        for q in range(rows):
            state_edges = []
            for ci, context in enumerate(contexts):
                state_edges.append({
                    "next": min(q + 1, rows - 1),
                    "row": traces[context["name"]][variant][q],
                })
            if len(state_edges) != alpha:
                raise AssertionError("alphabet construction")
            table.append(state_edges)
        variant_tables[variant] = {"initial": [0], "table": table}

    model = {
        "name": "uart-loopback-rtl",
        "description": "Pinned public UART TX/RX RTL loopback traces under one-cycle fault injections.",
        "source": manifest["source"],
        "capture": manifest["capture"],
        "taps": TAPS,
        "contexts": [
            {"name": c["name"], "payload": c["payload"], "inputs": [i] * rows}
            for i, c in enumerate(contexts)
        ],
        "classes": [
            {"name": name, "variants": variants}
            for name, variants in CLASS_VARIANTS.items()
        ],
        "variants": variant_tables,
    }

    # Freeze a bounded, discriminating matrix after a measured pilot.  The
    # 24 core cases cross three windows, two deletion budgets, and four context
    # scopes.  Four additional phase-offset controls at h=24,d=0 test whether
    # admitting the next start row changes the selected interface.
    cases = []
    context_sets = [[0], [1], [2], [0, 1, 2]]
    specs = [
        (h, d, [0], ctx)
        for h in (16, 24, 32)
        for d in (0, 1)
        for ctx in context_sets
    ] + [
        (24, 0, [0, 1], ctx)
        for ctx in context_sets
    ]
    for h, d, off, ctx in specs:
        label = "all" if len(ctx) > 1 else str(ctx[0])
        ident = f"uart-h{h}-d{d}-o{''.join(map(str, off))}-c{label}"
        cases.append({
            "id": ident,
            "model": model["name"],
            "spec": {"h": h, "d": d, "offsets": off, "contexts": ctx},
        })
    campaign = {
        "name": "public-rtl-uart-loopback",
        "source_manifest": str(manifest_path.relative_to(ROOT.parent.parent)),
        "cases": cases,
    }
    report = {
        "contexts": len(contexts),
        "variants": len(manifest["variant_order"]),
        "classes": len(CLASS_VARIANTS),
        "raw_traces": len(contexts) * len(manifest["variant_order"]),
        "rows_per_trace": rows,
        "captured_rows": rows * len(contexts) * len(manifest["variant_order"]),
        "candidate_taps": len(TAPS),
        "cases": len(cases),
        "maximum_h_plus_offset": max(c["spec"]["h"] + max(c["spec"]["offsets"]) for c in cases),
    }
    return model, campaign, report


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--trace-root", type=Path, default=ROOT)
    p.add_argument("--manifest", type=Path, default=ROOT / "trace_manifest.json")
    p.add_argument("--model", type=Path, default=ROOT.parent.parent / "models/uart-loopback-rtl.json")
    p.add_argument("--campaign", type=Path, default=ROOT.parent.parent / "models/rtl-campaign.json")
    p.add_argument("--report", type=Path, default=ROOT / "import_report.json")
    args = p.parse_args()
    model, campaign, report = build(args.trace_root, args.manifest)
    for path, obj in ((args.model, model), (args.campaign, campaign), (args.report, report)):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(obj, indent=2, sort_keys=True) + "\n")
    report.update(model_sha256=sha256(args.model), campaign_sha256=sha256(args.campaign))
    args.report.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
