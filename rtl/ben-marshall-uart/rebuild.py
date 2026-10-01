#!/usr/bin/env python3
"""Compile the pinned UART RTL, regenerate all retained traces, and import them."""
from __future__ import annotations
import argparse, csv, hashlib, json, os, re, shutil, subprocess, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
GENERATED = ROOT / "generated"
TRACE_ROOT = ROOT / "traces"
ROWS = 48
CONTEXTS = [
    {"name": "payload-5", "payload": 5},
    {"name": "payload-a", "payload": 10},
    {"name": "payload-3", "payload": 3},
]
BASE_VARIANTS = [
    {"name": "line_early", "class": "serial_interconnect_transient", "kind": 1, "cycle": 7, "value": 1},
    {"name": "line_late", "class": "serial_interconnect_transient", "kind": 1, "cycle": 17, "value": 1},
    {"name": "tx_state_idle", "class": "tx_control_state_transient", "kind": 2, "cycle": 12, "value": 0},
    {"name": "tx_state_stop", "class": "tx_control_state_transient", "kind": 2, "cycle": 17, "value": 3},
    {"name": "tx_data_early", "class": "tx_payload_state_transient", "kind": 3, "cycle": 10, "derive": "invert_tx_data0"},
    {"name": "tx_data_late", "class": "tx_payload_state_transient", "kind": 3, "cycle": 17, "derive": "invert_tx_data0"},
    {"name": "rx_state_idle", "class": "rx_control_state_transient", "kind": 4, "cycle": 12, "value": 0},
    {"name": "rx_state_stop", "class": "rx_control_state_transient", "kind": 4, "cycle": 17, "value": 3},
    {"name": "rx_sample_early", "class": "rx_sample_state_transient", "kind": 5, "cycle": 12, "derive": "invert_rx_sample"},
    {"name": "rx_sample_late", "class": "rx_sample_state_transient", "kind": 5, "cycle": 17, "derive": "invert_rx_sample"},
]
RESULT_RE = re.compile(r"RESULT rows=(\d+) fired=(\d+) unknown=(\d+) rx_valid=(\d+) rx_data=(\d+)")


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def command_version(executable: Path) -> str:
    r = subprocess.run([str(executable), "-V"], text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=False)
    return r.stdout.strip()


def read_nominal(path: Path) -> list[dict[str, str]]:
    with path.open(newline="") as f:
        return list(csv.DictReader(f))


