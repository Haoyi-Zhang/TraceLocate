#!/usr/bin/env python3
"""Independent bibliography identity and usage audit.

The audit is deliberately conservative: it detects duplicate identities,
uncited entries, missing entries, malformed DOIs, and definite metadata
mismatches against Crossref. Network failures are reported separately and do
not turn unverified metadata into a positive verification claim.
"""
from __future__ import annotations
import argparse, csv, json, re, subprocess, time, unicodedata
from dataclasses import dataclass, asdict
from pathlib import Path
from difflib import SequenceMatcher
from urllib.parse import quote

FIELD_RE = re.compile(r"(?ims)^\s*([A-Za-z][A-Za-z0-9_-]*)\s*=\s*(\{(?:[^{}]|\{[^{}]*\})*\}|\"(?:[^\"\\]|\\.)*\")\s*,?")
ENTRY_RE = re.compile(r"(?ms)^@(\w+)\s*\{\s*([^,]+),(.*?)(?=^@\w+\s*\{|\Z)")
DOI_RE = re.compile(r"^10\.\d{4,9}/\S+$", re.I)

def strip_outer(v:str)->str:
    v=v.strip()
    if len(v)>=2 and ((v[0]=='{' and v[-1]=='}') or (v[0]=='"' and v[-1]=='"')):
        v=v[1:-1]
    return re.sub(r"\s+"," ",v).strip()

def parse_bib(path:Path):
    s=path.read_text(encoding='utf-8')
    out=[]
    for m in ENTRY_RE.finditer(s):
        typ,key,body=m.groups(); fields={}
        for fm in FIELD_RE.finditer(body):
            fields[fm.group(1).lower()]=strip_outer(fm.group(2))
        out.append({'type':typ.lower(),'key':key.strip(),**fields})
    return out

def normalize(s:str)->str:
    s=s.replace('\\&',' and ').replace('~',' ')
    s=re.sub(r"\\[A-Za-z]+\*?(?:\[[^]]*\])?",' ',s)
    s=s.replace('{','').replace('}','').replace('\\',' ')
    s=unicodedata.normalize('NFKD',s).encode('ascii','ignore').decode().lower()
    s=re.sub(r'[^a-z0-9]+',' ',s)
    return ' '.join(s.split())

def title_similarity(a,b):
    a=normalize(a); b=normalize(b)
    if not a or not b:return 0.0
    seq=SequenceMatcher(None,a,b).ratio()
    sa,sb=set(a.split()),set(b.split())
    jac=len(sa&sb)/max(1,len(sa|sb))
    return max(seq,jac)

def curl_json(url:str, timeout=30):
    cp=subprocess.run(['curl','-LfsS','--retry','2','--max-time',str(timeout),'-H','User-Agent: coverage-certified-research-audit/1.0 (mailto:noreply@example.com)',url],capture_output=True,text=True)
    if cp.returncode:return None,cp.stderr[-500:]
    try:return json.loads(cp.stdout),''
    except Exception as e:return None,f'json:{e}'

