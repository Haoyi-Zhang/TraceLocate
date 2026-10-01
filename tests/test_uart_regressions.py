#!/usr/bin/env python3
"""Focused regressions for the retained UART evidence.

The checks guard two reviewer-sensitive facts: the authoritative optimum for
``uart-h24-d0-o0-c0`` is mask 2176 (``rxd`` + ``rx_sample``), whereas the
same-cost-looking name/bit confusion mask 2050 (``tx_busy`` + ``rx_sample``)
leaves a full-length cross-class alias.  The script also records the fixed
fault cycles and re-derives the two nominal-inversion fault values.
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from check_certificate import validate
from trace_engine import languages, lcs_length, pairs

CASE_ID = "uart-h24-d0-o0-c0"
TRUE_MASK = 2176       # bits 7 (rxd) and 11 (rx_sample)
FALSE_MASK = 2050      # bits 1 (tx_busy) and 11 (rx_sample)
EXPECTED_CYCLES = {
    "tx_data_early": 10,
    "tx_data_late": 17,
    "rx_sample_early": 12,
    "rx_sample_late": 17,
}


def selected_names(model: dict, mask: int) -> list[str]:
    return [tap["name"] for bit, tap in enumerate(model["taps"]) if mask & (1 << bit)]


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="") as fh:
        return list(csv.DictReader(fh))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=ROOT / "results/uart-regressions.json")
    args = parser.parse_args()

    model = json.loads((ROOT / "models/uart-loopback-rtl.json").read_text())
    campaign = json.loads((ROOT / "models/rtl-campaign.json").read_text())
    matches = [case for case in campaign["cases"] if case["id"] == CASE_ID]
    if len(matches) != 1:
        raise AssertionError("authoritative UART case must resolve exactly once")
    spec = matches[0]["spec"]
    if spec != {"contexts": [0], "d": 0, "h": 24, "offsets": [0]}:
        raise AssertionError(f"unexpected authoritative spec: {spec}")

    result = json.loads((ROOT / "results/rtl-campaign/cases" / f"{CASE_ID}.json").read_text())
    certificate = json.loads((ROOT / "results/rtl-campaign/certificates" / f"{CASE_ID}.json").read_text())
    checked = validate(model, spec, certificate)
    if result["status"] != "feasible" or result["mask"] != TRUE_MASK or certificate["mask"] != TRUE_MASK:
        raise AssertionError("authoritative UART optimum is not mask 2176")
    if result["cost"] != 3 or checked["cost"] != 3:
        raise AssertionError("authoritative UART optimum cost is not three")
    if selected_names(model, TRUE_MASK) != ["rxd", "rx_sample"]:
        raise AssertionError("mask 2176 does not bind to rxd and rx_sample")
    if selected_names(model, FALSE_MASK) != ["tx_busy", "rx_sample"]:
        raise AssertionError("mask 2050 does not bind to tx_busy and rx_sample")

    ps = pairs(languages(model, spec))
    true_bad = []
    false_bad = []
    for pid, left, right in ps:
        true_lcs = lcs_length(left, right, TRUE_MASK)
        false_lcs = lcs_length(left, right, FALSE_MASK)
        if true_lcs >= spec["h"] - spec["d"]:
            true_bad.append({"pair": list(pid), "lcs": true_lcs})
        if false_lcs >= spec["h"] - spec["d"]:
            false_bad.append({"pair": list(pid), "lcs": false_lcs})
    if true_bad:
        raise AssertionError(f"mask 2176 unexpectedly aliases: {true_bad[:1]}")
    if not false_bad or false_bad[0]["lcs"] != 24:
        raise AssertionError("mask 2050 must retain a full-length cross-class alias")

    bridge = ROOT / "rtl/ben-marshall-uart"
    manifest = json.loads((bridge / "trace_manifest.json").read_text())
    nominal = read_csv(bridge / manifest["traces"]["payload-5"]["nominal"]["file"])
    fault_records = {}
    for variant, cycle in EXPECTED_CYCLES.items():
        entry = manifest["traces"]["payload-5"][variant]
        resolved = manifest["resolved_faults"]["payload-5"][variant]
        if entry["fault_cycle"] != cycle or resolved["cycle"] != cycle:
            raise AssertionError(f"fixed cycle mismatch for {variant}")
        column = "tx_data0" if variant.startswith("tx_data") else "rx_sample"
        expected_value = 1 - int(nominal[cycle][column])
        if entry["fault_value"] != expected_value or resolved["value"] != expected_value:
            raise AssertionError(f"nominal-inversion mismatch for {variant}")
        fault_records[variant] = {"cycle": cycle, "value": expected_value, "column": column}

    report = {
        "status": "passed",
        "case": CASE_ID,
        "pair_count": len(ps),
        "authoritative_mask": TRUE_MASK,
        "authoritative_taps": selected_names(model, TRUE_MASK),
        "authoritative_cost": result["cost"],
        "confusable_mask": FALSE_MASK,
        "confusable_taps": selected_names(model, FALSE_MASK),
        "confusable_cross_class_aliases": len(false_bad),
        "alias_witness": false_bad[0],
        "fixed_faults": fault_records,
        "interpretation": (
            "A bit/name-binding regression for the frozen payload-5, h=24, d=0 task; "
            "not evidence for unmeasured UART configurations or physical faults."
        ),
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
