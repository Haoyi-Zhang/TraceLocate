#!/usr/bin/env python3
from pathlib import Path
import csv,json
root=Path(__file__).resolve().parents[2];lit=root/'artifact/literature';audit=lit/'literature_audit.csv'
if not audit.exists():raise SystemExit('run verify_bibliography first')
rows=[]
with audit.open(encoding='utf-8') as f:
 for r in csv.DictReader(f):
  status=r['status'];
  rows.append({'key':r['key'],'year':r['year'],'title':r['title'],'venue':r['venue'],'doi':r['doi'],'identity_evidence':status,'content_access_level':'metadata/abstract unless separately noted','claim_use':'citation identity and topic placement; no blanket full-text-reading claim'})
with (lit/'reading_ledger.csv').open('w',newline='',encoding='utf-8') as f:
 w=csv.DictWriter(f,fieldnames=rows[0].keys());w.writeheader();w.writerows(rows)
(lit/'README.md').write_text('''# Literature evidence\n\n`literature_audit.csv` records citation identity checks and Crossref comparisons.\n`reading_ledger.csv` deliberately distinguishes identity verification from content access.\nThe artifact does not redistribute copyrighted papers and makes no blanket claim that every cited work was read in full.\nA citation is retained only when it is used in the manuscript; DOI metadata, an official URL, ISBN, or fixed-source provenance supports its identity.\n''')