def run_trace(vvp: Path, image: Path, context: dict, variant: dict, target: Path) -> dict:
    target.parent.mkdir(parents=True, exist_ok=True)
    args = [
        str(vvp), str(image), f"+PAYLOAD={context['payload']}",
        f"+FAULT_KIND={variant['kind']}", f"+FAULT_CYCLE={variant['cycle']}",
        f"+FAULT_VALUE={variant['value']}", f"+ROWS={ROWS}", f"+TRACE={target}",
    ]
    r = subprocess.run(args, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=20, check=False)
    if r.returncode != 0:
        raise SystemExit(f"simulation failed ({variant['name']}, {context['name']}):\n{r.stdout}")
    matches = RESULT_RE.findall(r.stdout)
    if len(matches) != 1:
        raise SystemExit(f"missing/duplicate RESULT line: {r.stdout}")
    row_count, fired, unknown, valid_count, rx_data = map(int, matches[0])
    expected_fired = 0 if variant["kind"] == 0 else 1
    if (row_count, fired, unknown) != (ROWS, expected_fired, 0):
        raise SystemExit(f"trace contract failure: {context['name']}/{variant['name']}: {matches[0]}")
    return {
        "file": str(target.relative_to(ROOT)),
        "sha256": sha256(target),
        "bytes": target.stat().st_size,
        "fault_kind": variant["kind"],
        "fault_cycle": variant["cycle"],
        "fault_value": variant["value"],
        "fault_fired": fired,
        "unknown_rows": unknown,
        "rx_valid_count": valid_count,
        "rx_data_final": rx_data,
        "simulator_stdout": r.stdout.strip().splitlines()[0],
    }


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--iverilog", type=Path, help="path to the iverilog executable")
    p.add_argument("--keep-image", action="store_true")
    args = p.parse_args()
    if args.iverilog:
        iverilog = args.iverilog.resolve()
    else:
        found = shutil.which("iverilog")
        if not found:
            raise SystemExit("iverilog not found; pass --iverilog /path/to/iverilog")
        iverilog = Path(found).resolve()
    vvp = iverilog.with_name("vvp")
    if not iverilog.is_file() or not vvp.is_file():
        raise SystemExit("iverilog/vvp pair not found")

    subprocess.run([sys.executable, str(ROOT / "prepare_upstream.py")], check=True)
    GENERATED.mkdir(parents=True, exist_ok=True)
    image = GENERATED / "trace_tb.vvp"
    compile_cmd = [
        str(iverilog), "-g2012", "-s", "trace_tb", "-o", str(image),
        str(GENERATED / "uart_tx.v"), str(GENERATED / "uart_rx.v"), str(ROOT / "trace_tb.sv"),
    ]
    compiled = subprocess.run(compile_cmd, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=False)
    # Compiler diagnostics contain absolute source paths.  Normalize only that
    # repository prefix so the retained log and its digest are root-independent.
    compile_log = compiled.stdout.replace(str(ROOT.parent.parent), "${REPO}")
    (GENERATED / "compile.log").write_text(compile_log)
    if compiled.returncode != 0:
        raise SystemExit("RTL compilation failed; see generated/compile.log")

    if TRACE_ROOT.exists():
        shutil.rmtree(TRACE_ROOT)
    TRACE_ROOT.mkdir()
    traces: dict[str, dict[str, dict]] = {}
    variant_order = ["nominal"] + [v["name"] for v in BASE_VARIANTS]
    resolved_faults: dict[str, dict[str, dict]] = {}
    for context in CONTEXTS:
        cname = context["name"]
        traces[cname] = {}
        resolved_faults[cname] = {}
        nominal = {"name": "nominal", "class": "nominal", "kind": 0, "cycle": -1, "value": 0}
        npath = TRACE_ROOT / cname / "nominal.csv"
        traces[cname]["nominal"] = run_trace(vvp, image, context, nominal, npath)
        nominal_rows = read_nominal(npath)
        for base in BASE_VARIANTS:
            variant = dict(base)
            if variant.get("derive") == "invert_tx_data0":
                variant["value"] = 1 - int(nominal_rows[variant["cycle"]]["tx_data0"])
            elif variant.get("derive") == "invert_rx_sample":
                variant["value"] = 1 - int(nominal_rows[variant["cycle"]]["rx_sample"])
            variant.pop("derive", None)
            path = TRACE_ROOT / cname / (variant["name"] + ".csv")
            traces[cname][variant["name"]] = run_trace(vvp, image, context, variant, path)
            resolved_faults[cname][variant["name"]] = {
                k: variant[k] for k in ("class", "kind", "cycle", "value")
            }

    upstream = json.loads((ROOT / "upstream/SOURCE.json").read_text())
    manifest = {
        "schema": 1,
        "source": {
            "repository": upstream["repository"],
            "commit": upstream["commit"],
            "license": upstream["license"],
            "upstream_manifest": "rtl/ben-marshall-uart/upstream/SOURCE.json",
            "compatibility_manifest": "rtl/ben-marshall-uart/generated/manifest.json",
        },
        "simulator": {
            "executable": iverilog.name,
            "version": command_version(iverilog),
            "compile_command": [Path(x).name if x in (str(iverilog), str(vvp)) else x.replace(str(ROOT.parent.parent), "${REPO}") for x in compile_cmd],
            "compile_log_sha256": sha256(GENERATED / "compile.log"),
        },
        "capture": {
            "rows": ROWS,
            "clock_edge": "posedge after a one-time-unit nonblocking-assignment settle",
            "deletion_unit": "one complete 12-tap synchronized row",
            "timestamps_in_model": False,
            "bit_order": "tap 0 is the least-significant bit of row",
            "testbench": "rtl/ben-marshall-uart/trace_tb.sv",
            "testbench_timescale": "1ns/1ps",
            "testbench_half_period_ns": 5,
            "simulated_clock_hz": 100_000_000,
            "design_parameter_clk_hz": 4_000_000,
            "design_parameter_bit_rate": 1_000_000,
            "interpretation": (
                "cycle-normalized parameter configuration; absolute testbench time is "
                "not a 4 MHz clock or a 1 MHz physical line-rate measurement"
            ),
        },
        "contexts": CONTEXTS,
        "variant_order": variant_order,
        "resolved_faults": resolved_faults,
        "traces": traces,
    }
    (ROOT / "trace_manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    subprocess.run([sys.executable, str(ROOT / "import_traces.py")], check=True)
    if not args.keep_image:
        image.unlink(missing_ok=True)
    print(json.dumps({
        "status": "passed",
        "contexts": len(CONTEXTS),
        "variants": len(variant_order),
        "traces": len(CONTEXTS) * len(variant_order),
        "rows": ROWS * len(CONTEXTS) * len(variant_order),
        "manifest_sha256": sha256(ROOT / "trace_manifest.json"),
    }, indent=2))


if __name__ == "__main__":
    main()
