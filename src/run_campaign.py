"""Bounded, resumable, single-worker experiment runner; no network access."""
from __future__ import annotations
import argparse,json,time,resource
from pathlib import Path
from trace_engine import languages,pairs,synthesize,exhaustive_optimum,grid,cost
from check_certificate import validate


def write_json(path:Path,obj):
    # Pin the evidence serialization, not the host's default text newline.
    tmp=path.with_suffix(path.suffix+'.tmp')
    tmp.write_text(json.dumps(obj,separators=(',',':'))+'\n',encoding='utf-8',newline='\n')
    tmp.replace(path)


def run_one(root:Path,case:dict,out:Path):
    model=json.loads((root/'models'/(case['model']+'.json')).read_text());spec=case['spec']
    begin_wall=time.perf_counter();begin_cpu=time.process_time()
    certificate,stats=synthesize(model,spec)
    producer_cpu=time.process_time()-begin_cpu
    t=time.process_time();verified=validate(model,spec,certificate);checker_cpu=time.process_time()-t
    costs=[t['cost'] for t in model['taps']];ps=pairs(languages(model,spec));h=spec['h'];d=spec['d']
    baseline={}
    for mode in ('deletion','none','marked','marginal'):
        t=time.process_time();bm,nchecks=exhaustive_optimum(ps,costs,d,mode)
        elapsed=time.process_time()-t
        actual=(bm is not None and all(grid(x,y,bm)[-1][-1]<h-d for _,x,y in ps))
        baseline[mode]={'mask':bm,'cost':cost(bm,costs) if bm is not None else None,
                        'true_coverage':actual,'pair_checks':nchecks,'cpu_seconds':elapsed}
    exact=baseline['deletion']['cost']
    assert certificate['cost']==exact, (case['id'],certificate['cost'],exact)
    if certificate['status']=='feasible':
        assert baseline['deletion']['true_coverage']
    result={'id':case['id'],'model':case['model'],'spec':spec,'status':certificate['status'],
            'mask':certificate['mask'],'cost':certificate['cost'],'full_minimum_loss':certificate['full_margin']['loss'],
            'stats':stats,'verified':verified,'baselines':baseline,
            'metrics':{'producer_cpu_seconds':producer_cpu,'checker_cpu_seconds':checker_cpu,
                       'cpu_seconds':time.process_time()-begin_cpu,'wall_seconds':time.perf_counter()-begin_wall,
                       'process_peak_rss_kib':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,'workers':1}}
    write_json(out/'certificates'/(case['id']+'.json'),certificate)
    result['certificate_bytes']=(out/'certificates'/(case['id']+'.json')).stat().st_size
    write_json(out/'cases'/(case['id']+'.json'),result)
    return result


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--root',type=Path,default=Path('.'));p.add_argument('--out',type=Path,default=Path('results/campaign'))
    p.add_argument('--instance',type=Path,default=Path('models/campaign.json'))
    p.add_argument('--model');p.add_argument('--resume',action='store_true');p.add_argument('--seconds',type=float,default=25.)
    p.add_argument('--limit',type=int);args=p.parse_args()
    for name in ('cases','certificates','runs'):(args.out/name).mkdir(parents=True,exist_ok=True)
    instance=args.instance if args.instance.is_absolute() else args.root/args.instance
    campaign=json.loads(instance.read_text());todo=[c for c in campaign['cases'] if not args.model or c['model']==args.model]
    start=time.perf_counter();start_cpu=time.process_time();done=[];skipped=0
    for case in todo:
        if args.resume and (args.out/'cases'/(case['id']+'.json')).exists():skipped+=1;continue
        if done and (time.perf_counter()-start>=args.seconds or (args.limit and len(done)>=args.limit)):break
        result=run_one(args.root,case,args.out);done.append(case['id'])
        print(json.dumps({'case':case['id'],'status':result['status'],'cost':result['cost'],'cpu':round(result['metrics']['cpu_seconds'],6)}),flush=True)
    run={'cases':done,'skipped':skipped,'requested_cases':len(todo),'cpu_seconds':time.process_time()-start_cpu,
         'wall_seconds':time.perf_counter()-start,'process_peak_rss_kib':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
         'workers':1,'instance':str(args.instance),
         'stop_policy':'check seconds boundary between atomic cases; exact selection is bounded to 12 taps; horizon bounds are declared by the selected instance'}
    runfile='chunk-'+str(len(list((args.out/'runs').glob('*.json')))+1)+'.json'
    write_json(args.out/'runs'/runfile,run);print(json.dumps({'run_summary':run}),flush=True)
if __name__=='__main__':main()
