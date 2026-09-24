"""Bounded trace-language synthesis. Standard library; no external solver.

The consumer in check_certificate.py deliberately imports none of this module.
Rows are packed binary tap vectors; bit p belongs to tap p. Loss deletes an
entire row, with no timestamp. Distinct known contexts are never compared.
"""
from __future__ import annotations
from itertools import combinations
from typing import Any, Iterable

Word = tuple[int, ...]
Pair = tuple[tuple[int, int, int, int, int], Word, Word]


def languages(model: dict[str, Any], spec: dict[str, Any]) -> list[list[list[Word]]]:
    """Enumerate precisely the declared deterministic Mealy-model behaviors."""
    h = spec['h']; offsets = spec['offsets']; result = []
    for ci in spec['contexts']:
        stimulus = model['contexts'][ci]['inputs']
        groups = []
        for cls in model['classes']:
            words: set[Word] = set()
            for vn in cls['variants']:
                variant = model['variants'][vn]
                for initial in variant['initial']:
                    q = initial; rows = []
                    for inp in stimulus[:h + max(offsets)]:
                        edge = variant['table'][q][inp]
                        rows.append(edge['row']); q = edge['next']
                    for off in offsets:
                        words.add(tuple(rows[off:off+h]))
            groups.append(sorted(words))
        result.append(groups)
    return result


def pairs(ls: list[list[list[Word]]]) -> list[Pair]:
    out = []
    for ci, groups in enumerate(ls):
        for a, b in combinations(range(len(groups)), 2):
            for i, x in enumerate(groups[a]):
                for j, y in enumerate(groups[b]):
                    out.append(((ci,a,i,b,j),x,y))
    return out


def grid(x: Word, y: Word, mask: int) -> list[list[int]]:
    """Classical LCS grid, used by the producer/oracle baseline, not checker."""
    g = [[0]*(len(y)+1) for _ in range(len(x)+1)]
    for i, u in enumerate(x, 1):
        for j, v in enumerate(y, 1):
            g[i][j] = max(g[i-1][j],g[i][j-1],g[i-1][j-1]+int(((u^v)&mask)==0))
    return g




def lcs_length(x: Word, y: Word, mask: int) -> int:
    """Exact LCS length via the bit-parallel row-update identity.

    This is used only by the exhaustive baseline.  The producer's proof
    objects still come from the deletion frontier, and minimum-loss witnesses
    retain the ordinary dynamic-programming grid for an explicit alignment.
    Python integers supply an unbounded bit vector, so the result is exact.
    """
    positions: dict[int, int] = {}
    for j, value in enumerate(y):
        symbol = value & mask
        positions[symbol] = positions.get(symbol, 0) | (1 << j)
    state = 0
    for value in x:
        matches = positions.get(value & mask, 0)
        merged = matches | state
        state = merged & ~(merged - ((state << 1) | 1))
    return state.bit_count()

def alignment(x: Word, y: Word, mask: int, g: list[list[int]]|None=None) -> list[list[int]]:
    if g is None: g=grid(x,y,mask)
    i=len(x); j=len(y); out=[]
    while i and j:
        if not ((x[i-1]^y[j-1])&mask) and g[i][j] == g[i-1][j-1]+1:
            out.append([i-1,j-1]); i-=1;j-=1
        elif g[i-1][j] >= g[i][j-1]: i-=1
        else: j-=1
    return list(reversed(out))


def frontier(x: Word, y: Word, mask: int, d: int) -> dict[str, Any]:
    """Generate a quadratic loss-frontier blocking certificate.

    The integer at (a,b) is a furthest x-prefix after a x-deletions and
    b y-deletions. Outside both finite words, symbols are disjoint sentinels:
    virtual deletions are allowed but no virtual matching edge is allowed.
    At an in-range stopping point record one selected differing tap.
    The consumer checks upper-bound inequalities, not this recurrence or snakes.
    """
    h=len(x); upper=[[0]*(d+1) for _ in range(d+1)]
    taps: list[list[int|None]]=[[None]*(d+1) for _ in range(d+1)]
    for a in range(d+1):
        for b in range(d+1):
            seeds=[0]
            if a: seeds.append(upper[a-1][b]+1)
            if b: seeds.append(upper[a][b-1])
            i=max(seeds);j=i-a+b
            while i<h and j<h and ((x[i]^y[j])&mask)==0:
                i+=1;j+=1
            upper[a][b]=i
            if i<h and j<h:
                different=(x[i]^y[j])&mask
                taps[a][b]=(different & -different).bit_length()-1
    return {'upper':upper,'taps':taps}


