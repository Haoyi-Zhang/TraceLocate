#!/usr/bin/env python3
"""Fail-closed consistency gate for the scientific artifact.

This is not a release manifest generator. It checks that retained scientific
claims, sources, results, bibliography, and the compiled paper agree.
"""
from __future__ import annotations
import argparse,ast,csv,json,re,subprocess,sys,zipfile
from pathlib import Path

def run(cmd,cwd,timeout=900):
    cp=subprocess.run(cmd,cwd=cwd,text=True,capture_output=True,timeout=timeout)
    if cp.returncode:
        raise AssertionError(f"command failed {cmd}\nSTDOUT:\n{cp.stdout[-4000:]}\nSTDERR:\n{cp.stderr[-4000:]}")
    return cp.stdout+cp.stderr

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--root',type=Path,default=Path(__file__).resolve().parents[2]);ap.add_argument('--pdf',type=Path,default=None);a=ap.parse_args();root=a.root.resolve();paper=root/'paper';art=root/'artifact';errors=[]
    def need(cond,msg):
        if not cond:errors.append(msg)
    need(paper.is_dir() and art.is_dir(),'missing paper/ or artifact/')
    for p in root.rglob('*'):
        if p.is_file() and p.name in forbidden_names:errors.append(f'forbidden release metadata: {p.relative_to(root)}')
        if p.is_file() and p.suffix=='.py':
            try:ast.parse(p.read_text(encoding='utf-8'),filename=str(p))
            except Exception as e:errors.append(f'Python syntax: {p.relative_to(root)}: {e}')
    # Reject an implementation guard that imposes the historical twelve-observation ceiling.
    limit_patterns=[re.compile(r'len\([^)]*(?:obs|signal|candidate)[^)]*\)\s*>\s*12',re.I),re.compile(r'(?:at most|max(?:imum)?)\s+12\s+(?:observ|signal|candidate)',re.I)]
    for q in art.rglob('*.py'):
        qs=q.read_text(encoding='utf-8',errors='ignore')
        if q.name not in {'independent_math_validation.py','reviewer_gate.py'} and any(rx.search(qs) for rx in limit_patterns):
            errors.append(f'fixed twelve-observation implementation limit: {q.relative_to(root)}')
    # No stale claims from pre-two-bridge drafts.
    text='\n'.join(p.read_text(encoding='utf-8',errors='ignore') for p in root.rglob('*') if p.is_file() and p.suffix.lower() in {'.tex','.md','.py','.json','.csv','.sh'})
    # Bibliography and use.
    ba=art/'literature/literature_audit.json'
    need(ba.exists(),'missing literature audit')
    if ba.exists():
        b=json.loads(ba.read_text());need(b.get('entries',0)>=55,'fewer than 55 bibliography entries');need(not b.get('missing_keys'),'citations missing from BibTeX');need(not b.get('uncited_keys'),'uncited BibTeX padding');need(b.get('definite_mismatches',0)==0,'definite DOI metadata mismatch')
    # Independent mathematical oracle.
    mp=art/'results/independent_math_validation.json';need(mp.exists(),'missing independent math validation')
    if mp.exists():need(json.loads(mp.read_text()).get('status')=='pass','independent math validation failed')
    # Held-out processor bridge and its independent checker output.
    pb=art/'rtl/picorv32';
    for req in ['upstream/picorv32.v','upstream/SOURCE.json','tb_picorv32.v','results/summary.json','results/cases.json','results/check.json']:
        need((pb/req).exists(),f'missing PicoRV32 bridge file {req}')
    if (pb/'results/summary.json').exists():
        x=json.loads((pb/'results/summary.json').read_text());need(x.get('status')=='pass' and x.get('cases',0)>0,'PicoRV32 summary not passing')
    # Paper build products.
    pdf=a.pdf
    if pdf is None:
        ps=[p for p in paper.glob('*.pdf') if p.is_file()]
        pdf=max(ps,key=lambda p:p.stat().st_mtime) if ps else None
    need(pdf is not None and pdf.exists(),'compiled paper PDF absent')
    if pdf and pdf.exists():
        info=run(['pdfinfo',str(pdf)],root,60);m=re.search(r'^Pages:\s+(\d+)',info,re.M);need(bool(m),'cannot read page count')
        if m:need(int(m.group(1))<=14,'paper exceeds 14 pages')
        txt=run(['pdftotext',str(pdf),'-'],root,60)
        for phrase in ['Out-of-Sample Processor Bridge','Validity Boundary','PicoRV32']:
            need(phrase in txt,f'paper missing expected material: {phrase}')
        need('??' not in txt,'unresolved text marker in PDF')
    # Source provenance is scientific data, not a generated release checksum list.
    srcmeta=json.loads((pb/'upstream/SOURCE.json').read_text()) if (pb/'upstream/SOURCE.json').exists() else {}
    need(len(srcmeta.get('commit',''))==40,'PicoRV32 source is not commit-pinned')
    if errors:
        print(json.dumps({'status':'fail','errors':errors},indent=2));raise SystemExit(1)
    print(json.dumps({'status':'pass','checks':'paper/code/results/bibliography/provenance'},indent=2))
if __name__=='__main__':main()
