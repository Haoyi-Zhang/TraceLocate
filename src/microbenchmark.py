"""Reproducible pair-check microbenchmark, not a hardware performance benchmark."""
from __future__ import annotations
import argparse,csv,json,resource,statistics,time
from pathlib import Path
from trace_engine import frontier,grid
from check_certificate import verify_frontier


def trial(fn,reps):
    times=[]
    for _ in range(5):
        t=time.process_time()
        for _ in range(reps):fn()
        times.append((time.process_time()-t)/reps)
    return times


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--out',type=Path,default=Path('results/microbenchmark'))
    args=p.parse_args();args.out.mkdir(parents=True,exist_ok=True)
    start=time.process_time();startw=time.perf_counter();rows=[];raw=[]
    for d in (1,2,3,4):
        h0=d+1;m=2*d+1;v=[(1<<k)-1 for k in range(2*h0)];full=(1<<m)-1
        for h in (32,64,128,256,512):
            x=tuple([0]*(h-h0)+v[::2]);y=tuple([0]*(h-h0)+v[1::2])
            proof=frontier(x,y,full,d);core=verify_frontier(x,y,full,d,proof,m)
            assert core==full
            # Slow full-grid LCS is a correctness/reference baseline, not state of the art.
            assert grid(x,y,full)[-1][-1]==h-h0
            ck=trial(lambda:verify_frontier(x,y,full,d,proof,m),100)
            fr=trial(lambda:frontier(x,y,full,d),50)
            lc=trial(lambda:grid(x,y,full),max(1,512//h))
            row={'h':h,'d':d,'m':m,'local_records':(d+1)**2,'lcs_grid_cells':(h+1)**2,
                 'proof_json_bytes':len(json.dumps(proof,separators=(',',':')).encode()),
                 'kernel_taps':core.bit_count(),'checker_median_us':statistics.median(ck)*1e6,
                 'frontier_median_us':statistics.median(fr)*1e6,'lcs_median_us':statistics.median(lc)*1e6}
            rows.append(row);raw.append({'h':h,'d':d,'checker_trials_seconds':ck,'frontier_trials_seconds':fr,'lcs_trials_seconds':lc})
    with (args.out/'summary.csv').open('w',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
    result={'instances':raw,'design':'fixed essential-tap family with identical prefix padding; no random input selection',
            'timing':'five process-CPU batches; medians in CSV; construction and proof serialization excluded from check timing',
            'scope':'indexed pair verification only; excludes model replay, complete pair enumeration and interface optimization',
            'cpu_seconds':time.process_time()-start,'wall_seconds':time.perf_counter()-startw,
            'process_peak_rss_kib':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,'workers':1}
    (args.out/'raw.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({'cases':len(rows),'cpu_seconds':result['cpu_seconds'],'process_peak_rss_kib':result['process_peak_rss_kib']}))
if __name__=='__main__':main()
