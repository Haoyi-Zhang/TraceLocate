#!/usr/bin/env python3
from __future__ import annotations
import csv, hashlib, json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
PROJECT=ROOT.parent

def read_json(p:Path): return json.loads(p.read_text(encoding='utf-8'))
def read_jsonl(p:Path): return [json.loads(x) for x in p.read_text(encoding='utf-8').splitlines() if x.strip()]
def sha(p:Path): return hashlib.sha256(p.read_bytes()).hexdigest()
def stats(cases):
 return {
  'cases':len(cases),
  'feasible':sum(x['status']=='feasible' for x in cases),
  'infeasible':sum(x['status']=='infeasible' for x in cases),
  'zero_loss_aliases':sum(bool(x.get('full_interface_zero_loss_alias')) for x in cases),
 }

def ids(p:Path): return {x['case_id'] for x in read_json(p)['cases']}

finite=read_jsonl(ROOT/'results/cases.jsonl')
rtl=read_jsonl(ROOT/'results/rtl/cases.jsonl')
uart_ids=ids(ROOT/'models/uart-rtl-campaign.json')
arb_ids=ids(ROOT/'models/arbiter-rtl-campaign.json')
uart=[x for x in rtl if x['case_id'] in uart_ids]
arb=[x for x in rtl if x['case_id'] in arb_ids]
assert len(rtl)==len(uart)+len(arb) and uart_ids.isdisjoint(arb_ids)
S={'finite':stats(finite),'uart':stats(uart),'arbiter':stats(arb),'public_rtl':stats(rtl),'all_exact':stats(finite+rtl)}
expected={
 'finite':{'cases':432,'feasible':85,'infeasible':347,'zero_loss_aliases':327},
 'uart':{'cases':28,'feasible':12,'infeasible':16,'zero_loss_aliases':8},
 'arbiter':{'cases':24,'feasible':8,'infeasible':16,'zero_loss_aliases':8},
 'public_rtl':{'cases':52,'feasible':20,'infeasible':32,'zero_loss_aliases':16},
 'all_exact':{'cases':484,'feasible':105,'infeasible':379,'zero_loss_aliases':343},
}
assert S==expected,(S,expected)

models=[]
for name in ('uart-rtl.json','arbiter-rtl.json'):
 d=read_json(ROOT/'models'/name); models.append(d)
traces=sum(len(d['traces']) for d in models)
rows=sum(sum(len(t['values']) for t in d['traces']) for d in models)
scalar_samples=sum(sum(len(t['values'])*len(t['values'][0]) for t in d['traces']) for d in models)
assert (traces,rows,scalar_samples)==(60,2880,34560)

repro=read_json(ROOT/'results/final-reproduction-v2/reproduction-summary.json')
assert repro['status']=='passed'
assert repro['total_exact_cases']==484
assert repro['two_system_cases']==52

bibliography=read_json(ROOT/'literature/bibliography-verification.json')
fulltext=read_json(ROOT/'literature/fulltext-calibration.json')
assert bibliography['entries']>=55 and bibliography['verified']==bibliography['entries'] and not bibliography['unresolved']
assert fulltext['records']==22 and fulltext['categories']=={'adjacent':5,'closest':12,'influential':5}

oracle=read_json(ROOT/'results/exhaustive-small.json')
arb_mut=read_json(ROOT/'results/arbiter-bridge-mutations.json')
bridge_mut=read_json(ROOT/'results/bridge-mutations.json')
mutation=read_json(ROOT/'results/mutation-summary.json')
lcs=read_json(ROOT/'results/lcs-crosscheck.json')

