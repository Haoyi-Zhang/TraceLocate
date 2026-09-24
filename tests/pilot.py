from itertools import product,combinations
from time import process_time,perf_counter
import json,resource

def lcs(a,b):
 d=[[0]*(len(b)+1) for _ in range(len(a)+1)]
 for i,x in enumerate(a,1):
  for j,y in enumerate(b,1):d[i][j]=max(d[i-1][j],d[i][j-1],d[i-1][j-1]+(x==y))
 return d[-1][-1]
def subseqs(a,k):return {tuple(a[i] for i in I) for I in combinations(range(len(a)),k)}
t0=perf_counter();c0=process_time();checks=0
for n in range(1,5):
 words=list(product(range(2),repeat=n))
 for a in words:
  for b in words:
   for d in range(n+1):
    assert bool(subseqs(a,n-d)&subseqs(b,n-d))==(lcs(a,b)>=n-d)
    checks+=1
words=list(product(range(4),repeat=3));correlation=None;timing=None
for a in words:
 for b in words:
  joint=lcs(a,b)
  separate=[lcs(tuple((x>>p)&1 for x in a),tuple((x>>p)&1 for x in b)) for p in range(2)]
  if correlation is None and min(separate)>=2 and joint<2:correlation={'a':a,'b':b,'joint_lcs':joint,'per_tap_lcs':separate,'h':3,'d':1}
  ham=sum(x!=y for x,y in zip(a,b))
  if timing is None and ham>1 and joint>=2:timing={'a':a,'b':b,'hamming_distance':ham,'joint_lcs':joint,'h':3,'d':1}
assert correlation and timing
out={'oracle_comparisons':checks,'correlation_counterexample':correlation,'timestamp_counterexample':timing,'workers':1,'wall_seconds':perf_counter()-t0,'cpu_seconds':process_time()-c0,'peak_rss_kib':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,'scope':'binary words length 1..4; two-tap words length 3; no device observations'}
print(json.dumps(out,indent=2));open('results/pilot.json','w').write(json.dumps(out,indent=2)+'\n')
