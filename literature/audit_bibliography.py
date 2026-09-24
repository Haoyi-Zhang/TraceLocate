#!/usr/bin/env python3
"""Fail-closed bibliography identity audit.

Every BibTeX entry must resolve through one of:
* exact DOI registry metadata (Crossref or OpenAlex),
* high-confidence title/year/author registry match,
* ISBN registry metadata,
* an allow-listed authoritative publisher/standards page, or
* a pinned, byte-checked public software source recorded in this artifact.

The script writes an auditable CSV/JSON ledger and exits nonzero on any
unresolved or materially mismatched entry.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import html
import json
import re
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any, Iterable

UA = "coverage-certified-trace-localization-bibliography-audit/1.0 (research artifact)"
AUTHORITATIVE_HOSTS = {
    "doi.org", "dx.doi.org", "ieeexplore.ieee.org", "dl.acm.org",
    "link.springer.com", "springer.com", "sciencedirect.com", "elsevier.com",
    "onlinelibrary.wiley.com", "cambridge.org", "mitpress.mit.edu",
    "nist.gov", "nvlpubs.nist.gov", "arxiv.org", "drops.dagstuhl.de",
    "openlibrary.org", "worldcat.org", "usenix.org", "riscv.org",
    "arm.com", "developer.arm.com", "accellera.org", "iso.org",
    "github.com", "raw.githubusercontent.com", "opencores.org",
    "computer.org", "ieee.org", "sigda.org", "dblp.org",
}

@dataclass
class Entry:
    kind: str
    key: str
    fields: dict[str, str]


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def strip_outer(value: str) -> str:
    value = value.strip().rstrip(",").strip()
    if len(value) >= 2 and ((value[0] == "{" and value[-1] == "}") or (value[0] == '"' and value[-1] == '"')):
        return value[1:-1]
    return value


def parse_bibtex(path: Path) -> list[Entry]:
    text = path.read_text(encoding="utf-8")
    entries: list[Entry] = []
    pos = 0
    while True:
        m = re.search(r"@(\w+)\s*\{", text[pos:], re.I)
        if not m:
            break
        kind = m.group(1)
        start = pos + m.end()
        depth = 1
        i = start
        quote = False
        escape = False
        while i < len(text) and depth:
            ch = text[i]
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                quote = not quote
            elif not quote:
                if ch == "{": depth += 1
                elif ch == "}": depth -= 1
            i += 1
        if depth:
            raise ValueError(f"unbalanced BibTeX entry near byte {start}")
        body = text[start:i-1]
        comma = body.find(",")
        if comma < 0:
            raise ValueError("missing BibTeX key delimiter")
        key = body[:comma].strip()
        fields_text = body[comma+1:]
        fields: dict[str, str] = {}
        j = 0
        while j < len(fields_text):
            while j < len(fields_text) and fields_text[j] in " \t\r\n,": j += 1
            if j >= len(fields_text): break
            fm = re.match(r"([A-Za-z][A-Za-z0-9_-]*)\s*=\s*", fields_text[j:])
            if not fm:
                # Ignore trailing comments/unknown tokens rather than silently
                # misparse a real field.
                rem = fields_text[j:].strip()
                if rem:
                    raise ValueError(f"cannot parse field in {key}: {rem[:80]!r}")
                break
            name = fm.group(1).lower()
            j += fm.end()
            if j >= len(fields_text): raise ValueError(f"missing value for {key}.{name}")
            if fields_text[j] == "{":
                k = j + 1; d = 1; esc = False
                while k < len(fields_text) and d:
                    c = fields_text[k]
                    if esc: esc = False
                    elif c == "\\": esc = True
                    elif c == "{": d += 1
                    elif c == "}": d -= 1
                    k += 1
                if d: raise ValueError(f"unbalanced field {key}.{name}")
                raw = fields_text[j:k]
                j = k
            elif fields_text[j] == '"':
                k = j + 1; esc = False
                while k < len(fields_text):
                    c = fields_text[k]
                    if esc: esc = False
                    elif c == "\\": esc = True
                    elif c == '"':
                        k += 1; break
                    k += 1
                raw = fields_text[j:k]
                j = k
            else:
                k = j
                while k < len(fields_text) and fields_text[k] not in ",\n": k += 1
                raw = fields_text[j:k]
                j = k
            fields[name] = strip_outer(raw).strip()
        entries.append(Entry(kind.lower(), key, fields))
        pos = i
    if not entries:
        raise ValueError("no BibTeX entries parsed")
    keys = [e.key for e in entries]
    if len(keys) != len(set(keys)):
        raise ValueError("duplicate BibTeX keys")
    return entries


def latex_plain(s: str) -> str:
    s = html.unescape(s or "")
    # Common protected/accent forms are normalized after command removal.
    s = re.sub(r"\\(?:textit|textbf|emph|mathrm|mathit|operatorname)\s*\{([^{}]*)\}", r"\1", s)
    s = re.sub(r"\\[A-Za-z]+\*?(?:\[[^\]]*\])?", " ", s)
    s = s.replace("{", "").replace("}", "").replace("$", " ")
    s = re.sub(r"[~_^\\]", " ", s)
    s = unicodedata.normalize("NFKD", s)
    s = "".join(ch for ch in s if not unicodedata.combining(ch))
    return re.sub(r"\s+", " ", s).strip()


def norm(s: str) -> str:
    s = latex_plain(s).lower()
    s = re.sub(r"[^a-z0-9]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def tokens(s: str) -> set[str]:
    stop = {"a","an","the","of","for","to","and","in","on","with","by","from","using","toward","towards"}
    return {x for x in norm(s).split() if len(x) > 1 and x not in stop}


def title_score(a: str, b: str) -> float:
    na, nb = norm(a), norm(b)
    if not na or not nb: return 0.0
    ta, tb = tokens(a), tokens(b)
    j = len(ta & tb) / max(1, len(ta | tb))
    c = len(ta & tb) / max(1, min(len(ta), len(tb)))
    seq = SequenceMatcher(None, na, nb).ratio()
    return max(j, 0.65*c + 0.35*seq, seq)


def first_year(obj: dict[str, Any]) -> str:
    for name in ("published-print", "published-online", "issued", "created"):
        parts = (((obj.get(name) or {}).get("date-parts") or [[None]])[0])
        if parts and parts[0]: return str(parts[0])
    return ""


def surname(author_field: str) -> str:
    if not author_field: return ""
    first = re.split(r"\s+and\s+", latex_plain(author_field), flags=re.I)[0].strip()
    if "," in first: return norm(first.split(",",1)[0]).split()[-1]
    bits = norm(first).split()
    return bits[-1] if bits else ""


def response_json(url: str, cache_path: Path, timeout: int = 30) -> tuple[dict[str, Any] | list[Any], str, int]:
    if cache_path.exists():
        raw = cache_path.read_bytes()
        return json.loads(raw), sha256_bytes(raw), 200
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        raw = r.read()
        status = getattr(r, "status", 200)
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_bytes(raw)
    return json.loads(raw), sha256_bytes(raw), status


def response_head(url: str, timeout: int = 25) -> tuple[int, str, str]:
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "text/html,application/pdf,*/*"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        data = r.read(200000)
        status = getattr(r, "status", 200)
        final = r.geturl()
    text = data.decode("utf-8", "ignore")
    return status, final, text


def candidate_title(obj: dict[str, Any]) -> str:
    t = obj.get("title", "")
    if isinstance(t, list): return t[0] if t else ""
    return str(t or "")


def verify_doi(entry: Entry, cache: Path) -> dict[str, Any] | None:
    doi = entry.fields.get("doi", "").strip().lower().replace("https://doi.org/", "")
    if not doi: return None
    enc = urllib.parse.quote(doi, safe="")
    try:
        data, digest, status = response_json(f"https://api.crossref.org/works/{enc}", cache/f"crossref-doi-{entry.key}.json")
        msg = data.get("message", {}) if isinstance(data, dict) else {}
        rt = candidate_title(msg)
        score = title_score(entry.fields.get("title", ""), rt)
        registered_doi = str(msg.get("DOI", "")).lower()
        if status == 200 and registered_doi == doi and score >= 0.62:
            return {"method":"crossref_doi", "registry_title":rt, "registry_year":first_year(msg), "score":score,
                    "evidence_url":f"https://api.crossref.org/works/{enc}", "response_sha256":digest}
    except Exception:
        pass
    try:
        data, digest, status = response_json(f"https://api.openalex.org/works/https://doi.org/{enc}", cache/f"openalex-doi-{entry.key}.json")
        rt = str(data.get("display_name", ""))
        score = title_score(entry.fields.get("title", ""), rt)
        if status == 200 and score >= 0.62:
            return {"method":"openalex_doi", "registry_title":rt, "registry_year":str(data.get("publication_year", "")), "score":score,
                    "evidence_url":f"https://api.openalex.org/works/https://doi.org/{enc}", "response_sha256":digest}
    except Exception:
        pass
    return None


def verify_title(entry: Entry, cache: Path) -> dict[str, Any] | None:
    title = entry.fields.get("title", "")
    year = entry.fields.get("year", "")
    auth = surname(entry.fields.get("author", ""))
    q = urllib.parse.urlencode({"query.bibliographic": latex_plain(title), "rows":"5", "select":"DOI,title,author,issued,published-print,published-online,created,publisher,type"})
    try:
        data, digest, _ = response_json(f"https://api.crossref.org/works?{q}", cache/f"crossref-title-{entry.key}.json")
        items = (((data or {}).get("message") or {}).get("items") or []) if isinstance(data, dict) else []
        best = None
        for item in items:
            rt = candidate_title(item)
            score = title_score(title, rt)
            ry = first_year(item)
            year_ok = not year or not ry or abs(int(re.sub(r"\D","",year)[:4] or 0)-int(ry[:4])) <= 2
            names = " ".join(norm(str(a.get("family", ""))) for a in item.get("author", []) if isinstance(a, dict))
            author_ok = not auth or not names or auth in names.split()
            rank = score + (0.04 if year_ok else -0.25) + (0.03 if author_ok else -0.10)
            if best is None or rank > best[0]: best=(rank,score,year_ok,author_ok,item,rt,ry)
        if best and best[1] >= 0.78 and best[2] and best[3]:
            item=best[4]
            return {"method":"crossref_title", "registry_title":best[5], "registry_year":best[6], "score":best[1],
                    "evidence_url":f"https://api.crossref.org/works?{q}", "response_sha256":digest,
                    "matched_doi":str(item.get("DOI", ""))}
    except Exception:
        pass
    q2 = urllib.parse.urlencode({"search":latex_plain(title), "per-page":"5"})
    try:
        data, digest, _ = response_json(f"https://api.openalex.org/works?{q2}", cache/f"openalex-title-{entry.key}.json")
        best=None
        for item in (data.get("results",[]) if isinstance(data,dict) else []):
            rt=str(item.get("display_name", "")); score=title_score(title,rt); ry=str(item.get("publication_year", ""))
            year_ok=not year or not ry or abs(int(re.sub(r"\D","",year)[:4] or 0)-int(ry[:4]))<=2
            rank=score+(0.04 if year_ok else -0.25)
            if best is None or rank>best[0]: best=(rank,score,year_ok,item,rt,ry)
        if best and best[1]>=0.80 and best[2]:
            return {"method":"openalex_title", "registry_title":best[4], "registry_year":best[5], "score":best[1],
                    "evidence_url":f"https://api.openalex.org/works?{q2}", "response_sha256":digest,
                    "matched_doi":str((best[3].get("doi") or "")).replace("https://doi.org/","")}
    except Exception:
        pass
    return None


def verify_isbn(entry: Entry, cache: Path) -> dict[str, Any] | None:
    isbn = re.sub(r"[^0-9Xx]", "", entry.fields.get("isbn", ""))
    if not isbn: return None
    try:
        data,digest,_=response_json(f"https://openlibrary.org/isbn/{isbn}.json",cache/f"openlibrary-isbn-{entry.key}.json")
        rt=str(data.get("title", "")); score=title_score(entry.fields.get("title",""),rt)
        if score>=0.65:
            return {"method":"openlibrary_isbn","registry_title":rt,"registry_year":str(data.get("publish_date","")),"score":score,
                    "evidence_url":f"https://openlibrary.org/isbn/{isbn}.json","response_sha256":digest}
    except Exception:
        pass
    return None


def verify_pinned_software(entry: Entry, artifact: Path) -> dict[str, Any] | None:
    mapping={
        "benmarshall_uart": artifact/"rtl"/"ben-marshall-uart"/"SOURCE.json",
        "bmartini_arbiter": artifact/"rtl"/"bmartini-arbiter"/"SOURCE.json",
    }
    p=mapping.get(entry.key)
    if not p or not p.exists(): return None
    data=json.loads(p.read_text(encoding="utf-8"))
    # Every SOURCE record must describe byte-checked files that exist locally.
    files=data.get("files",[])
    if not files: return None
    checked=0
    for f in files:
        rel=f.get("path") or f.get("local_path") or f.get("name")
        expected=f.get("sha256")
        candidates=[p.parent/"upstream"/Path(str(rel)).name, p.parent/Path(str(rel))]
        local=next((x for x in candidates if x.exists()),None)
        if local is None or not expected or sha256_bytes(local.read_bytes())!=expected: return None
        checked+=1
    return {"method":"pinned_software_source","registry_title":entry.fields.get("title",""),"registry_year":entry.fields.get("year",""),
            "score":1.0,"evidence_url":entry.fields.get("url",data.get("repository","")),"response_sha256":sha256_bytes(p.read_bytes()),
            "checked_files":checked}


def verify_authoritative_url(entry: Entry) -> dict[str, Any] | None:
    url=entry.fields.get("url","").strip()
    if not url: return None
    host=(urllib.parse.urlparse(url).hostname or "").lower()
    if not any(host==h or host.endswith("."+h) for h in AUTHORITATIVE_HOSTS): return None
    try:
        status,final,text=response_head(url)
        if 200<=status<400:
            # For HTML, require at least one uncommon title token on the page,
            # except exact standards/repository URLs whose path is the identity.
            tt={x for x in tokens(entry.fields.get("title","")) if len(x)>=5}
            page=norm(text[:150000])
            token_hits=sum(1 for x in tt if x in page)
            path=urllib.parse.urlparse(final).path.lower()
            identity_path=any(s in path for s in ("/doi/", "/document/", "/standards/", "/repos/", "/blob/", "/tree/", "/abs/", "/pdf/"))
            if token_hits>=min(2,max(1,len(tt)//4)) or identity_path:
                return {"method":"authoritative_url","registry_title":"","registry_year":"","score":1.0 if identity_path else token_hits/max(1,len(tt)),
                        "evidence_url":final,"response_sha256":sha256_bytes(text.encode("utf-8","ignore"))}
    except Exception:
        pass
    return None


def main() -> None:
    ap=argparse.ArgumentParser()
    ap.add_argument("--bib",type=Path,default=Path(__file__).resolve().parents[2]/"paper"/"references.bib")
    ap.add_argument("--artifact",type=Path,default=Path(__file__).resolve().parents[1])
    ap.add_argument("--outdir",type=Path,default=Path(__file__).resolve().parent)
    args=ap.parse_args()
    args.outdir.mkdir(parents=True,exist_ok=True)
    cache=args.outdir/"cache"; cache.mkdir(parents=True,exist_ok=True)
    entries=parse_bibtex(args.bib)
    rows=[]
    for i,e in enumerate(entries,1):
        result=verify_pinned_software(e,args.artifact)
        if result is None: result=verify_doi(e,cache)
        if result is None: result=verify_isbn(e,cache)
        if result is None: result=verify_title(e,cache)
        if result is None: result=verify_authoritative_url(e)
        status="verified" if result else "unresolved"
        result=result or {"method":"","registry_title":"","registry_year":"","score":0.0,"evidence_url":"","response_sha256":""}
        rows.append({
            "index":i,"key":e.key,"entry_type":e.kind,"title":latex_plain(e.fields.get("title","")),
            "year":e.fields.get("year",""),"authors":latex_plain(e.fields.get("author","")),"venue":latex_plain(e.fields.get("journal") or e.fields.get("booktitle") or e.fields.get("publisher") or ""),
            "doi":e.fields.get("doi",""),"url":e.fields.get("url",""),"status":status,
            "verification_method":result.get("method",""),"matched_title":result.get("registry_title",""),
            "matched_year":result.get("registry_year",""),"title_score":round(float(result.get("score",0.0)),6),
            "matched_doi":result.get("matched_doi",""),"evidence_url":result.get("evidence_url",""),
            "evidence_sha256":result.get("response_sha256",""),"checked_files":result.get("checked_files","")
        })
        time.sleep(0.05)
    fields=list(rows[0])
    csv_path=args.outdir/"bibliography-verification.csv"
    with csv_path.open("w",newline="",encoding="utf-8") as f:
        w=csv.DictWriter(f,fieldnames=fields); w.writeheader(); w.writerows(rows)
    unresolved=[r["key"] for r in rows if r["status"]!="verified"]
    methods={}
    for r in rows: methods[r["verification_method"]]=methods.get(r["verification_method"],0)+1
    report={
        "schema":"bibliography-verification-v1","bibtex_path":str(args.bib),"bibtex_sha256":sha256_bytes(args.bib.read_bytes()),
        "entries":len(rows),"verified":len(rows)-len(unresolved),"unresolved":unresolved,"methods":dict(sorted(methods.items())),
        "ledger_csv":csv_path.name,"ledger_sha256":sha256_bytes(csv_path.read_bytes()),"rows":rows,
    }
    (args.outdir/"bibliography-verification.json").write_text(json.dumps(report,indent=2,sort_keys=True)+"\n",encoding="utf-8")
    print(json.dumps({k:report[k] for k in ("entries","verified","unresolved","methods")},indent=2,sort_keys=True))
    if unresolved:
        raise SystemExit("unresolved bibliography entries: "+", ".join(unresolved))

if __name__=="__main__":
    main()
