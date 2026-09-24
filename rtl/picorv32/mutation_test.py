#!/usr/bin/env python3
from __future__ import annotations
import csv,json,shutil,subprocess,sys,tempfile
from pathlib import Path
root=Path(__file__).resolve().parent
checker=root/'check_bridge.py'
base_cases=json.loads((root/'results/cases.json').read_text())
feas=next((x for x in base_cases if x['status']=='feasible'),None)
infeas=next((x for x in base_cases if x['status']=='infeasible'),None)
mutations=[]

def run_mut(name,mutator):
    with tempfile.TemporaryDirectory(prefix='pico-mut-') as td:
        td=Path(td);res=td/'results';raw=td/'raw';shutil.copytree(root/'results',res);shutil.copytree(root/'raw',raw);mutator(res,raw)
        cp=subprocess.run([sys.executable,str(checker),'--root',str(root),'--results',str(res),'--raw',str(raw)],capture_output=True,text=True)
        cmp=subprocess.run([sys.executable,str(root/'compare_bridge.py'),'--reference',str(root/'results'),'--candidate',str(res),'--reference-raw',str(root/'raw'),'--candidate-raw',str(raw)],capture_output=True,text=True)
        if cp.returncode==0 and cmp.returncode==0:raise AssertionError(f'mutation accepted: {name}')
        mutations.append({'name':name,'rejected':True,'checker_rejected':cp.returncode!=0,'replay_compare_rejected':cmp.returncode!=0})

def flip_raw(res,raw):
    p=raw/'mode_1.csv';rows=list(csv.reader(p.open()));rows[2][2]='1' if rows[2][2]=='0' else '0';
    with p.open('w',newline='') as f:csv.writer(f).writerows(rows)
def empty_witness(res,raw):
    xs=json.loads((res/'cases.json').read_text());x=next(z for z in xs if z['status']=='feasible');x['selected']=[];x['cost']=0;(res/'cases.json').write_text(json.dumps(xs))
def lower_cost(res,raw):
    xs=json.loads((res/'cases.json').read_text());x=next(z for z in xs if z['status']=='feasible');x['cost']=max(0,x['cost']-1);(res/'cases.json').write_text(json.dumps(xs))
def wrong_mode(res,raw):
    xs=json.loads((res/'cases.json').read_text());x=xs[0];x['fault_mode']=((x['fault_mode'])%6)+1;(res/'cases.json').write_text(json.dumps(xs))
def false_infeasible(res,raw):
    xs=json.loads((res/'cases.json').read_text());x=next(z for z in xs if z['status']=='feasible');x['status']='infeasible';x['selected']=[];x['cost']=None;(res/'cases.json').write_text(json.dumps(xs))
for name,fn in [('raw-bit-flip',flip_raw),('empty-witness',empty_witness),('lower-claimed-cost',lower_cost),('wrong-fault-member',wrong_mode),('false-infeasible',false_infeasible)]:run_mut(name,fn)
out={'status':'pass','mutations':mutations,'rejected':len(mutations)}
(root/'results/mutation_test.json').write_text(json.dumps(out,indent=2));print(json.dumps(out,indent=2))
