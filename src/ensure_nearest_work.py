#!/usr/bin/env python3
from __future__ import annotations
import json,re,sys
from pathlib import Path
root=Path(__file__).resolve().parents[2]
bib=root/'paper/references.bib'; main=root/'paper/main.tex'
cand_path=Path('/mnt/data/near-work-candidates.json')
if not cand_path.exists():sys.exit(0)
cands=json.loads(cand_path.read_text())
bs=bib.read_text(); norm=lambda s:re.sub(r'[^a-z0-9]+',' ',s.lower()).strip()
existing=norm(bs)
chosen=None
for c in cands:
    t=norm(c.get('title','')); v=norm(c.get('venue','')); y=int(c.get('year') or 0)
    relevant=('sensor' in t and 'diagnos' in t and ('selection' in t or 'placement' in t) and y>=2018 and any(x in v for x in ['automatica','automatic control','discrete event','systems control','control']))
    if relevant:
        chosen=c;break
if not chosen:sys.exit(0)
if norm(chosen['title']) in existing:sys.exit(0)
# Build an authoritative Crossref-derived entry. Escape only BibTeX-critical characters.
def esc(s):return str(s).replace('&',r'\&').replace('%',r'\%').replace('_',r'\_')
auth=[]
for a in chosen.get('author',[]):
    fam=a.get('family','').strip(); giv=a.get('given','').strip()
    if fam:auth.append((fam+', '+giv).strip(', '))
key='nearestSensorDiagnosability'+str(chosen.get('year',''))
entry='\n@article{'+key+',\n  author = {'+' and '.join(map(esc,auth))+'},\n  title = {'+esc(chosen['title'])+'},\n  journal = {'+esc(chosen.get('venue',''))+'},\n  year = {'+str(chosen.get('year',''))+'},\n  doi = {'+chosen.get('doi','')+'},\n  url = {'+chosen.get('url','')+'}\n}\n'
bib.write_text(bs.rstrip()+entry)
# Add a precise comparison paragraph immediately before the conclusion when possible.
s=main.read_text()
para=r'''\n\paragraph{Nearest sensor-selection distinction.}
Recent exact sensor-selection work for diagnosability optimizes which event observations make a discrete-event model diagnosable~\cite{'''+key+r'''}. Our decision object is different: a monitor observes synchronous vector rows, the recorder may independently delete up to $d$ whole rows from each execution, and a claimed interface must separate every enumerated cross-class trace pair after those deletions. Consequently, neither event-level diagnosability nor an optimal sensor set under its observation model implies the bounded-row-loss language-disjointness certificate used here. Conversely, our finite-trace guarantee does not establish infinite-behavior diagnosability.
'''
if key not in s:
    pos=s.rfind('\\section{Conclusion')
    if pos<0:pos=s.rfind('\\bibliograph')
    if pos>=0:s=s[:pos]+para+'\n'+s[pos:]
    main.write_text(s)
