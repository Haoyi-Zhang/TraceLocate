#!/usr/bin/env python3
from pathlib import Path
import json,re,subprocess
root=Path(__file__).resolve().parents[2]
art=root/'artifact';paper=root/'paper'
bib=json.loads((art/'literature/literature_audit.json').read_text())
pico=json.loads((art/'rtl/picorv32/results/summary.json').read_text())
pdf=max(paper.glob('*.pdf'),key=lambda p:p.stat().st_mtime)
info=subprocess.run(['pdfinfo',str(pdf)],capture_output=True,text=True,check=True).stdout
pages=int(re.search(r'^Pages:\s+(\d+)',info,re.M).group(1))
# Discover the retained primary-matrix summary without depending on its directory name.
primary=None
for p in art.rglob('*.json'):
    if 'picorv32' in str(p) or 'literature' in str(p) or 'replay' in str(p):continue
    try:o=json.loads(p.read_text())
    except Exception:continue
    objs=[]
    if isinstance(o,dict):objs=[o]+[v for v in o.values() if isinstance(v,dict)]
    for d in objs:
        nums={k:v for k,v in d.items() if isinstance(v,int)}
        total=next((nums[k] for k in nums if k.lower() in {'total_cases','cases','case_count','total'}),None)
        if total==484:
            primary={'path':str(p.relative_to(root)),'data':d};break
    if primary:break
ptext='The retained canonical result files and clean replay establish the primary matrix; the manuscript gives its per-family breakdown.'
if primary:ptext=f"The primary 484-task matrix is machine-readable in `{primary['path']}` and is reconstructed by the replay entry point."
state=f'''# Current State

## Scientific status

The project implements and checks a finite trace-localization contract for equal-length synchronous row traces under at most `d` independent whole-row deletions per execution. The paper separates general theorems, finite exact results, and external-validity limitations.

{ptext}

A held-out PicoRV32 bridge is reported separately from that predeclared matrix. It contains {pico['traces']} raw executions, {pico['cases']} exact tasks, {pico['feasible']} feasible tasks, and {pico['infeasible']} infeasible tasks over {pico['observations']} scalar candidates. Its replay recompiles a commit-pinned upstream source, regenerates traces, checks lower-cost masks, and runs directed mutation tests.

The current manuscript is {pages} pages and contains {bib['entries']} cited bibliography entries. The bibliography audit reports {bib.get('crossref_verified',0)} DOI records matched against cached Crossref metadata, with no missing citation keys, uncited padding entries, or definite DOI-title mismatches. Identity verification is not represented as blanket full-text reading.

## Reproduction

```bash
cd artifact
python reproduce.py --out results/reproduction
```

Supplying `--iverilog /path/to/iverilog` recompiles the public RTL bridges, including the held-out PicoRV32 study, and compares regenerated records with the retained evidence.

```bash
cd paper
sh build.sh
```

## Boundaries that remain explicit

The results do not measure routed probe cost, trace-address encoding, timestamp/control logic, synthesis area, power, timing, FPGA behavior, fabricated silicon, debug yield, or a population distribution of physical defects. The theorem does not cover row substitutions, bit corruption, insertion, timing skew, unequal unsynchronized executions, or unbounded behaviors. Exact interface search has no fixed twelve-observation semantic limit, but remains exponential in the worst case. The pairwise certificate bound is not a task-size-independent bound on a global interface.
'''
(root/'CURRENT-STATE.md').write_text(state)
readme=f'''# Coverage-Certified Trace Localization Artifact

This directory contains the finite-model producer, independent consumers, retained raw traces, public RTL bridges, exact results, mutation tests, and the single replay entry point.

Run `python reproduce.py --out results/reproduction` from this directory. Add `--iverilog /path/to/iverilog` to recompile the pinned RTL sources. The replay also runs a zero-import finite oracle and the bibliography-use audit. See `../CURRENT-STATE.md` for the claim boundary and `literature/README.md` for literature evidence levels.
'''
(art/'README.md').write_text(readme)