extra={
 'public_rtl_systems':2,
 'public_rtl_traces':traces,
 'public_rtl_rows':rows,
 'public_rtl_scalar_samples':scalar_samples,
 'bibliography_entries':bibliography['entries'],
 'bibliography_verified':bibliography['verified'],
 'fulltext_records':fulltext['records'],
 'fulltext_unique_pdfs':fulltext['unique_pdfs'],
 'fulltext_closest':fulltext['categories']['closest'],
 'fulltext_influential':fulltext['categories']['influential'],
 'fulltext_adjacent':fulltext['categories']['adjacent'],
 'independent_selection_instances':oracle['selection_instances'],
 'independent_collision_checks':oracle['collision_equivalence_checks'],
 'independent_projection_checks':oracle['projection_monotonicity_checks'],
 'arbiter_bridge_mutations_rejected':arb_mut['rejected'],
 'uart_bridge_mutations_rejected':bridge_mut['rejected'],
 'certificate_mutations_rejected':mutation['rejected'],
 'bitparallel_grid_checks':lcs['comparisons'],
}
# Preserve published original validation counts where the retained reports name them.
for name,p,key in [
 ('explicit_subsequence_checks',ROOT/'results/subsequence-check.json','comparisons'),
 ('frontier_grid_checks',ROOT/'results/frontier-crosscheck.json','comparisons'),
 ('weighted_instances',ROOT/'results/weighted-summary.json','cases'),
 ('permutation_instances',ROOT/'results/permutation-summary.json','cases'),
 ('microbenchmarks',ROOT/'results/microbenchmarks.json','cases'),
]:
 if p.exists():
  d=read_json(p); extra[name]=d.get(key,d.get('count',d.get('instances',0)))

report={
 'schema':'final-evidence-v1','status':'passed','statistics':S,'validation':extra,
 'reproduction_summary_sha256':sha(ROOT/'results/final-reproduction-v2/reproduction-summary.json'),
 'bibliography_verification_sha256':sha(ROOT/'literature/bibliography-verification.json'),
 'fulltext_calibration_sha256':sha(ROOT/'literature/fulltext-calibration.json'),
}
rows_out=[]
for group,vals in S.items():
 for k,v in vals.items(): rows_out.append({'group':group,'metric':k,'value':v})
for k,v in extra.items(): rows_out.append({'group':'validation','metric':k,'value':v})
with (ROOT/'results/final-evidence.csv').open('w',newline='',encoding='utf-8') as f:
 w=csv.DictWriter(f,fieldnames=['group','metric','value']);w.writeheader();w.writerows(rows_out)

def cmd(name,val): return f"\\newcommand{{\\{name}}}{{{val:,}}}"
macros=[
 cmd('FiniteCases',S['finite']['cases']),cmd('FiniteFeasible',S['finite']['feasible']),cmd('FiniteInfeasible',S['finite']['infeasible']),cmd('FiniteAliases',S['finite']['zero_loss_aliases']),
 cmd('UARTCases',S['uart']['cases']),cmd('UARTFeasible',S['uart']['feasible']),cmd('UARTInfeasible',S['uart']['infeasible']),cmd('UARTAliases',S['uart']['zero_loss_aliases']),
 cmd('ArbiterCases',S['arbiter']['cases']),cmd('ArbiterFeasible',S['arbiter']['feasible']),cmd('ArbiterInfeasible',S['arbiter']['infeasible']),cmd('ArbiterAliases',S['arbiter']['zero_loss_aliases']),
 cmd('RTLCases',S['public_rtl']['cases']),cmd('RTLFeasible',S['public_rtl']['feasible']),cmd('RTLInfeasible',S['public_rtl']['infeasible']),cmd('RTLAliases',S['public_rtl']['zero_loss_aliases']),
 cmd('AllExactCases',S['all_exact']['cases']),cmd('AllExactFeasible',S['all_exact']['feasible']),cmd('AllExactInfeasible',S['all_exact']['infeasible']),cmd('AllExactAliases',S['all_exact']['zero_loss_aliases']),
 cmd('RTLSystems',2),cmd('RTLTraces',traces),cmd('RTLRows',rows),cmd('RTLScalarSamples',scalar_samples),
 cmd('BibliographyCount',bibliography['entries']),cmd('FulltextCount',fulltext['records']),
 cmd('ExhaustiveSelectionInstances',oracle['selection_instances']),cmd('ExhaustiveCollisionChecks',oracle['collision_equivalence_checks']),cmd('ExhaustiveProjectionChecks',oracle['projection_monotonicity_checks']),
]
gen=PROJECT/'paper/generated';gen.mkdir(parents=True,exist_ok=True)
(gen/'final-stats.tex').write_text('% generated by artifact/src/finalize_evidence.py\n'+'\n'.join(macros)+'\n')
print(json.dumps(report,indent=2,sort_keys=True))
