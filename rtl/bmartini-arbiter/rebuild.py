#!/usr/bin/env python3
"""Rebuild deterministic raw traces for the pinned bmartini arbiter RTL."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
ARTIFACT = HERE.parents[1]
UPSTREAM = HERE / "upstream"
GENERATED = HERE / "generated"
RAW = HERE / "raw"
SOURCE = UPSTREAM / "SOURCE.json"
TB = HERE / "trace_tb.sv"

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


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for block in iter(lambda: fh.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def git_blob_sha1(data: bytes) -> str:
    return hashlib.sha1(f"blob {len(data)}\0".encode() + data).hexdigest()


def verify_upstream() -> dict[str, Any]:
    source = json.loads(SOURCE.read_text(encoding="utf-8"))
    for name, record in source["files"].items():
        path = UPSTREAM / name
        data = path.read_bytes()
        if len(data) != record["bytes"]:
            raise RuntimeError(f"byte count mismatch for {name}")
        if hashlib.sha256(data).hexdigest() != record["sha256"]:
            raise RuntimeError(f"sha256 mismatch for {name}")
        if git_blob_sha1(data) != record["git_blob_sha1"]:
            raise RuntimeError(f"Git blob mismatch for {name}")
    return source


def find_vvp(iverilog: Path) -> Path:
    candidates = [iverilog.with_name("vvp"), Path(shutil.which("vvp") or "")]
    for candidate in candidates:
        if str(candidate) and candidate.is_file() and os.access(candidate, os.X_OK):
            return candidate
    raise RuntimeError("vvp not found next to iverilog or on PATH")


def count_rows(path: Path) -> int:
    with path.open(newline="", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    if len(rows) != 48:
        raise RuntimeError(f"expected 48 rows in {path}, got {len(rows)}")
    for idx, row in enumerate(rows):
        if int(row["cycle"]) != idx:
            raise RuntimeError(f"non-contiguous cycle at {path}:{idx}")
        bits = [row[name] for name in (
            "request0", "request1", "request2", "request3",
            "grant0", "grant1", "grant2", "grant3",
            "select0", "select1", "active", "token0")]
        if any(bit not in {"0", "1"} for bit in bits):
            raise RuntimeError(f"non-binary value at {path}:{idx}")
        packed = sum(int(bit) << pos for pos, bit in enumerate(bits))
        if row["row"].lower() != f"{packed:03x}":
            raise RuntimeError(f"packed row mismatch at {path}:{idx}")
    return len(rows)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--iverilog", type=Path, default=Path(shutil.which("iverilog") or ""))
    parser.add_argument("--skip-import", action="store_true")
    args = parser.parse_args()
    if not args.iverilog.is_file():
        raise SystemExit("provide --iverilog /path/to/iverilog")
    vvp = find_vvp(args.iverilog)
    source = verify_upstream()

    GENERATED.mkdir(parents=True, exist_ok=True)
    RAW.mkdir(parents=True, exist_ok=True)
    executable = GENERATED / "trace_tb.vvp"
    compile_cmd = [str(args.iverilog), "-g2012", "-Wall", "-o", str(executable), str(UPSTREAM / "arbiter.v"), str(TB)]
    proc = subprocess.run(compile_cmd, text=True, capture_output=True, check=False)
    (GENERATED / "compile.log").write_text(proc.stdout + proc.stderr, encoding="utf-8")
    if proc.returncode:
        raise RuntimeError(f"iverilog failed; see {GENERATED / 'compile.log'}")

    traces: list[dict[str, Any]] = []
    for context_id, context in enumerate(CONTEXTS):
        for variant_id, (variant, fault_class, fault_cycle) in enumerate(VARIANTS):
            out = RAW / f"{context}__{variant}.csv"
            run_cmd = [str(vvp), str(executable), f"+CONTEXT={context_id}", f"+VARIANT={variant_id}", f"+OUT={out}"]
            run = subprocess.run(run_cmd, text=True, capture_output=True, check=False)
            if run.returncode:
                raise RuntimeError(f"simulation failed for {context}/{variant}: {run.stdout}{run.stderr}")
            expected = 0 if variant_id == 0 else 1
            marker = f"FAULT_FIRED={expected}"
            if marker not in run.stdout or "ROWS=48" not in run.stdout:
                raise RuntimeError(f"bad simulator marker for {context}/{variant}: {run.stdout}")
            rows = count_rows(out)
            traces.append({
                "context": context,
                "context_id": context_id,
                "variant": variant,
                "variant_id": variant_id,
                "class": fault_class,
                "fault_cycle": fault_cycle,
                "fault_fired": expected,
                "rows": rows,
                "path": str(out.relative_to(HERE)),
                "sha256": sha256(out),
                "stdout": run.stdout.strip(),
            })

    manifest = {
        "schema": "coverage-certified-arbiter-traces-v1",
        "source": source,
        "compiler": {
            "path_basename": args.iverilog.name,
            "version": subprocess.run([str(args.iverilog), "-V"], text=True, capture_output=True, check=False).stdout.splitlines()[:2],
            "command": ["iverilog", "-g2012", "-Wall", "-o", "generated/trace_tb.vvp", "upstream/arbiter.v", "trace_tb.sv"],
            "testbench_sha256": sha256(TB),
        },
        "capture": {
            "rows_per_trace": 48,
            "tap_order": [
                "request0", "request1", "request2", "request3",
                "grant0", "grant1", "grant2", "grant3",
                "select0", "select1", "active", "token0"
            ],
            "contexts": CONTEXTS,
            "variant_order": [item[0] for item in VARIANTS],
        },
        "traces": traces,
    }
    (HERE / "trace_manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    if not args.skip_import:
        subprocess.run([os.fspath(Path(os.sys.executable)), os.fspath(HERE / "import_traces.py")], check=True)

    print(json.dumps({"status": "passed", "traces": len(traces), "rows": sum(t["rows"] for t in traces)}, sort_keys=True))


if __name__ == "__main__":
    main()