def is_separated(x: Word,y: Word,mask: int,d:int) -> bool:
    return frontier(x,y,mask,d)['upper'][d][d] < len(x)


def cost(mask: int, costs: list[int]) -> int:
    return sum(w for i,w in enumerate(costs) if mask>>i&1)


def ranked_masks(costs: list[int]) -> list[int]:
    return sorted(range(1<<len(costs)),key=lambda s:(cost(s,costs),s.bit_count(),s))


def obstruction(pair: Pair, mask: int, d: int) -> dict[str, Any]:
    pid,x,y=pair;k=len(x)-d
    a=alignment(x,y,mask)[:k]
    if len(a)!=k:raise ValueError('requested a collision for a separated pair')
    clause=0
    for i,j in a:clause |= x[i]^y[j]
    return {'pair':list(pid),'alignment':a,'clause':clause}


def coverage(ps: list[Pair],mask:int,d:int) -> list[dict[str,Any]]:
    out=[]
    for pid,x,y in ps:
        c=frontier(x,y,mask,d)
        if c['upper'][d][d]>=len(x):raise ValueError('non-covering mask')
        out.append({'pair':list(pid),**c})
    return out


def minimum_loss(ps: list[Pair],mask:int) -> dict[str,Any]:
    """Exact smallest per-trace loss at fixed horizon and tap set.

    A longest cross-class alignment witnesses the upper bound on loss. A
    frontier certificate for every pair one budget below proves minimality.
    """
    h=len(ps[0][1]);largest=-1;best=None
    for pair in ps:
        g=grid(pair[1],pair[2],mask)
        if g[-1][-1]>largest:
            largest=g[-1][-1];best=(pair,alignment(pair[1],pair[2],mask,g))
    assert best is not None
    d=h-largest;pair,a=best
    return {'loss':d,'mask':mask,'pair':list(pair[0]),'alignment':a,
            'below':coverage(ps,mask,d-1) if d else []}


def synthesize(model:dict[str,Any],spec:dict[str,Any]) -> tuple[dict[str,Any],dict[str,Any]]:
    ls=languages(model,spec);ps=pairs(ls);h=spec['h'];d=spec['d']
    costs=[t['cost'] for t in model['taps']];full=(1<<len(costs))-1
    if len(costs)>12:raise ValueError('exact synthesis is bounded to 12 taps')
    full_margin=minimum_loss(ps,full)
    stats={'contexts':len(ls),'classes':len(model['classes']),
           'traces':sum(len(g) for c in ls for g in c),'pairs':len(ps),
           'candidate_checks':0,'pair_checks':0,'clauses':0,'frontier_cells':0}
    base={'model':model['name'],'spec':spec.copy(),'full_margin':full_margin}
    if full_margin['loss']<=d:
        return {**base,'status':'infeasible','mask':None,'cost':None,
                'obstructions':[],'coverage':[]},stats
    clauses=[];seen=set();ranked=ranked_masks(costs)
    for iteration in range(1<<len(costs)):
        candidate=next(s for s in ranked if all(s&c['clause'] for c in clauses))
        if candidate in seen:raise AssertionError('counterexample failed to exclude candidate')
        seen.add(candidate);stats['candidate_checks']+=1
        bad=None
        for pair in ps:
            stats['pair_checks']+=1
            if not is_separated(pair[1],pair[2],candidate,d):bad=pair;break
        if bad is None:
            cov=coverage(ps,candidate,d)
            stats['clauses']=len(clauses);stats['frontier_cells']=len(cov)*(d+1)**2
            return {**base,'status':'feasible','mask':candidate,'cost':cost(candidate,costs),
                    'obstructions':clauses,'coverage':cov},stats
        witness=obstruction(bad,candidate,d)
        if not witness['clause']:raise AssertionError('contradiction with full-tap margin')
        clauses.append(witness)
    raise AssertionError('finite refinement failed to terminate')


def exhaustive_optimum(ps:list[Pair],costs:list[int],d:int,mode:str='deletion') -> tuple[int|None,int]:
    checks=0
    for mask in ranked_masks(costs):
        good=True
        for _,x,y in ps:
            checks+=1
            if mode=='marked':
                distinct=sum(bool((u^v)&mask) for u,v in zip(x,y))
                sep=distinct>d
            elif mode=='marginal':
                sep=any(lcs_length(x,y,1<<p)<len(x)-d for p in range(len(costs)) if mask>>p&1)
            elif mode=='none':sep=any((u^v)&mask for u,v in zip(x,y))
            else:sep=lcs_length(x,y,mask)<len(x)-d
            if not sep:good=False;break
        if good:return mask,checks
    return None,checks
