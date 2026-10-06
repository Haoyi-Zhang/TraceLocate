#!/usr/bin/env python3
"""Fail-closed consistency gate for the supported 432+28 evidence scope.

The gate checks only the current project tree.  It does not certify scientific
novelty, physical validity, or publication acceptance; those remain human
review questions.  It fails on any source/result/PDF scope split.
"""
from __future__ import annotations

import argparse
import ast
import csv
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

EXPECTED_ROOT = {"README.md", "artifact", "paper"}
FORBIDDEN_DIRS = {".pytest_cache", "__pycache__", ".git"}
FORBIDDEN_SUFFIXES = {".pyc", ".pyo"}
UNSUPPORTED_PATH_PARTS = {"bmartini-arbiter", "picorv32"}


def load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def run(command: list[str], cwd: Path, timeout: int = 180) -> str:
    p = subprocess.run(command, cwd=cwd, text=True, stdout=subprocess.PIPE,
                       stderr=subprocess.STDOUT, timeout=timeout, check=False)
    if p.returncode:
        raise AssertionError(f"command failed ({p.returncode}): {' '.join(command)}\n{p.stdout[-6000:]}")
    return p.stdout


def citation_keys(tex: str) -> list[str]:
    keys: list[str] = []
    for match in re.finditer(r"\\cite\{([^}]*)\}", tex):
        keys.extend(x.strip() for x in match.group(1).split(",") if x.strip())
    return keys


def bib_keys(bib: str) -> list[str]:
    return re.findall(r"(?m)^\s*@\w+\s*\{\s*([^,]+),", bib)


def case_set(path: Path) -> set[str]:
    obj = load(path)
    cases = obj.get("cases", [])
    ids = [c["id"] for c in cases]
    if len(ids) != len(set(ids)):
        raise AssertionError(f"duplicate case id in {path}")
    return set(ids)


