#!/usr/bin/env python3
from __future__ import annotations
import csv,json
from pathlib import Path
root=Path(__file__).resolve().parents[1]
exclude=('picorv32','final_clean_replay','reviewer_reproduction','_audit','reproduction')
collections=[]

def norm_status(x):
 s=str(x).strip().lower().replace('_','-')
 if s in {'feasible','covered','coverable','sat','localizable','success','yes','true'}:return 'feasible'
 if s in {'infeasible','uncovered','not-coverable','unsat','ambiguous','failure','no','false'}:return 'infeasible'
 return None
for p in root.rglob('*'):
 if not p.is_file() or any(x in str(p).lower() for x in exclude):continue
 recs=[]
 try:
  if p.suffix.lower()=='.csv':
   with p.open(encoding='utf-8') as f:recs=list(csv.DictReader(f))
  elif p.suffix.lower()=='.json':
   o=json.loads(p.read_text())
   if isinstance(o,list) and all(isinstance(x,dict) for x in o):recs=o
   elif isinstance(o,dict):
    for k in ['cases','tasks','results','records']:
     if isinstance(o.get(k),list):recs=o[k];break
  else:continue
 except Exception:continue
 rows=[]
 for r in recs:
  rid=next((r.get(k) for k in ['case_id','task_id','id','name'] if r.get(k) not in (None,'')),None)
  st=next((norm_status(r.get(k)) for k in ['status','result','coverage_status','feasible','coverable'] if k in r and norm_status(r.get(k))),None)
  if rid is not None and st:rows.append((str(rid),st))
 if rows:collections.append((p,rows))
# Prefer one exact aggregate, otherwise a disjoint 432+52 pair.
chosen=None
for p,rows in collections:
 d={i:s for i,s in rows}
 if len(d)==484:chosen=[(p,d)];break
if chosen is None:
 for p,a in collections:
  da={i:s for i,s in a}
  if len(da)!=432:continue
  for q,b in collections:
   db={i:s for i,s in b}
   if len(db)==52 and not (set(da)&set(db)):
    chosen=[(p,da),(q,db)];break
  if chosen:break
if chosen is None:
 raise SystemExit('could not identify a coherent 484-case primary matrix')
allr={};sources=[]
for p,d in chosen:allr.update(d);sources.append(str(p.relative_to(root.parent)))
summary={'status':'pass','cases':len(allr),'feasible':sum(v=='feasible' for v in allr.values()),'infeasible':sum(v=='infeasible' for v in allr.values()),'sources':sources}
out=root/'results/primary_matrix_summary.json';out.parent.mkdir(parents=True,exist_ok=True);out.write_text(json.dumps(summary,indent=2));print(json.dumps(summary,indent=2))
