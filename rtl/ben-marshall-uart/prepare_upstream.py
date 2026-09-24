#!/usr/bin/env python3
"""Verify pinned UART sources and generate declaration-order compatibility copies.

The upstream logic is left untouched. The only rewrite moves four existing
parameter declarations into the ANSI module parameter list because Icarus 13
requires PAYLOAD_BITS to be declared before it is used in an ANSI port width.
"""
from __future__ import annotations
import hashlib, json, re
from pathlib import Path

ROOT = Path(__file__).resolve().parent
UP = ROOT / "upstream"
OUT = ROOT / "generated"
META = json.loads((UP / "SOURCE.json").read_text())


def git_blob(data: bytes) -> str:
    return hashlib.sha1(f"blob {len(data)}\0".encode() + data).hexdigest()


def rewrite(name: str) -> dict[str, object]:
    path = UP / name
    data = path.read_bytes()
    key = "rtl/" + name
    expected = META["files"][key]
    if len(data) != expected["bytes"] or git_blob(data) != expected["blob"]:
        raise SystemExit(f"source integrity failure: {name}")
    text = data.decode()
    module = name.removesuffix(".v")
    marker = f"module {module}("
    if text.count(marker) != 1:
        raise SystemExit(f"unexpected module declaration: {name}")
    header = (
        f"module {module} #(\n"
        "parameter   BIT_RATE        = 9600,\n"
        "parameter   CLK_HZ          = 50_000_000,\n"
        "parameter   PAYLOAD_BITS    = 8,\n"
        "parameter   STOP_BITS       = 1\n"
        ")("
    )
    text = text.replace(marker, header, 1)
    patterns = [
        r"parameter\s+BIT_RATE\s*=\s*9600;\s*// bits / sec\n",
        r"parameter\s+CLK_HZ\s*=\s*50_000_000;\n",
        r"parameter\s+PAYLOAD_BITS\s*=\s*8;\n",
        r"parameter\s+STOP_BITS\s*=\s*1;\n",
    ]
    for pat in patterns:
        text, n = re.subn(pat, "", text, count=1)
        if n != 1:
            raise SystemExit(f"expected parameter declaration not found in {name}: {pat}")
    OUT.mkdir(parents=True, exist_ok=True)
    target = OUT / name
    target.write_text(text)
    return {
        "file": name,
        "upstream_bytes": len(data),
        "upstream_git_blob": git_blob(data),
        "generated_bytes": target.stat().st_size,
        "generated_sha256": hashlib.sha256(target.read_bytes()).hexdigest(),
        "rewrite": "move existing parameters to ANSI module parameter list only",
    }


def main() -> None:
    records = [rewrite("uart_tx.v"), rewrite("uart_rx.v")]
    (OUT / "manifest.json").write_text(json.dumps({
        "source_repository": META["repository"],
        "source_commit": META["commit"],
        "records": records,
    }, indent=2) + "\n")
    print(json.dumps(records, indent=2))


if __name__ == "__main__":
    main()
