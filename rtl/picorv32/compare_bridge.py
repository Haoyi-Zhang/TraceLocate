#!/usr/bin/env python3
from pathlib import Path
import argparse,json,hashlib
ap=argparse.ArgumentParser();ap.add_argument('--reference',type=Path,required=True);ap.add_argument('--candidate',type=Path,required=True);ap.add_argument('--reference-raw',type=Path,required=True);ap.add_argument('--candidate-raw',type=Path,required=True);a=ap.parse_args()
for name in ['cases.json']:
 if json.loads((a.reference/name).read_text())!=json.loads((a.candidate/name).read_text()):raise SystemExit(f'mismatch {name}')
r=json.loads((a.reference/'summary.json').read_text());c=json.loads((a.candidate/'summary.json').read_text())
for d in (r,c):d.pop('elapsed_seconds',None)
if r!=c:raise SystemExit('summary mismatch')
for p in sorted(a.reference_raw.glob('mode_*.csv')):
 q=a.candidate_raw/p.name
 if not q.exists() or p.read_bytes()!=q.read_bytes():raise SystemExit(f'raw mismatch {p.name}')
print(json.dumps({'status':'pass','raw_traces':len(list(a.reference_raw.glob('mode_*.csv'))),'case_records':len(json.loads((a.reference/'cases.json').read_text()))},indent=2))
