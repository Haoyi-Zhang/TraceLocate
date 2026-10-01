#!/usr/bin/env python3
"""Temporary-fixture tests for fail-closed reproduction output handling."""
from __future__ import annotations

import argparse
import json
import tempfile
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from output_safety import UnsafeOutput, create_new_output, validate_new_output


def rejected(repo: Path, requested: Path | str) -> str:
    try:
        validate_new_output(repo, requested)
    except UnsafeOutput as exc:
        return str(exc)
    raise AssertionError(f"unsafe output accepted: {requested}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    records = []
    with tempfile.TemporaryDirectory(prefix="coverage-output-safety-") as td:
        base = Path(td)
        repo = base / "artifact"
        other = base / "other-project"
        repo.mkdir(); other.mkdir()
        (repo / "results/campaign").mkdir(parents=True)
        (repo / "results/campaign/sentinel.txt").write_text("retained\n")
        (other / "sentinel.txt").write_text("unrelated\n")

        unsafe = [
            (repo, "repository root"),
            (repo.parent, "repository parent"),
            (repo / "results/campaign", "retained results"),
            (other / "new-output", "unrelated project"),
            (repo / "reproductions", "dedicated parent itself"),
        ]
        for path, label in unsafe:
            records.append({"case": label, "rejected": True, "reason": rejected(repo, path)})

        existing = repo / "reproductions/existing"
        existing.mkdir(parents=True)
        records.append({"case": "existing output", "rejected": True,
                        "reason": rejected(repo, existing)})

        external = base / "external-target"
        external.mkdir()
        link = repo / "reproductions/link"
        link.symlink_to(external, target_is_directory=True)
        records.append({"case": "symlink escape", "rejected": True,
                        "reason": rejected(repo, link / "run")})

        valid = create_new_output(repo, Path("reproductions/run-a"))
        (valid / "result.txt").write_text("ok\n")
        assert valid == repo / "reproductions/run-a"
        assert (repo / "results/campaign/sentinel.txt").read_text() == "retained\n"
        assert (other / "sentinel.txt").read_text() == "unrelated\n"
        records.append({"case": "new dedicated output", "accepted": True})

    source = (ROOT / "_reproduce_core.py").read_text(encoding="utf-8")
    if "rmtree(" in source:
        raise AssertionError("reproducer must not recursively delete a caller-selected path")
    report = {
        "status": "passed",
        "unsafe_paths_rejected": sum(bool(r.get("rejected")) for r in records),
        "valid_paths_accepted": sum(bool(r.get("accepted")) for r in records),
        "records": records,
        "destructive_repository_command_executed": False,
    }
    text = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(text)
    print(text, end="")


if __name__ == "__main__":
    main()
