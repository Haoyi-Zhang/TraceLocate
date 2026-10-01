#!/usr/bin/env python3
"""Independent validation of the pinned UART capture-to-language bridge.

The checker is intentionally separate from ``import_traces.py``.  It binds each
packed bit position to the CSV column, testbench RTL expression, model tap name,
kind, and cost; verifies the fixed fault schedule and nominal-value inversions;
and then checks every retained trace row, imported transition-table cell, and
28-case campaign declaration.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
from pathlib import Path
from typing import Any

DEFAULT_ROOT = Path(__file__).resolve().parents[1]
HEADER = [
    "cycle", "txd", "tx_busy", "tx_fsm0", "tx_fsm1", "tx_bit0",
    "tx_bit1", "tx_data0", "rxd", "rx_valid", "rx_fsm0", "rx_fsm1",
    "rx_sample", "row",
]
TAP_BINDINGS = [
    {"index": 0, "column": "txd", "signal": "uart_txd", "name": "txd", "kind": "port", "cost": 1},
    {"index": 1, "column": "tx_busy", "signal": "uart_tx_busy", "name": "tx_busy", "kind": "port", "cost": 1},
    {"index": 2, "column": "tx_fsm0", "signal": "tx.fsm_state[0]", "name": "tx_fsm[0]", "kind": "internal", "cost": 2},
    {"index": 3, "column": "tx_fsm1", "signal": "tx.fsm_state[1]", "name": "tx_fsm[1]", "kind": "internal", "cost": 2},
    {"index": 4, "column": "tx_bit0", "signal": "tx.bit_counter[0]", "name": "tx_bit_count[0]", "kind": "internal", "cost": 2},
    {"index": 5, "column": "tx_bit1", "signal": "tx.bit_counter[1]", "name": "tx_bit_count[1]", "kind": "internal", "cost": 2},
    {"index": 6, "column": "tx_data0", "signal": "tx.data_to_send[0]", "name": "tx_payload_shift[0]", "kind": "internal", "cost": 3},
    {"index": 7, "column": "rxd", "signal": "uart_rxd", "name": "rxd", "kind": "interconnect", "cost": 1},
    {"index": 8, "column": "rx_valid", "signal": "uart_rx_valid", "name": "rx_valid", "kind": "port", "cost": 1},
    {"index": 9, "column": "rx_fsm0", "signal": "rx.fsm_state[0]", "name": "rx_fsm[0]", "kind": "internal", "cost": 2},
    {"index": 10, "column": "rx_fsm1", "signal": "rx.fsm_state[1]", "name": "rx_fsm[1]", "kind": "internal", "cost": 2},
    {"index": 11, "column": "rx_sample", "signal": "rx.bit_sample", "name": "rx_sample", "kind": "internal", "cost": 2},
]
EXPECTED_TAPS = [{"name": b["name"], "cost": b["cost"], "kind": b["kind"]} for b in TAP_BINDINGS]
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
FAULT_SPECS: dict[str, dict[str, Any]] = {
    "line_early": {"class": "serial_interconnect_transient", "kind": 1, "cycle": 7, "value": 1},
    "line_late": {"class": "serial_interconnect_transient", "kind": 1, "cycle": 17, "value": 1},
    "tx_state_idle": {"class": "tx_control_state_transient", "kind": 2, "cycle": 12, "value": 0},
    "tx_state_stop": {"class": "tx_control_state_transient", "kind": 2, "cycle": 17, "value": 3},
    "tx_data_early": {"class": "tx_payload_state_transient", "kind": 3, "cycle": 10, "invert": "tx_data0"},
    "tx_data_late": {"class": "tx_payload_state_transient", "kind": 3, "cycle": 17, "invert": "tx_data0"},
    "rx_state_idle": {"class": "rx_control_state_transient", "kind": 4, "cycle": 12, "value": 0},
    "rx_state_stop": {"class": "rx_control_state_transient", "kind": 4, "cycle": 17, "value": 3},
    "rx_sample_early": {"class": "rx_sample_state_transient", "kind": 5, "cycle": 12, "invert": "rx_sample"},
    "rx_sample_late": {"class": "rx_sample_state_transient", "kind": 5, "cycle": 17, "invert": "rx_sample"},
}
EXPECTED_TIMEBASE = {
    "testbench_timescale": "1ns/1ps",
    "testbench_half_period_ns": 5,
    "simulated_clock_hz": 100_000_000,
    "design_parameter_clk_hz": 4_000_000,
    "design_parameter_bit_rate": 1_000_000,
    "interpretation": (
        "cycle-normalized parameter configuration; absolute testbench time is "
        "not a 4 MHz clock or a 1 MHz physical line-rate measurement"
    ),
}


def need(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def git_blob(data: bytes) -> str:
    return hashlib.sha1(f"blob {len(data)}\0".encode() + data).hexdigest()


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def normalized_expr(value: str) -> str:
    return re.sub(r"\s+", "", value)


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


def check_testbench_binding(path: Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8")
    need("`timescale 1ns/1ps" in text, "testbench timescale")
    bit_rate = re.search(r"localparam\s+integer\s+BIT_RATE\s*=\s*([0-9_]+)\s*;", text)
    clk_hz = re.search(r"localparam\s+integer\s+CLK_HZ\s*=\s*([0-9_]+)\s*;", text)
    half = re.search(r"always\s*#\s*([0-9_]+)\s+clk\s*=\s*~clk\s*;", text)
    need(bit_rate is not None and clk_hz is not None and half is not None, "testbench timing declarations")
    need(int(bit_rate.group(1).replace("_", "")) == EXPECTED_TIMEBASE["design_parameter_bit_rate"], "BIT_RATE parameter")
    need(int(clk_hz.group(1).replace("_", "")) == EXPECTED_TIMEBASE["design_parameter_clk_hz"], "CLK_HZ parameter")
    need(int(half.group(1).replace("_", "")) == EXPECTED_TIMEBASE["testbench_half_period_ns"], "testbench half-period")

    header_match = re.search(r'\$fdisplay\s*\(\s*fd\s*,\s*"(cycle,[^"]*,row)"\s*\)\s*;', text)
    need(header_match is not None, "CSV header declaration")
    need(header_match.group(1).split(",") == HEADER, "CSV column order")

    row_match = re.search(r"\brow\s*=\s*\{(.*?)\}\s*;", text, flags=re.S)
    need(row_match is not None, "packed-row assignment")
    row_msb_to_lsb = [normalized_expr(x) for x in row_match.group(1).split(",")]
    row_lsb_to_msb = list(reversed(row_msb_to_lsb))

    calls = re.findall(r'\$fdisplay\s*\(\s*fd\s*,\s*"([^"]*)"\s*(?:,\s*(.*?))?\)\s*;', text, flags=re.S)
    data_calls = [(fmt, args) for fmt, args in calls if fmt.startswith("%0d,")]
    need(len(data_calls) == 1, "CSV data write declaration")
    data_args = [normalized_expr(x) for x in data_calls[0][1].split(",")]
    need(len(data_args) == 14 and data_args[0] == "c" and data_args[-1] == "row", "CSV data argument count/order")
    csv_signals = data_args[1:-1]

    expected_signals = [normalized_expr(b["signal"]) for b in TAP_BINDINGS]
    need(row_lsb_to_msb == expected_signals, "packed bit-to-RTL signal binding")
    need(csv_signals == expected_signals, "CSV column-to-RTL signal binding")
    return {
        "timescale": "1ns/1ps",
        "half_period_ns": int(half.group(1).replace("_", "")),
        "simulated_clock_hz": 100_000_000,
        "ordered_bindings": TAP_BINDINGS,
    }


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
        for binding in TAP_BINDINGS:
            column = binding["column"]
            need(record[column] in ("0", "1"), f"non-binary {column} {path}")
            bits.append(int(record[column]))
        packed = sum(bit << p for p, bit in enumerate(bits))
        need(int(record["row"]) == packed, f"row packing {path}:{cycle}")
        packed_rows.append(packed)
    return packed_rows, data


def expected_fault(spec: dict[str, Any], nominal: list[dict[str, str]]) -> dict[str, Any]:
    value = spec.get("value")
    if "invert" in spec:
        value = 1 - int(nominal[spec["cycle"]][spec["invert"]])
    return {
        "class": spec["class"],
        "kind": spec["kind"],
        "cycle": spec["cycle"],
        "value": value,
    }


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

    testbench = check_testbench_binding(bridge / "trace_tb.sv")
    manifest = json.loads((bridge / "trace_manifest.json").read_text())
    need(manifest["source"]["commit"] == "5fd2db850a41b65aa34f3a31c663fc8704c7abd8", "source commit")
    need(manifest["simulator"]["executable"] == "iverilog" and "13.0" in manifest["simulator"]["version"],
         "simulator identity")
    need(sha256(generated / "compile.log") == manifest["simulator"]["compile_log_sha256"],
         "compile log integrity")
    capture = manifest["capture"]
    rows = capture["rows"]
    need(rows == 48 and capture["deletion_unit"].startswith("one complete"), "capture contract")
    for key, value in EXPECTED_TIMEBASE.items():
        need(capture.get(key) == value, f"capture timebase {key}")
    contexts = manifest["contexts"]
    need([(c["name"], c["payload"]) for c in contexts] == [("payload-5", 5), ("payload-a", 10), ("payload-3", 3)], "contexts")
    variants = ["nominal"] + list(FAULT_SPECS)
    need(manifest["variant_order"] == variants, "variant order")
    need(set(manifest.get("resolved_faults", {})) == {c["name"] for c in contexts}, "resolved fault contexts")

    trace_rows: dict[str, dict[str, list[int]]] = {}
    raw_records: dict[str, dict[str, list[dict[str, str]]]] = {}
    resolved_expected: dict[str, dict[str, dict[str, Any]]] = {}
    for context in contexts:
        cname = context["name"]
        trace_rows[cname] = {}
        raw_records[cname] = {}
        resolved_expected[cname] = {}
        need(set(manifest["traces"][cname]) == set(variants), f"trace membership {cname}")
        # Read nominal first so derived fault values are bound to the declared cycle.
        nentry = manifest["traces"][cname]["nominal"]
        npath = bridge / nentry["file"]
        need(sha256(npath) == nentry["sha256"], f"trace hash {cname}/nominal")
        nrows, nominal = read_trace(npath, rows)
        trace_rows[cname]["nominal"] = nrows
        raw_records[cname]["nominal"] = nominal
        need((nentry["fault_kind"], nentry["fault_cycle"], nentry["fault_value"], nentry["fault_fired"], nentry["unknown_rows"]) == (0, -1, 0, 0, 0), f"nominal declaration {cname}")

        for variant, spec in FAULT_SPECS.items():
            expected = expected_fault(spec, nominal)
            resolved_expected[cname][variant] = expected
            entry = manifest["traces"][cname][variant]
            path = bridge / entry["file"]
            need(sha256(path) == entry["sha256"], f"trace hash {cname}/{variant}")
            rs, records = read_trace(path, rows)
            trace_rows[cname][variant] = rs
            raw_records[cname][variant] = records
            need(entry["unknown_rows"] == 0 and entry["fault_fired"] == 1, f"fault firing {cname}/{variant}")
            need((entry["fault_kind"], entry["fault_cycle"], entry["fault_value"]) ==
                 (expected["kind"], expected["cycle"], expected["value"]),
                 f"fixed fault schedule/value {cname}/{variant}")
            need(manifest["resolved_faults"][cname].get(variant) == expected,
                 f"resolved fault record {cname}/{variant}")
        need(manifest["resolved_faults"][cname] == resolved_expected[cname],
             f"resolved fault set {cname}")

    model = json.loads((root / "models/uart-loopback-rtl.json").read_text())
    need(model["name"] == "uart-loopback-rtl", "model identity")
    need(model.get("taps") == EXPECTED_TAPS, "ordered tap name/kind/cost binding")
    need(model.get("capture") == capture, "model capture metadata")
    need({c["name"]: c["variants"] for c in model["classes"]} == CLASS_VARIANTS, "model classes")
    need(len(model["contexts"]) == len(contexts), "model context count")
    for ci, context in enumerate(contexts):
        need(model["contexts"][ci]["name"] == context["name"] and model["contexts"][ci]["payload"] == context["payload"], f"model context identity {ci}")
        need(model["contexts"][ci]["inputs"] == [ci] * rows, f"context stimulus {ci}")
    for variant in variants:
        table = model["variants"][variant]["table"]
        need(len(table) == rows and model["variants"][variant]["initial"] == [0], f"variant table {variant}")
        for q, edges in enumerate(table):
            need(len(edges) == len(contexts), f"table alphabet {variant}/{q}")
            for ci, context in enumerate(contexts):
                need(edges[ci] == {"next": min(q + 1, rows - 1), "row": trace_rows[context["name"]][variant][q]},
                     f"model translation {variant}/{q}/{ci}")

    campaign = json.loads((root / "models/rtl-campaign.json").read_text())
    cases = campaign["cases"]
    context_sets = ([0], [1], [2], [0, 1, 2])
    expected_specs = {
        (h, d, (0,), tuple(ctx))
        for h in (16, 24, 32) for d in (0, 1) for ctx in context_sets
    } | {(24, 0, (0, 1), tuple(ctx)) for ctx in context_sets}
    actual_specs = {
        (c["spec"]["h"], c["spec"]["d"], tuple(c["spec"]["offsets"]), tuple(c["spec"]["contexts"]))
        for c in cases
    }
    need(campaign.get("name") == "public-rtl-uart-loopback", "campaign identity")
    need(campaign.get("source_manifest") == "rtl/ben-marshall-uart/trace_manifest.json", "campaign source manifest")
    need(len(cases) == len({c["id"] for c in cases}) == 28, "campaign identifiers")
    need(actual_specs == expected_specs, "campaign Cartesian product")
    need(all(c["model"] == model["name"] and c["spec"]["h"] + max(c["spec"]["offsets"]) <= rows for c in cases), "campaign bounds")

    report = {
        "status": "passed",
        "source_files_verified": len(EXPECTED_BLOBS),
        "compatibility_copies_verified": 2,
        "simulator_log_verified": 1,
        "tap_bindings_verified": len(TAP_BINDINGS),
        "tap_bindings": TAP_BINDINGS,
        "testbench_timebase": testbench,
        "testbench_timescale": capture["testbench_timescale"],
        "testbench_half_period_ns": capture["testbench_half_period_ns"],
        "simulated_clock_hz": capture["simulated_clock_hz"],
        "design_parameter_clk_hz": capture["design_parameter_clk_hz"],
        "design_parameter_bit_rate": capture["design_parameter_bit_rate"],
        "contexts": len(contexts),
        "fault_classes": len(CLASS_VARIANTS) - 1,
        "variants": len(variants),
        "raw_traces": len(contexts) * len(variants),
        "rows_per_trace": rows,
        "captured_rows": rows * len(contexts) * len(variants),
        "translated_table_cells": rows * len(contexts) * len(variants),
        "resolved_fault_records": len(contexts) * len(FAULT_SPECS),
        "campaign_cases": len(cases),
        "model_sha256": sha256(root / "models/uart-loopback-rtl.json"),
        "campaign_sha256": sha256(root / "models/rtl-campaign.json"),
        "interpretation": (
            "Exact retained RTL-simulation trace translation check under a cycle-normalized "
            "parameter configuration; not synthesis, place-and-route, silicon, line-rate, or "
            "electrical-fault validation."
        ),
    }
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    try:
        main()
    except (ValueError, KeyError, TypeError, OSError, IndexError) as exc:
        raise SystemExit("REJECT: " + str(exc))
