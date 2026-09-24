"""Independent validation of the pinned public-RTL capture-to-language bridge."""
from __future__ import annotations
import argparse, csv, hashlib, json, re
from pathlib import Path

DEFAULT_ROOT = Path(__file__).resolve().parents[1]
HEADER = [
    "cycle", "txd", "tx_busy", "tx_fsm0", "tx_fsm1", "tx_bit0",
    "tx_bit1", "tx_data0", "rxd", "rx_valid", "rx_fsm0", "rx_fsm1",
    "rx_sample", "row",
]
TAP_COLUMNS = HEADER[1:13]
EXPECTED_BLOBS = {
    "uart_tx.v": (5268, "89906d6c5059a592dd086bbf60997368375cd1bb"),
    "uart_rx.v": (5718, "1cb2eadcb544f57864b29d380e893f92fac5f38c"),
    "LICENSE": (1069, "22b2e46c610d85f568e402c0c556821676d55253"),
}
CLASS_VARIANTS = {
    "nominal": ["nominal"],
    "serial_interconnect_transient": ["line_early", "line_late"],
    "tx_control_state_transient": ["tx_state_idle", "tx_state_stop"],
    "tx_payload_state_transient": ["tx_data_early", "tx_data_late"],
    "rx_control_state_transient": ["rx_state_idle", "rx_state_stop"],
    "rx_sample_state_transient": ["rx_sample_early", "rx_sample_late"],
}
FIXED = {
    "line_early": (1, 7, 1), "line_late": (1, 17, 1),
    "tx_state_idle": (2, 12, 0), "tx_state_stop": (2, 17, 3),
    "rx_state_idle": (4, 12, 0), "rx_state_stop": (4, 17, 3),
}


