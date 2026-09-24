from itertools import product
import random,time,json,resource

def lcs(x,y,mask):
 a=[v&mask for v in x];b=[v&mask for v in y];old=[0]*(len(b)+1)
 for u in a:
  new=[0]
  for j,v in enumerate(b,1):new.append(max(old[j],new[-1],old[j-1]+int(u==v)))
  old=new
 return old[-1]

def frontier(x,y,mask,d):
 n=len(x); F=[[0]*(d+1) for _ in range(d+1)];W=[[None]*(d+1) for _ in range(d+1)]
 for a in range(d+1):
  for b in range(d+1):
   i=max(([F[a-1][b]+1] if a else [])+([F[a][b-1]] if b else [])+[0]);j=i-a+b
   while i<n and j<n and (x[i]&mask)==(y[j]&mask):i+=1;j+=1
   F[a][b]=i
   if i<n and j<n:
    diff=(x[i]^y[j])&mask;W[a][b]=(diff&-diff).bit_length()-1
 return F,W

def check(x,y,mask,d,F,W):
 n=len(x)
 for a in range(d+1):
  for b in range(d+1):
   u=F[a][b];v=u-a+b
   if not (a<=u<=n+d and b<=v):return False
   if a and u<F[a-1][b]+1:return False
   if b and u<F[a][b-1]:return False
   if u<n and v<n:
    p=W[a][b]
    if p is None or not (mask>>p)&1 or not ((x[u]^y[v])>>p)&1:return False
   elif W[a][b] is not None:return False
 return F[d][d]<n

t0=time.process_time();pairs=0;reduced=0
for n in range(1,5):
 ws=list(product(range(4),repeat=n))
 for ai,x in enumerate(ws):
  for y in ws[ai:]:
   for d in range(n):
    F,W=frontier(x,y,3,d); expected=lcs(x,y,3)<n-d
    assert (F[d][d]<n)==expected,(x,y,d,F)
    if expected:
     assert check(x,y,3,d,F,W)
     core=sum(1<<p for p in set(z for row in W for z in row if z is not None))
     assert core.bit_count()<=(d+1)**2
     assert lcs(x,y,core)<n-d
     if core!=3:reduced+=1
    pairs+=1
r=random.Random(1703)
for z in range(3000):
 n=r.randrange(1,40);m=r.randrange(1,33);d=r.randrange(min(n,5));mask=(1<<m)-1
 x=[r.randrange(1<<m) for _ in range(n)];y=x.copy()
 for _ in range(r.randrange(1,6)):
  y.pop(r.randrange(n));y.insert(r.randrange(n),r.randrange(1<<m))
 F,W=frontier(x,y,mask,d);expected=lcs(x,y,mask)<n-d
 assert (F[d][d]<n)==expected
 if expected:assert check(x,y,mask,d,F,W)
 pairs+=1
out={'pair_budget_checks':pairs,'strict_two_tap_core_reductions':reduced,'cpu_seconds':time.process_time()-t0,'peak_rss_kib':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,'workers':1,'result':'all assertions passed','scope':'exhaustive two-bit words lengths 1..4, unordered pairs including equal, d=0..n-1; 3000 seeded larger word pairs'}
print(json.dumps(out,indent=2));json.dump(out,open('results/kernel-pilot.json','w'),indent=2)
