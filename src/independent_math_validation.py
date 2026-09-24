#!/usr/bin/env python3
"""Independent finite oracle for the paper's mathematical contract.

This module intentionally does not import the producer or certificate checker.
It validates the LCS/deletion equivalence, projection monotonicity, and exact
weighted interface search on bounded instances by direct enumeration.
"""
from __future__ import annotations
import argparse,itertools,json,random,time
from pathlib import Path

def lcs(a,b):
    prev=[0]*(len(b)+1)
    for x in a:
        cur=[0]
        for j,y in enumerate(b,1):
            cur.append(prev[j-1]+1 if x==y else max(prev[j],cur[-1]))
        prev=cur
    return prev[-1]

def subsequences_at_most_d(x,d):
    n=len(x); out=set()
    for k in range(d+1):
        for deleted in itertools.combinations(range(n),k):
            ds=set(deleted); out.add(tuple(x[i] for i in range(n) if i not in ds))
    return out

def collision_direct(a,b,d):
    return not subsequences_at_most_d(a,d).isdisjoint(subsequences_at_most_d(b,d))

def project_trace(trace,mask,m):
    idx=[i for i in range(m) if mask>>i&1]
    return tuple(tuple(row[i] for i in idx) for row in trace)

def feasible(pairs,mask,m,d):
    for a,b in pairs:
        pa,pb=project_trace(a,mask,m),project_trace(b,mask,m)
        if lcs(pa,pb)>=len(a)-d:return False
    return True

def exhaustive_opt(pairs,m,d,costs):
    best=None; bestmask=None; checked=0
    for mask in range(1<<m):
        c=sum(costs[i] for i in range(m) if mask>>i&1)
        if best is not None and c>=best:continue
        checked+=1
        if feasible(pairs,mask,m,d):best,bestmask=c,mask
    return best,bestmask,checked

def branch_opt(pairs,m,d,costs):
    # Exact monotone branch-and-bound; no fixed observation-count ceiling.
    full=(1<<m)-1
    if not feasible(pairs,full,m,d):return None,None,1
    order=sorted(range(m),key=lambda i:(costs[i],i))
    best=sum(costs);bestmask=full;nodes=0
    def rec(pos,mask,cost):
        nonlocal best,bestmask,nodes
        nodes+=1
        if cost>=best:return
        # If current mask works, record it and do not add more signals.
        if feasible(pairs,mask,m,d):best,bestmask=cost,mask;return
        if pos==m:return
        # Safe infeasibility prune: even all remaining signals cannot help.
        rem=mask
        for q in range(pos,m):rem|=1<<order[q]
        if not feasible(pairs,rem,m,d):return
        i=order[pos]
        rec(pos+1,mask,cost)
        rec(pos+1,mask|(1<<i),cost+costs[i])
    rec(0,0,0)
    return best,bestmask,nodes

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--out',type=Path,required=True);args=ap.parse_args()
    t=time.time();eq=0
    for h in range(1,7):
        seqs=list(itertools.product(range(2),repeat=h))
        for a in seqs:
            for b in seqs:
                for d in range(h):
                    direct=collision_direct(a,b,d)
                    criterion=lcs(a,b)>=h-d
                    if direct!=criterion:raise AssertionError((a,b,d,direct,criterion))
                    eq+=1
    mono=0
    # Exhaustive vector-row projection checks at bounded size.
    for h in range(1,5):
        rows=list(itertools.product(range(2),repeat=3))
        # deterministic prefix covers all one-row traces and a dense bounded sample later
        traces=list(itertools.product(rows,repeat=h))
        if len(traces)>256:traces=traces[:128]+traces[-128:]
        for a in traces:
            for b in traces:
                for small in range(1<<3):
                    for large in range(1<<3):
                        if small & ~large:continue
                        ls=lcs(project_trace(a,small,3),project_trace(b,small,3))
                        ll=lcs(project_trace(a,large,3),project_trace(b,large,3))
                        if ll>ls:raise AssertionError(('projection',a,b,small,large,ls,ll))
                        mono+=1
    rng=random.Random(20260920);opt=0;unsat=0
    for m in range(1,15):
        for rep in range(24):
            h=rng.randint(3,7);d=rng.randint(0,min(2,h-1));pairs=[]
            for _ in range(rng.randint(1,4)):
                a=tuple(tuple(rng.randrange(2) for _ in range(m)) for _ in range(h))
                b=tuple(tuple(rng.randrange(2) for _ in range(m)) for _ in range(h))
                pairs.append((a,b))
            costs=[rng.randint(1,7) for _ in range(m)]
            x=exhaustive_opt(pairs,m,d,costs);y=branch_opt(pairs,m,d,costs)
            if x[0]!=y[0] or (x[0] is not None and not feasible(pairs,y[1],m,d)):
                raise AssertionError(('opt',m,rep,x,y))
            if x[0] is None:unsat+=1
            opt+=1
    result={'status':'pass','lcs_deletion_equivalence_checks':eq,'projection_monotonicity_checks':mono,'weighted_optimality_instances':opt,'weighted_unsat_instances':unsat,'max_candidate_observations':14,'elapsed_seconds':round(time.time()-t,6)}
    args.out.parent.mkdir(parents=True,exist_ok=True);args.out.write_text(json.dumps(result,indent=2));print(json.dumps(result,indent=2))
if __name__=='__main__':main()