def need(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def git_blob(data: bytes) -> str:
    return hashlib.sha1(f"blob {len(data)}\0".encode() + data).hexdigest()


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def expected_compat(text: str, module: str) -> str:
    marker = f"module {module}("
    need(text.count(marker) == 1, f"module declaration {module}")
    text = text.replace(marker, (
        f"module {module} #(\n"
        "parameter   BIT_RATE        = 9600,\n"
        "parameter   CLK_HZ          = 50_000_000,\n"
        "parameter   PAYLOAD_BITS    = 8,\n"
        "parameter   STOP_BITS       = 1\n"
        ")("), 1)
    pats = [
        r"parameter\s+BIT_RATE\s*=\s*9600;\s*// bits / sec\n",
        r"parameter\s+CLK_HZ\s*=\s*50_000_000;\n",
        r"parameter\s+PAYLOAD_BITS\s*=\s*8;\n",
        r"parameter\s+STOP_BITS\s*=\s*1;\n",
    ]
    for pat in pats:
        text, n = re.subn(pat, "", text, count=1)
        need(n == 1, f"compatibility declaration {module}/{pat}")
    return text


def read_trace(path: Path, rows: int) -> tuple[list[int], list[dict[str, str]]]:
    with path.open(newline="") as f:
        reader = csv.DictReader(f)
        need(reader.fieldnames == HEADER, f"header {path}")
        data = list(reader)
    need(len(data) == rows, f"trace length {path}")
    packed_rows = []
    for cycle, record in enumerate(data):
        need(int(record["cycle"]) == cycle, f"cycle order {path}")
        bits = []
        for column in TAP_COLUMNS:
            need(record[column] in ("0", "1"), f"non-binary {column} {path}")
            bits.append(int(record[column]))
        packed = sum(bit << p for p, bit in enumerate(bits))
        need(int(record["row"]) == packed, f"row packing {path}:{cycle}")
        packed_rows.append(packed)
    return packed_rows, data


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--root", type=Path, default=DEFAULT_ROOT,
                   help="standalone artifact root (supports isolated mutation tests)")
    p.add_argument("--out", type=Path, default=None)
    args = p.parse_args()
    root = args.root.resolve()
    bridge = root / "rtl/ben-marshall-uart"
    out = args.out or (root / "results/rtl-bridge-check.json")

    upstream = bridge / "upstream"
    generated = bridge / "generated"
    for name, (size, blob) in EXPECTED_BLOBS.items():
        data = (upstream / name).read_bytes()
        need(len(data) == size and git_blob(data) == blob, f"upstream integrity {name}")
    for name, module in (("uart_tx.v", "uart_tx"), ("uart_rx.v", "uart_rx")):
        need((generated / name).read_text() == expected_compat((upstream / name).read_text(), module),
             f"compatibility output {name}")

    manifest = json.loads((bridge / "trace_manifest.json").read_text())
    need(manifest["source"]["commit"] == "5fd2db850a41b65aa34f3a31c663fc8704c7abd8", "source commit")
    need(manifest["simulator"]["executable"] == "iverilog" and "13.0" in manifest["simulator"]["version"],
         "simulator identity")
    need(sha256(generated / "compile.log") == manifest["simulator"]["compile_log_sha256"],
         "compile log integrity")
    rows = manifest["capture"]["rows"]
    need(rows == 48 and manifest["capture"]["deletion_unit"].startswith("one complete"), "capture contract")
    contexts = manifest["contexts"]
    need([(c["name"], c["payload"]) for c in contexts] == [("payload-5",5),("payload-a",10),("payload-3",3)], "contexts")
    variants = ["nominal"] + [v for key in CLASS_VARIANTS if key != "nominal" for v in CLASS_VARIANTS[key]]
    need(manifest["variant_order"] == variants, "variant order")

    trace_rows: dict[str, dict[str, list[int]]] = {}
    raw_records: dict[str, dict[str, list[dict[str, str]]]] = {}
    for context in contexts:
        cname = context["name"]
        trace_rows[cname] = {}; raw_records[cname] = {}
        need(set(manifest["traces"][cname]) == set(variants), f"trace membership {cname}")
        for variant in variants:
            entry = manifest["traces"][cname][variant]
            path = bridge / entry["file"]
            need(sha256(path) == entry["sha256"], f"trace hash {cname}/{variant}")
            rs, records = read_trace(path, rows)
            trace_rows[cname][variant] = rs; raw_records[cname][variant] = records
            need(entry["unknown_rows"] == 0, f"unknown rows {cname}/{variant}")
            need(entry["fault_fired"] == (0 if variant == "nominal" else 1), f"fault firing {cname}/{variant}")
            if variant in FIXED:
                need((entry["fault_kind"], entry["fault_cycle"], entry["fault_value"]) == FIXED[variant],
                     f"fault declaration {cname}/{variant}")
        nominal = raw_records[cname]["nominal"]
        for variant, column, kind in (("tx_data_early","tx_data0",3),("tx_data_late","tx_data0",3),
                                      ("rx_sample_early","rx_sample",5),("rx_sample_late","rx_sample",5)):
            entry = manifest["traces"][cname][variant]
            need(entry["fault_kind"] == kind, f"derived fault kind {variant}")
            expected = 1 - int(nominal[entry["fault_cycle"]][column])
            need(entry["fault_value"] == expected, f"derived opposite value {cname}/{variant}")

    model = json.loads((root / "models/uart-loopback-rtl.json").read_text())
    need(model["name"] == "uart-loopback-rtl" and len(model["taps"]) == 12, "model identity/taps")
    need({c["name"]: c["variants"] for c in model["classes"]} == CLASS_VARIANTS, "model classes")
    need(len(model["contexts"]) == len(contexts), "model context count")
    for ci, context in enumerate(contexts):
        need(model["contexts"][ci]["inputs"] == [ci] * rows, f"context stimulus {ci}")
    for variant in variants:
        table = model["variants"][variant]["table"]
        need(len(table) == rows and model["variants"][variant]["initial"] == [0], f"variant table {variant}")
        for q, edges in enumerate(table):
            need(len(edges) == len(contexts), f"table alphabet {variant}/{q}")
            for ci, context in enumerate(contexts):
                need(edges[ci] == {"next": min(q+1, rows-1), "row": trace_rows[context["name"]][variant][q]},
                     f"model translation {variant}/{q}/{ci}")

    campaign = json.loads((root / "models/rtl-campaign.json").read_text())
    cases = campaign["cases"]
    context_sets = ([0], [1], [2], [0,1,2])
    expected_specs = {
        (h, d, (0,), tuple(ctx))
        for h in (16, 24, 32) for d in (0, 1) for ctx in context_sets
    } | {
        (24, 0, (0, 1), tuple(ctx)) for ctx in context_sets
    }
    actual_specs = {(c["spec"]["h"],c["spec"]["d"],tuple(c["spec"]["offsets"]),tuple(c["spec"]["contexts"])) for c in cases}
    need(len(cases) == len({c["id"] for c in cases}) == 28, "campaign identifiers")
    need(actual_specs == expected_specs, "campaign Cartesian product")
    need(all(c["model"] == model["name"] and c["spec"]["h"] + max(c["spec"]["offsets"]) <= rows for c in cases), "campaign bounds")

    report = {
        "status": "passed",
        "source_files_verified": len(EXPECTED_BLOBS),
        "compatibility_copies_verified": 2,
        "simulator_log_verified": 1,
        "contexts": len(contexts),
        "fault_classes": len(CLASS_VARIANTS) - 1,
        "variants": len(variants),
        "raw_traces": len(contexts) * len(variants),
        "rows_per_trace": rows,
        "captured_rows": rows * len(contexts) * len(variants),
        "translated_table_cells": rows * len(contexts) * len(variants),
        "campaign_cases": len(cases),
        "model_sha256": sha256(root / "models/uart-loopback-rtl.json"),
        "campaign_sha256": sha256(root / "models/rtl-campaign.json"),
        "interpretation": "Exact retained RTL-simulation trace translation check; not synthesis, place-and-route, silicon, or electrical-fault validation."
    }
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    try:
        main()
    except (ValueError, KeyError, TypeError, OSError) as exc:
        raise SystemExit("REJECT: " + str(exc))
