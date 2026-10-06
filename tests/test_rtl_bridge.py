"""Obligation-directed corruptions for the public-RTL capture bridge.

The test invokes the independent bridge checker against isolated copies.  It
therefore exercises source pinning, compatibility-rewrite integrity, trace
hashing, fault metadata, table translation, and campaign membership rather
than merely parsing the retained files.
"""
from __future__ import annotations
import argparse, json, os, shutil, subprocess, sys, tempfile
from contextlib import nullcontext
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CHECKER = ROOT / "src/check_rtl_bridge.py"


def copy_fixture(target: Path) -> None:
    (target / "rtl").mkdir(parents=True)
    shutil.copytree(ROOT / "rtl/ben-marshall-uart", target / "rtl/ben-marshall-uart")
    (target / "models").mkdir()
    for name in ("uart-loopback-rtl.json", "rtl-campaign.json"):
        shutil.copy2(ROOT / "models" / name, target / "models" / name)


def invoke(root: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-B", str(CHECKER), "--root", str(root), "--out", str(root / "check.json")],
        text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=20, check=False,
        env={**os.environ, "PYTHONUTF8": "1", "PYTHONDONTWRITEBYTECODE": "1"},
    )


def mutate_source(root: Path) -> None:
    path = root / "rtl/ben-marshall-uart/upstream/uart_tx.v"
    data = bytearray(path.read_bytes()); data[32] ^= 1; path.write_bytes(data)


def mutate_compatibility(root: Path) -> None:
    path = root / "rtl/ben-marshall-uart/generated/uart_rx.v"
    path.write_text(path.read_text() + "\n")


def mutate_trace(root: Path) -> None:
    path = root / "rtl/ben-marshall-uart/traces/payload-5/line_early.csv"
    data = bytearray(path.read_bytes()); data[-2] = ord('1') if data[-2] != ord('1') else ord('0'); path.write_bytes(data)


def mutate_fault_metadata(root: Path) -> None:
    path = root / "rtl/ben-marshall-uart/trace_manifest.json"
    data = json.loads(path.read_text())
    data["traces"]["payload-5"]["line_early"]["fault_value"] = 0
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n")


def mutate_model_cell(root: Path) -> None:
    path = root / "models/uart-loopback-rtl.json"
    data = json.loads(path.read_text())
    data["variants"]["line_early"]["table"][7][0]["row"] ^= 1
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n")


def mutate_campaign(root: Path) -> None:
    path = root / "models/rtl-campaign.json"
    data = json.loads(path.read_text()); data["cases"].pop()
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n")


def mutate_renamed_case(root: Path) -> None:
    path = root / "models/rtl-campaign.json"
    data = json.loads(path.read_text())
    data["cases"][0]["id"] = "renamed-owned-case"
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n")


def mutate_exchanged_case_ids(root: Path) -> None:
    path = root / "models/rtl-campaign.json"
    data = json.loads(path.read_text())
    data["cases"][0]["id"], data["cases"][1]["id"] = (
        data["cases"][1]["id"], data["cases"][0]["id"])
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n")



def mutate_equal_cost_tap_names(root: Path) -> None:
    """Swap only the equal-cost tx_busy/rxd names; all rows/hashes stay fixed."""
    path = root / "models/uart-loopback-rtl.json"
    data = json.loads(path.read_text())
    data["taps"][1]["name"], data["taps"][7]["name"] = (
        data["taps"][7]["name"], data["taps"][1]["name"]
    )
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n")


def mutate_derived_fault_cycle(root: Path) -> None:
    """Move payload-5/tx_data_early 10->11 without touching traces or hashes."""
    path = root / "rtl/ben-marshall-uart/trace_manifest.json"
    data = json.loads(path.read_text())
    data["traces"]["payload-5"]["tx_data_early"]["fault_cycle"] = 11
    data["resolved_faults"]["payload-5"]["tx_data_early"]["cycle"] = 11
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n")

def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("out", nargs="?", type=Path, default=ROOT / "results/rtl-bridge-mutations.json")
    p.add_argument("--fixtures", type=Path,
                   help="new directory in which to retain all passive mutation fixtures and outputs")
    args = p.parse_args()
    if args.fixtures:
        args.fixtures.mkdir(parents=True, exist_ok=False)
    def fixture(label: str):
        if args.fixtures:
            path = args.fixtures / label
            path.mkdir()
            return nullcontext(path)
        return tempfile.TemporaryDirectory(prefix="rtl-bridge-" + label + "-")
    def capture(root: Path, result: subprocess.CompletedProcess[str]) -> None:
        if args.fixtures:
            (root / "checker-output.txt").write_text(result.stdout, encoding="utf-8")
    mutations = [
        ("pinned upstream blob", mutate_source, "upstream integrity"),
        ("declaration-only compatibility copy", mutate_compatibility, "compatibility output"),
        ("retained trace digest", mutate_trace, "trace hash"),
        ("fault declaration", mutate_fault_metadata, "fixed fault schedule/value"),
        ("trace-to-table cell", mutate_model_cell, "model translation"),
        ("frozen campaign membership", mutate_campaign, "campaign identifiers"),
        ("renamed campaign case", mutate_renamed_case, "campaign identifier-to-spec binding"),
        ("exchanged campaign case identifiers", mutate_exchanged_case_ids,
         "campaign identifier-to-spec binding"),
        ("equal-cost tx_busy/rxd tap-name swap", mutate_equal_cost_tap_names,
         "ordered tap name/kind/cost binding"),
        ("payload-5 tx_data_early cycle 10-to-11", mutate_derived_fault_cycle,
         "fixed fault schedule/value"),
    ]
    records = []
    with fixture("positive") as td:
        root = Path(td); copy_fixture(root); result = invoke(root)
        capture(root, result)
        if result.returncode != 0:
            raise AssertionError("valid bridge rejected: " + result.stdout)
    for index, (label, mutation, expected) in enumerate(mutations):
        with fixture(f"mutation-{index}") as td:
            root = Path(td); copy_fixture(root); mutation(root); result = invoke(root)
            capture(root, result)
            text = result.stdout.strip()
            if result.returncode == 0:
                raise AssertionError("invalid bridge accepted: " + label)
            if expected not in text:
                raise AssertionError(f"unexpected rejection for {label}: {text}")
            records.append({"mutation": label, "rejected": True, "reason": text.splitlines()[-1]})
    report = {
        "status": "passed", "valid_fixture_accepted": True,
        "mutations_rejected": len(records), "mutations": records,
        "interpretation": "Targeted translation-integrity tests; not proof that the RTL fault classes model physical defects.",
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
