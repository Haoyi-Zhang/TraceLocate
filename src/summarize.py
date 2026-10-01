"""Validate complete experiment membership and regenerate claim-linked tables."""
from __future__ import annotations
import argparse,collections,csv,json,statistics
from pathlib import Path
from check_certificate import validate


def csv_write(path,rows):
    with path.open('w',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--root',type=Path,default=Path('.'))
    p.add_argument('--results',type=Path,default=Path('results/campaign'))
    p.add_argument('--out',type=Path,default=Path('results/summary'))
    p.add_argument('--instance',type=Path,default=Path('models/campaign.json'))
    args=p.parse_args();root=args.root.resolve()
    results=args.results if args.results.is_absolute() else root/args.results
    out=args.out if args.out.is_absolute() else root/args.out
    instance=args.instance if args.instance.is_absolute() else root/args.instance
    out.mkdir(parents=True,exist_ok=True)
    tasks=json.loads(instance.read_text())['cases'];models={}
    expected={c['id'] for c in tasks};actual={f.stem for f in (results/'cases').glob('*.json')}
    assert actual==expected,('missing or extra cases',expected-actual,actual-expected)
    assert {f.stem for f in (results/'certificates').glob('*.json')}==expected
    data=[]
    for task in tasks:
        ident=task['id'];mn=task['model']
        if mn not in models:models[mn]=json.loads((root/'models'/(mn+'.json')).read_text())
        r=json.loads((results/'cases'/(ident+'.json')).read_text())
        c=json.loads((results/'certificates'/(ident+'.json')).read_text())
        v=validate(models[mn],task['spec'],c)
        assert r['spec']==task['spec'] and r['model']==mn and r['id']==ident
        assert v==r['verified'] and r['cost']==c['cost'] and r['status']==c['status']
        assert r['cost']==r['baselines']['deletion']['cost']
        data.append(r)
    by=[]
    for name in sorted(models):
        rs=[r for r in data if r['model']==name];fe=[r for r in rs if r['status']=='feasible']
        row={'mechanism':name,'cases':len(rs),'feasible':len(fe),'infeasible':len(rs)-len(fe),
             'zero_loss_infeasible':sum(r['full_minimum_loss']==0 for r in rs),
             'min_cost':min((r['cost'] for r in fe),default='NA'),'max_cost':max((r['cost'] for r in fe),default='NA'),
             'max_pair_count':max(r['stats']['pairs'] for r in rs),
             'max_candidate_checks':max(r['stats']['candidate_checks'] for r in rs),
             'max_pair_core':max(r['verified'].get('max_pair_core',0) for r in rs),
             'no_loss_false_coverage':sum(r['baselines']['none']['mask'] is not None and not r['baselines']['none']['true_coverage'] for r in rs),
             'marked_false_coverage':sum(r['baselines']['marked']['mask'] is not None and not r['baselines']['marked']['true_coverage'] for r in rs),
             'marginal_missed_feasible':sum(r['status']=='feasible' and r['baselines']['marginal']['mask'] is None for r in rs),
             'total_case_cpu_seconds':sum(r['metrics']['cpu_seconds'] for r in rs)}
        by.append(row)
    csv_write(out/'by-mechanism.csv',by)
    sensitivity=[]
    for d in sorted({r['spec']['d'] for r in data}):
        for h in sorted({r['spec']['h'] for r in data}):
            for o in sorted({len(r['spec']['offsets']) for r in data}):
                rs=[r for r in data if r['spec']['d']==d and r['spec']['h']==h and len(r['spec']['offsets'])==o]
                sensitivity.append({'d':d,'h':h,'offset_count':o,'cases':len(rs),'feasible':sum(r['status']=='feasible' for r in rs)})
    csv_write(out/'sensitivity.csv',sensitivity)
    baselines=[]
    for mode in ('deletion','none','marked','marginal'):
        chosen=[r for r in data if r['baselines'][mode]['mask'] is not None]
        baselines.append({'method':mode,'declared_feasible':len(chosen),'actually_covered':sum(r['baselines'][mode]['true_coverage'] for r in chosen),
                          'false_coverage':sum(not r['baselines'][mode]['true_coverage'] for r in chosen),
                          'missed_feasible':sum(r['status']=='feasible' and r['baselines'][mode]['mask'] is None for r in data),
                          'above_true_minimum':sum(r['status']=='feasible' and r['baselines'][mode]['cost'] is not None and r['baselines'][mode]['cost']>r['cost'] for r in data),
                          'cpu_seconds':sum(r['baselines'][mode]['cpu_seconds'] for r in data)})
    csv_write(out/'baselines.csv',baselines)

    # Exact per-case interface widths.  Every declared tap is one captured bit;
    # weighted cost remains a separate abstract installation cost.
    interfaces=[]
    for r in data:
        full_taps=len(models[r['model']]['taps'])
        selected=None if r['mask'] is None else int(r['mask']).bit_count()
        h=r['spec']['h']
        interfaces.append({
            'case':r['id'], 'model':r['model'], 'h':h, 'status':r['status'],
            'selected_taps':selected if selected is not None else 'NA',
            'full_taps':full_taps,
            'selected_capture_bits':selected*h if selected is not None else 'NA',
            'full_capture_bits':full_taps*h,
            'selected_fraction':f'{selected/full_taps:.6f}' if selected is not None else 'NA'
        })
    csv_write(out/'interfaces.csv',interfaces)

    runs=[json.loads(p.read_text()) for p in (results/'runs').glob('*.json')]
    all_run_ids=[i for r in runs for i in r['cases']]
    assert sorted(all_run_ids)==sorted(expected),'run metadata does not partition the campaign'
    summary={'cases':len(data),'feasible':sum(r['status']=='feasible' for r in data),'infeasible':sum(r['status']=='infeasible' for r in data),
             'zero_loss_infeasible':sum(r['full_minimum_loss']==0 for r in data),'certificate_checks':len(data),
             'max_pairs':max(r['stats']['pairs'] for r in data),'max_candidates':max(r['stats']['candidate_checks'] for r in data),
             'certificate_min_bytes':min(r['certificate_bytes'] for r in data),'certificate_max_bytes':max(r['certificate_bytes'] for r in data),
             'campaign_cpu_seconds':sum(r['cpu_seconds'] for r in runs),'campaign_wall_seconds':sum(r['wall_seconds'] for r in runs),
             'process_peak_rss_kib':max(r['process_peak_rss_kib'] for r in runs),'workers':1,
             'producer_cpu_seconds':sum(r['metrics']['producer_cpu_seconds'] for r in data),
             'checker_cpu_seconds':sum(r['metrics']['checker_cpu_seconds'] for r in data),
             'full_minimum_loss_distribution':dict(sorted(collections.Counter(r['full_minimum_loss'] for r in data).items())),
             'selected_tap_count_distribution':dict(sorted(collections.Counter(int(r['mask']).bit_count() for r in data if r['mask'] is not None).items())),
             'selected_capture_bits_min':min((int(r['mask']).bit_count()*r['spec']['h'] for r in data if r['mask'] is not None),default=None),
             'selected_capture_bits_max':max((int(r['mask']).bit_count()*r['spec']['h'] for r in data if r['mask'] is not None),default=None)}
    (out/'summary.json').write_text(json.dumps(summary,indent=2)+'\n');print(json.dumps(summary,sort_keys=True))
if __name__=='__main__':main()