def collect_cites(texroot:Path):
    keys=set()
    for p in texroot.rglob('*.tex'):
        s=p.read_text(encoding='utf-8',errors='ignore')
        # Remove comments while respecting escaped percent.
        s='\n'.join(re.split(r'(?<!\\)%',line,maxsplit=1)[0] for line in s.splitlines())
        for m in re.finditer(r'\\(?:cite|citep|citet|citeauthor|citeyear|citealp|citealt|nocite)\w*\s*(?:\[[^]]*\]\s*)*\{([^}]*)\}',s):
            keys.update(k.strip() for k in m.group(1).split(',') if k.strip() and k.strip()!='*')
    return keys

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--paper',type=Path,default=Path(__file__).resolve().parents[2]/'paper')
    ap.add_argument('--out',type=Path,default=Path(__file__).resolve().parents[1]/'literature')
    ap.add_argument('--min-entries',type=int,default=55)
    ap.add_argument('--require-network',action='store_true')
    args=ap.parse_args(); args.out.mkdir(parents=True,exist_ok=True)
    bib=args.paper/'references.bib'; entries=parse_bib(bib); cites=collect_cites(args.paper)
    keys={e['key'] for e in entries}; errors=[]; warnings=[]
    if len(entries)<args.min_entries:errors.append(f'only {len(entries)} entries; require {args.min_entries}')
    if len(keys)!=len(entries):errors.append('duplicate BibTeX keys')
    missing=sorted(cites-keys); uncited=sorted(keys-cites)
    if missing:errors.append('missing BibTeX keys: '+', '.join(missing))
    if uncited:errors.append('uncited BibTeX entries: '+', '.join(uncited))
    seen_title={}; seen_doi={}; rows=[]; cache={}
    cache_path=args.out/'crossref_cache.json'
    if cache_path.exists():
        try:cache=json.loads(cache_path.read_text())
        except Exception:cache={}
    network_success=0
    for e in entries:
        key=e['key']; title=e.get('title',''); doi=e.get('doi','').strip().lower().replace('https://doi.org/','').replace('http://doi.org/','')
        nt=normalize(title)
        if not title:errors.append(f'{key}: missing title')
        if nt in seen_title:errors.append(f'{key}: duplicate title with {seen_title[nt]}')
        else:seen_title[nt]=key
        status='metadata-only'; remote_title=''; remote_year=''; sim=''; note=''
        if doi:
            if not DOI_RE.match(doi):errors.append(f'{key}: malformed DOI {doi}')
            if doi in seen_doi:errors.append(f'{key}: duplicate DOI with {seen_doi[doi]}')
            else:seen_doi[doi]=key
            obj=cache.get(doi)
            if obj is None:
                data,err=curl_json('https://api.crossref.org/works/'+quote(doi,safe=''))
                if data and data.get('status')=='ok':
                    obj=data.get('message',{}); cache[doi]=obj; network_success+=1; time.sleep(0.05)
                else:
                    note='crossref unavailable: '+err
            else:network_success+=1
            if obj:
                remote_title=(obj.get('title') or [''])[0]
                parts=obj.get('published-print') or obj.get('published-online') or obj.get('issued') or {}
                try:remote_year=str(parts['date-parts'][0][0])
                except Exception:remote_year=''
                score=title_similarity(title,remote_title); sim=f'{score:.3f}'
                if score<0.58:
                    status='definite-mismatch'; errors.append(f'{key}: Crossref title mismatch ({score:.3f})')
                else:
                    status='crossref-verified'
                by=e.get('year','')
                if by.isdigit() and remote_year.isdigit() and abs(int(by)-int(remote_year))>1:
                    status='definite-mismatch'; errors.append(f'{key}: year {by} vs Crossref {remote_year}')
        else:
            url=e.get('url','')
            if not url and not e.get('isbn',''):
                warnings.append(f'{key}: no DOI/URL/ISBN; identity supported only by supplied metadata')
            status='url-or-isbn' if (url or e.get('isbn','')) else 'metadata-only'
        rows.append({'key':key,'type':e.get('type',''),'year':e.get('year',''),'title':title,'venue':e.get('journal') or e.get('booktitle') or e.get('publisher',''),'doi':doi,'url':e.get('url',''),'status':status,'crossref_title':remote_title,'crossref_year':remote_year,'title_similarity':sim,'note':note})
    cache_path.write_text(json.dumps(cache,ensure_ascii=False,indent=2,sort_keys=True))
    with (args.out/'literature_audit.csv').open('w',newline='',encoding='utf-8') as f:
        w=csv.DictWriter(f,fieldnames=rows[0].keys() if rows else ['key']);w.writeheader();w.writerows(rows)
    summary={'entries':len(entries),'cited_keys':len(cites),'missing_keys':missing,'uncited_keys':uncited,'doi_entries':sum(bool(r['doi']) for r in rows),'crossref_verified':sum(r['status']=='crossref-verified' for r in rows),'definite_mismatches':sum(r['status']=='definite-mismatch' for r in rows),'network_successes':network_success,'warnings':warnings,'errors':errors,'status':'pass' if not errors and (network_success>0 or not args.require_network) else 'fail'}
    (args.out/'literature_audit.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2))
    print(json.dumps(summary,ensure_ascii=False,indent=2))
    raise SystemExit(0 if summary['status']=='pass' else 1)
if __name__=='__main__':main()