def require_case_tree(instance: Path, results: Path) -> None:
    expected = case_set(instance)
    for leaf in ("cases", "certificates"):
        actual = {p.stem for p in (results / leaf).glob("*.json")}
        if actual != expected:
            raise AssertionError({"path": str(results / leaf),
                                  "missing": sorted(expected - actual),
                                  "extra": sorted(actual - expected)})


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--pdf", type=Path)
    args = parser.parse_args()
    root = args.root.resolve(strict=True)
    paper = root / "paper"
    art = root / "artifact"
    errors: list[str] = []

    def need(cond: bool, message: str) -> None:
        if not cond:
            errors.append(message)

    need({p.name for p in root.iterdir()} == EXPECTED_ROOT,
         f"project root must contain exactly {sorted(EXPECTED_ROOT)}")
    need(paper.is_dir() and art.is_dir(), "missing paper/ or artifact/")

    # Packaging hygiene and Python syntax.
    for p in root.rglob("*"):
        rel = p.relative_to(root)
        if p.is_symlink():
            errors.append(f"symlink in package: {rel}")
        if p.is_dir() and p.name in FORBIDDEN_DIRS:
            errors.append(f"forbidden cache/VCS directory: {rel}")
        if p.is_file() and p.suffix in FORBIDDEN_SUFFIXES:
            errors.append(f"forbidden bytecode file: {rel}")
        if any(part.lower() in UNSUPPORTED_PATH_PARTS for part in rel.parts):
            errors.append(f"unsupported draft asset retained: {rel}")
        if p.is_file() and p.suffix == ".py":
            try:
                ast.parse(p.read_text(encoding="utf-8"), filename=str(p))
            except Exception as exc:
                errors.append(f"Python syntax error {rel}: {exc}")

    # Reproducer interface and destructive-delete guard.
    core = (art / "_reproduce_core.py").read_text(encoding="utf-8")
    need("rmtree(" not in core, "reproducer contains recursive deletion")
    need("--retained-only" in core and "--iverilog" in core,
         "reproducer lacks explicit full/retained-only modes")
    need((art / "src/output_safety.py").exists(), "missing output-safety implementation")
    need((art / "tests/test_output_safety.py").exists(), "missing output-safety tests")

    # Canonical campaigns and one-to-one result/certificate correspondence.
    try:
        finite_ids = case_set(art / "models/campaign.json")
        uart_ids = case_set(art / "models/rtl-campaign.json")
        need(len(finite_ids) == 432, f"finite campaign has {len(finite_ids)} cases")
        need(len(uart_ids) == 28, f"UART campaign has {len(uart_ids)} cases")
        need(all(x.startswith("uart-") for x in uart_ids), "canonical RTL campaign contains non-UART ids")
        require_case_tree(art / "models/campaign.json", art / "results/campaign")
        require_case_tree(art / "models/rtl-campaign.json", art / "results/rtl-campaign")
    except Exception as exc:
        errors.append(f"campaign/result correspondence: {exc}")

    expected_summaries = [
        (art / "results/summary/summary.json", {"cases":432,"feasible":85,"infeasible":347,"zero_loss_infeasible":327}),
        (art / "results/rtl-summary/summary.json", {"cases":28,"feasible":12,"infeasible":16,"zero_loss_infeasible":8}),
    ]
    for path, expected in expected_summaries:
        try:
            data = load(path)
            for key, value in expected.items():
                need(data.get(key) == value, f"{path.relative_to(root)} {key}: expected {value}, got {data.get(key)}")
        except Exception as exc:
            errors.append(f"summary {path}: {exc}")

    checks = [
        ("results/rtl-bridge-check.json", "status", "passed"),
        ("results/rtl-bridge-mutations.json", "status", "passed"),
        ("results/uart-regressions.json", "status", "passed"),
        ("results/exhaustive-small.json", "status", "passed"),
        ("results/independent_math_validation.json", "status", "pass"),
    ]
    for rel, key, expected in checks:
        path = art / rel
        try:
            need(load(path).get(key) == expected, f"{rel} is not {expected}")
        except Exception as exc:
            errors.append(f"cannot read {rel}: {exc}")
    try:
        bridge = load(art / "results/rtl-bridge-check.json")
        need(bridge.get("campaign_cases") == 28, "bridge checker campaign count is not 28")
        need(bridge.get("raw_traces") == 33, "bridge checker trace count is not 33")
        need(bridge.get("captured_rows") == 1584, "bridge checker row count is not 1,584")
        need(bridge.get("tap_bindings_verified") == 12, "bridge checker did not bind 12 taps")
        need(bridge.get("simulated_clock_hz") == 100_000_000, "bridge checker timebase is not 100 MHz")
        need(bridge.get("design_parameter_clk_hz") == 4_000_000, "UART CLK_HZ parameter mismatch")
        need(bridge.get("design_parameter_bit_rate") == 1_000_000, "UART BIT_RATE parameter mismatch")
        bridge_mut = load(art / "results/rtl-bridge-mutations.json")
        need(bridge_mut.get("mutations_rejected") == 10, "bridge mutation count is not 10")
        contract = load(art / "results/contract-tests.json")
        need(contract.get("result") == "all assertions passed", "certificate contract suite failed")
        need(len(contract.get("invalid_mutations", [])) == 24, "certificate mutation count is not 24")
        need(contract.get("multi_pair_mutation_baseline", {}).get("pairs") == 3,
             "multi-pair mutation baseline absent")
        reg = load(art / "results/uart-regressions.json")
        need(reg.get("authoritative_mask") == 2176, "UART authoritative mask is not 2176")
        need(reg.get("confusable_mask") == 2050, "UART confusable mask is not 2050")
        need(reg.get("confusable_cross_class_aliases", 0) > 0,
             "mask 2050 has no recorded cross-class alias")
    except Exception as exc:
        errors.append(f"bridge/mutation regression: {exc}")

    # Bibliography count, citation closure, reading ledger and identity audit.
    try:
        tex = (paper / "main.tex").read_text(encoding="utf-8")
        bib = (paper / "references.bib").read_text(encoding="utf-8")
        bk = bib_keys(bib); ck = citation_keys(tex)
        need(len(bk) >= 55, f"bibliography has only {len(bk)} entries")
        need(len(bk) == len(set(bk)), "duplicate BibTeX keys")
        need(set(ck) == set(bk),
             f"citation closure mismatch: missing={sorted(set(ck)-set(bk))}, unused={sorted(set(bk)-set(ck))}")
        with (art / "literature.csv").open(newline="", encoding="utf-8") as f:
            ledger = list(csv.DictReader(f))
        ledger_keys = [r["key"] for r in ledger]
        need(set(ledger_keys) == set(bk) and len(ledger_keys) == len(set(ledger_keys)),
             "literature.csv does not cover each BibTeX key exactly once")
        audit_path = art / "literature/bibliography-verification.json"
        need(audit_path.exists(), "missing bibliography identity audit")
        if audit_path.exists():
            audit = load(audit_path)
            need(audit.get("entries") == len(bk), "bibliography audit entry count mismatch")
            need(audit.get("stable_identity_records") == len(bk), "not all bibliography entries have stable identity records")
            need(not audit.get("unresolved"), "bibliography audit has unresolved entries")
    except Exception as exc:
        errors.append(f"bibliography audit: {exc}")

    # Manuscript source must not claim excluded experiments or stale totals.
    try:
        main_text = (paper / "main.tex").read_text(encoding="utf-8")
        forbidden = [r"PicoRV32", r"held[- ]out", r"out[- ]of[- ]sample",
                     r"two[- ]system", r"484\s+(?:case|task)", r"105\s+feasible",
                     r"379\s+infeasible"]
        for pat in forbidden:
            need(re.search(pat, main_text, re.I) is None, f"stale manuscript claim matches {pat}")
        need("generated/final-stats.tex" in main_text, "main.tex does not input generated final statistics")
        need((paper / "generated/final-stats.tex").exists(), "generated/final-stats.tex missing")
        need("\\Pico" not in (paper / "generated/reviewer_stats.tex").read_text(encoding="utf-8"),
             "stale Pico macros remain")
    except Exception as exc:
        errors.append(f"manuscript scope check: {exc}")

    # Compiled PDF and log.
    pdf = args.pdf.resolve() if args.pdf else (paper / "coverage-certified-post-silicon.pdf")
    need(pdf.exists(), "compiled PDF missing")
    if pdf.exists():
        try:
            info = run(["pdfinfo", str(pdf)], root, 60)
            match = re.search(r"^Pages:\s+(\d+)", info, re.M)
            need(match is not None, "cannot read PDF page count")
            if match:
                need(int(match.group(1)) <= 14, "paper exceeds 14 pages")
            text = run(["pdftotext", str(pdf), "-"], root, 60)
            normalized_text = " ".join(text.split())
            need("Coverage Certificates for Post-Silicon Trace Localization under Bounded Row Loss" in normalized_text,
                 "PDF title mismatch")
            need("PicoRV32" not in text, "PDF still contains PicoRV32")
            need("484 tasks" not in text and "484 cases" not in text, "PDF still contains stale 484 total")
        except Exception as exc:
            errors.append(f"PDF inspection: {exc}")
    log = paper / "main.log"
    if log.exists():
        log_text = log.read_text(encoding="utf-8", errors="ignore")
        for marker in ("LaTeX Error", "Citation `", "Reference `", "There were undefined references", "Overfull \\hbox", "Overfull \\vbox"):
            need(marker not in log_text, f"LaTeX log contains {marker}")
    else:
        errors.append("paper/main.log missing")

    if errors:
        print(json.dumps({"status":"fail", "errors":errors}, indent=2, sort_keys=True))
        raise SystemExit(1)
    report = {
        "status":"pass",
        "scope":{"finite_cases":432,"uart_cases":28,"total_cases":460},
        "certificate_mutations":24,
        "bridge_mutations":10,
        "bibliography_entries":len(bib_keys((paper / "references.bib").read_text(encoding="utf-8"))),
        "note":"Consistency/reproducibility gate only; not peer review or physical validation.",
    }
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
