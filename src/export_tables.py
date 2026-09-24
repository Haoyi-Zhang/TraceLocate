"""Export paper-ready deterministic data; no dependency on a manuscript tree."""
from __future__ import annotations
import argparse,csv,json
from pathlib import Path

def read_csv(path):
    with path.open() as f:return list(csv.DictReader(f))
def write_csv(path,rows):
    with path.open('w',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--out',type=Path,required=True);a=p.parse_args();a.out.mkdir(parents=True,exist_ok=True)
    rows=read_csv(Path('results/summary/sensitivity.csv'));coverage=[]
    for h in (4,8,12):
        z={'h':h}
        for d in (0,1,2):
            rs=[r for r in rows if int(r['d'])==d and int(r['h'])==h]
            z['loss'+str(d)]=sum(int(r['feasible']) for r in rs)
            assert sum(int(r['cases']) for r in rs)==48
        coverage.append(z)
    write_csv(a.out/'coverage.csv',coverage)
    mb=read_csv(Path('results/microbenchmark/summary.csv'))
    write_csv(a.out/'local-checking.csv',[r for r in mb if int(r['d'])==4])
    names={'arbiter':'Arbiter','counter':'Counter','credit':'Credit','fifo':'FIFO','handshake':'Handshake','lfsr':'Shift register'}
    lines=[]
    for r in read_csv(Path('results/summary/by-mechanism.csv')):
        model=json.loads(Path('models',r['mechanism']+'.json').read_text())
        n=max(len(v['table']) for v in model['variants'].values());init=max(len(v['initial']) for v in model['variants'].values())
        cost=r['min_cost'] if r['min_cost']==r['max_cost'] else r['min_cost']+'--'+r['max_cost']
        if cost=='NA':cost='---'
        lines.append(f"{names[r['mechanism']]} & {n} & {len(model['taps'])} & {len(model['classes'])} & {init} & {r['feasible']} & {r['max_pair_count']} & {cost} \\\\")
    (a.out/'mechanism-rows.tex').write_text('\n'.join(lines)+'\n')
    lines=[]
    bn={'deletion':'Full-grid oracle','none':'No-loss control','marked':'Marked-erasure control','marginal':'Marginal-tap control'}
    for r in read_csv(Path('results/summary/baselines.csv')):
        lines.append(f"{bn[r['method']]} & {r['declared_feasible']} & {r['actually_covered']} & {r['false_coverage']} & {r['missed_feasible']} \\\\")
    (a.out/'baseline-rows.tex').write_text('\n'.join(lines)+'\n')

    # Public-RTL bridge table and exact selected-interface inventory.
    rtl_model=json.loads(Path('models/uart-loopback-rtl.json').read_text())
    rtl_cases=[]
    for task in json.loads(Path('models/rtl-campaign.json').read_text())['cases']:
        rtl_cases.append(json.loads(Path('results/rtl-campaign/cases',task['id']+'.json').read_text()))
    groups=[]
    for h,d,off in [(16,0,[0]),(16,1,[0]),(24,0,[0]),(24,1,[0]),
                    (32,0,[0]),(32,1,[0]),(24,0,[0,1])]:
        rs=[r for r in rtl_cases if r['spec']['h']==h and r['spec']['d']==d and r['spec']['offsets']==off]
        assert len(rs)==4
        feasible=[r for r in rs if r['status']=='feasible']
        losses=sorted({r['full_minimum_loss'] for r in rs})
        costs=sorted({r['cost'] for r in feasible})
        cost_text='---' if not costs else (str(costs[0]) if len(costs)==1 else f'{costs[0]}--{costs[-1]}')
        loss_text=str(losses[0]) if len(losses)==1 else '/'.join(map(str,losses))
        groups.append({'h':h,'d':d,'offsets':','.join(map(str,off)),'cases':len(rs),
                       'feasible':len(feasible),'full_minimum_loss':loss_text,'optimum_cost':cost_text})
    write_csv(a.out/'rtl-bridge.csv',groups)
    rtl_lines=[]
    for r in groups:
        offset_tex=r'$\{0\}$' if r['offsets']=='0' else r'$\{0,1\}$'
        rtl_lines.append(f"{r['h']} & {r['d']} & {offset_tex} & {r['feasible']}/4 & {r['full_minimum_loss']} & {r['optimum_cost']} " + r"\\")
    (a.out/'rtl-rows.tex').write_text('\n'.join(rtl_lines)+'\n')
    inventory=[]
    for r in rtl_cases:
        names=[] if r['mask'] is None else [t['name'] for i,t in enumerate(rtl_model['taps']) if r['mask']>>i&1]
        tap_count=len(names) if r['mask'] is not None else None
        full_taps=len(rtl_model['taps']);h=r['spec']['h']
        inventory.append({'case':r['id'],'h':h,'d':r['spec']['d'],
                          'offsets':' '.join(map(str,r['spec']['offsets'])),
                          'contexts':' '.join(map(str,r['spec']['contexts'])),
                          'status':r['status'],'cost':r['cost'] if r['cost'] is not None else 'NA',
                          'full_minimum_loss':r['full_minimum_loss'],
                          'selected_taps':tap_count if tap_count is not None else 'NA',
                          'full_taps':full_taps,
                          'selected_capture_bits':tap_count*h if tap_count is not None else 'NA',
                          'full_capture_bits':full_taps*h,
                          'taps':'; '.join(names)})
    write_csv(a.out/'rtl-selected-interfaces.csv',inventory)
    print(json.dumps({'coverage_rows':len(coverage),'microbenchmark_rows':5,'model_rows':6,
                      'baseline_rows':4,'rtl_table_rows':len(groups),'rtl_cases':len(inventory)}))
if __name__=='__main__':main()
