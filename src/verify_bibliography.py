#!/usr/bin/env python3
"""Offline, fail-closed bibliography identity and citation-use audit.

This checker does not claim to re-query publisher registries during a clean
reproduction.  It checks the frozen bibliography repaired against publisher,
DOI-registry, DBLP, or pinned-source records; every scholarly item must carry a
unique DOI and the one software source must carry its immutable commit URL.
It also requires exact citation closure and one literature-ledger row per key.
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import unicodedata
from pathlib import Path

DOI_RE = re.compile(r"^10\.\d{4,9}/\S+$", re.I)
ENTRY_START = re.compile(r"(?m)^@(\w+)\s*\{\s*([^,]+),")


def normalize(value: str) -> str:
    value = value.replace("\\&", " and ").replace("~", " ")
    value = re.sub(r"\\[A-Za-z]+\*?(?:\[[^]]*\])?", " ", value)
    value = value.replace("{", "").replace("}", "").replace("\\", " ")
    value = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode().lower()
    return " ".join(re.sub(r"[^a-z0-9]+", " ", value).split())


def split_entries(text: str) -> list[tuple[str, str, str]]:
    matches = list(ENTRY_START.finditer(text))
    entries: list[tuple[str, str, str]] = []
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        entries.append((match.group(1).lower(), match.group(2).strip(), text[match.end():end]))
    return entries


def parse_fields(body: str) -> dict[str, str]:
    fields: dict[str, str] = {}
    i = 0
    n = len(body)
    while i < n:
        while i < n and (body[i].isspace() or body[i] in ",}"):
            i += 1
        start = i
        while i < n and (body[i].isalnum() or body[i] in "_-"):
            i += 1
        if i == start:
            i += 1
            continue
        name = body[start:i].lower()
        while i < n and body[i].isspace():
            i += 1
        if i >= n or body[i] != "=":
            continue
        i += 1
        while i < n and body[i].isspace():
            i += 1
        if i >= n:
            break
        if body[i] == "{":
            depth = 1
            i += 1
            start = i
            while i < n and depth:
                if body[i] == "{":
                    depth += 1
                elif body[i] == "}":
                    depth -= 1
                    if depth == 0:
                        break
                i += 1
            value = body[start:i]
            i += 1
        elif body[i] == '"':
            i += 1
            start = i
            escaped = False
            while i < n:
                ch = body[i]
                if ch == '"' and not escaped:
                    break
                escaped = (ch == "\\" and not escaped)
                if ch != "\\":
                    escaped = False
                i += 1
            value = body[start:i]
            i += 1
        else:
            start = i
            while i < n and body[i] not in ",\n":
                i += 1
            value = body[start:i]
        fields[name] = re.sub(r"\s+", " ", value).strip()
    return fields


def parse_bib(path: Path) -> list[dict[str, str]]:
    result: list[dict[str, str]] = []
    for entry_type, key, body in split_entries(path.read_text(encoding="utf-8")):
        result.append({"type": entry_type, "key": key, **parse_fields(body)})
    return result


def strip_tex_comments(text: str) -> str:
    return "\n".join(re.split(r"(?<!\\)%", line, maxsplit=1)[0] for line in text.splitlines())


def collect_citation_contexts(paper: Path) -> dict[str, list[dict[str, str]]]:
    contexts: dict[str, list[dict[str, str]]] = {}
    for tex_path in sorted(paper.rglob("*.tex")):
        text = strip_tex_comments(tex_path.read_text(encoding="utf-8", errors="ignore"))
        section = ""
        cursor = 0
        token_re = re.compile(r"\\(?:section|subsection)\{([^}]*)\}|\\cite\{([^}]*)\}")
        for match in token_re.finditer(text):
            if match.group(1) is not None:
                section = re.sub(r"\\[A-Za-z]+|[{}]", "", match.group(1)).strip()
            else:
                lo = max(0, text.rfind("\n\n", 0, match.start()))
                hi0 = text.find("\n\n", match.end())
                hi = len(text) if hi0 < 0 else hi0
                snippet = re.sub(r"\s+", " ", text[lo:hi]).strip()
                for key in (x.strip() for x in match.group(2).split(",")):
                    if key:
                        contexts.setdefault(key, []).append({
                            "file": str(tex_path.relative_to(paper)),
                            "section": section,
                            "snippet": snippet,
                        })
            cursor = match.end()
    return contexts


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--paper", type=Path)
    parser.add_argument("--out", type=Path)
    parser.add_argument("--min-entries", type=int, default=55)
    args = parser.parse_args()
    root = args.root.resolve(strict=True)
    paper = (args.paper or root.parent / "paper").resolve(strict=True)
    out = (args.out or root / "literature").resolve()
    out.mkdir(parents=True, exist_ok=True)

    entries = parse_bib(paper / "references.bib")
    contexts = collect_citation_contexts(paper)
    keys = [entry["key"] for entry in entries]
    errors: list[str] = []
    if len(entries) < args.min_entries:
        errors.append(f"only {len(entries)} entries; require at least {args.min_entries}")
    if len(keys) != len(set(keys)):
        errors.append("duplicate BibTeX keys")
    cited = set(contexts)
    key_set = set(keys)
    if cited - key_set:
        errors.append("missing BibTeX keys: " + ", ".join(sorted(cited - key_set)))
    if key_set - cited:
        errors.append("uncited BibTeX entries: " + ", ".join(sorted(key_set - cited)))

    ledger_path = root / "literature.csv"
    with ledger_path.open(newline="", encoding="utf-8") as handle:
        ledger_rows = list(csv.DictReader(handle))
    ledger = {row["key"]: row for row in ledger_rows}
    if len(ledger_rows) != len(ledger):
        errors.append("duplicate keys in literature.csv")
    if set(ledger) != key_set:
        errors.append("literature.csv key set differs from references.bib")

    seen_titles: dict[str, str] = {}
    seen_dois: dict[str, str] = {}
    audit_rows: list[dict[str, str | int]] = []
    context_rows: list[dict[str, str | int]] = []
    for entry in entries:
        key = entry["key"]
        title = entry.get("title", "")
        norm_title = normalize(title)
        doi = entry.get("doi", "").strip().lower()
        url = entry.get("url", "").strip()
        row_errors: list[str] = []
        if not title:
            row_errors.append("missing title")
        elif norm_title in seen_titles:
            row_errors.append(f"duplicate title with {seen_titles[norm_title]}")
        else:
            seen_titles[norm_title] = key
        if entry["type"] == "misc":
            if not url:
                row_errors.append("misc source lacks URL")
            if "commit" not in entry.get("howpublished", "").lower():
                row_errors.append("software source is not pinned to a commit")
            identifier = url
            identity_basis = "immutable-source-url"
        else:
            if not doi or not DOI_RE.match(doi):
                row_errors.append("missing or malformed DOI")
            elif doi in seen_dois:
                row_errors.append(f"duplicate DOI with {seen_dois[doi]}")
            else:
                seen_dois[doi] = key
            identifier = doi
            identity_basis = "doi"
        contexts_for_key = contexts.get(key, [])
        if not contexts_for_key:
            row_errors.append("not cited")
        ledger_row = ledger.get(key, {})
        if ledger_row:
            if normalize(ledger_row.get("title", "")) != norm_title:
                row_errors.append("ledger title mismatch")
            expected_source = url if entry["type"] == "misc" else f"https://doi.org/{doi}"
            if ledger_row.get("source_url", "").lower() != expected_source.lower():
                row_errors.append("ledger source URL mismatch")
            if not ledger_row.get("reading_depth") or not ledger_row.get("relevant_content"):
                row_errors.append("ledger lacks reading-depth or relevance record")
        status = "stable-identity-record" if not row_errors else "error"
        audit_rows.append({
            "key": key,
            "type": entry["type"],
            "year": entry.get("year", ""),
            "title": title,
            "venue": entry.get("journal") or entry.get("booktitle") or entry.get("howpublished", ""),
            "identifier": identifier,
            "identity_basis": identity_basis,
            "citation_occurrences": len(contexts_for_key),
            "reading_depth": ledger_row.get("reading_depth", ""),
            "status": status,
            "errors": "; ".join(row_errors),
        })
        for item in contexts_for_key:
            context_rows.append({
                "key": key,
                "title": title,
                "file": item["file"],
                "section": item["section"],
                "snippet": item["snippet"],
                "ledger_relevance": ledger_row.get("relevant_content", ""),
                "ledger_delta_or_limit": ledger_row.get("retained_delta_or_limit", ""),
            })
        errors.extend(f"{key}: {message}" for message in row_errors)

    if audit_rows:
        with (out / "reference-identity-audit.csv").open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=audit_rows[0].keys())
            writer.writeheader(); writer.writerows(audit_rows)
    if context_rows:
        with (out / "citation-context-audit.csv").open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=context_rows[0].keys())
            writer.writeheader(); writer.writerows(context_rows)

    stable = sum(row["status"] == "stable-identity-record" for row in audit_rows)
    summary = {
        "schema": "offline-bibliography-audit-v1",
        "status": "pass" if not errors else "fail",
        "entries": len(entries),
        "minimum_required": args.min_entries,
        "scholarly_doi_entries": sum(entry["type"] != "misc" and bool(entry.get("doi")) for entry in entries),
        "pinned_source_entries": sum(entry["type"] == "misc" for entry in entries),
        "stable_identity_records": stable,
        "citation_keys": len(cited),
        "citation_occurrences": sum(len(items) for items in contexts.values()),
        "duplicate_titles": len(entries) - len(seen_titles),
        "duplicate_dois": sum(bool(entry.get("doi")) for entry in entries) - len(seen_dois),
        "unresolved": errors,
        "scope_note": (
            "Identity means a unique stable DOI or an immutable pinned source plus exact ledger and citation closure. "
            "The clean run is offline and does not claim to re-resolve registries or to have read every paper in full; "
            "reading depth is recorded separately in literature.csv."
        ),
    }
    (out / "bibliography-verification.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
    raise SystemExit(0 if summary["status"] == "pass" else 1)


if __name__ == "__main__":
    main()
