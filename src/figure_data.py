"""Exact retained-data inputs for the coverage and local-checking plots."""
import csv
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]

def rows(root, relative):
    with (root/relative).open(encoding='utf-8',newline='') as f:
        return list(csv.DictReader(f))

def data(root=ROOT):
    sensitivity=rows(root,'results/summary/sensitivity.csv')
    counts=[]
    for h in (4,8,12):
        values=[]
        for d in range(3):
            group=[r for r in sensitivity if int(r['h'])==h and int(r['d'])==d]
            if sum(int(r['cases']) for r in group)!=48:
                raise ValueError('coverage denominator changed')
            values.append(sum(int(r['feasible']) for r in group))
        counts.append((h,*values))
    if counts!=[(4,9,6,2),(8,12,11,6),(12,14,13,12)]:
        raise ValueError('retained coverage values changed; review the manuscript')
    timing=[r for r in rows(root,'results/microbenchmark/summary.csv') if int(r['d'])==4]
    if [int(r['h']) for r in timing]!=[32,64,128,256,512] or any(int(r['local_records'])!=25 for r in timing):
        raise ValueError('retained timing-family identity changed')
    return counts,timing
