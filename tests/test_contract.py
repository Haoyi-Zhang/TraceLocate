"""Finite independent oracles and semantically invalid certificate mutations.

This suite is not a theorem prover. Its small oracle constructs subsequences
explicitly rather than implementing the producer's LCS/frontier recurrence.
"""
from __future__ import annotations
import copy,itertools,json,random,resource,sys,time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from trace_engine import synthesize,frontier,grid,lcs_length,exhaustive_optimum,languages,pairs,minimum_loss
from check_certificate import validate,verify_frontier,InvalidCertificate


def words_model(words,costs):
    h=len(words[0]);vs={}
    for i,w in enumerate(words):
        vs[str(i)]={'initial':[0],'table':[[{'next':min(q+1,h-1),'row':v}] for q,v in enumerate(w)]}
    return {'name':'word_fixture','taps':[{'name':f'tap{p}','cost':c} for p,c in enumerate(costs)],
            'variants':vs,'classes':[{'name':f'class{i}','variants':[str(i)]} for i in range(len(words))],
            'contexts':[{'name':'fixed','inputs':[0]*h}]}


def subs(word,mask,k):
    return {tuple(word[i]&mask for i in inds) for inds in itertools.combinations(range(len(word)),k)}


def independent_optimum(words,costs,d):
    h=len(words[0]);best=None
    for mask in range(1<<len(costs)):
        if all(not (subs(a,mask,h-d)&subs(b,mask,h-d)) for a,b in itertools.combinations(words,2)):
            cost=sum(c for p,c in enumerate(costs) if (mask>>p)&1)
            if best is None or cost<best:best=cost
    return best


def expect_rejected(model,spec,cert,label,records):
    try:validate(model,spec,cert)
    except (InvalidCertificate,KeyError,TypeError,IndexError,ValueError,RecursionError) as e:
        records.append({'mutation':label,'rejected':True,'reason':str(e)})
    else:raise AssertionError('invalid certificate accepted: '+label)


def main():
    t0=time.process_time();w0=time.perf_counter();rng=random.Random(99173);weighted=[]
    # Cross-check the bit-parallel exact baseline against the conventional grid
    # over an independently seeded range of symbols, masks, and horizons.
    lcs_checks=0
    for h in range(1,33):
        for _ in range(40):
            m=rng.randrange(1,13);mask=rng.randrange(1<<m)
            a=tuple(rng.randrange(1<<m) for _ in range(h))
            b=tuple(rng.randrange(1<<m) for _ in range(h))
            assert lcs_length(a,b,mask)==grid(a,b,mask)[-1][-1]
            lcs_checks+=1
    for case in range(120):
        h=rng.randrange(1,6);m=rng.randrange(1,6);d=rng.randrange(h+1)
        words=[tuple(rng.randrange(1<<m) for _ in range(h)) for _ in range(rng.randrange(2,5))]
        costs=[rng.randrange(1,7) for _ in range(m)]
        model=words_model(words,costs);spec={'h':h,'d':d,'offsets':[0],'contexts':[0]}
        cert,_=synthesize(model,spec);ver=validate(model,spec,cert)
        oracle=independent_optimum(words,costs,d)
        assert cert['cost']==oracle,(case,oracle,cert['cost'])
        true_ell=min((h-k for k in range(h+1) if any(subs(a,(1<<m)-1,k)&subs(b,(1<<m)-1,k) for a,b in itertools.combinations(words,2))),default=h)
        assert cert['full_margin']['loss']==true_ell
        # Permuting tap coordinates together with their costs preserves optimum.
        perm=list(range(m));rng.shuffle(perm)
        remapped=[tuple(sum(((row>>p)&1)<<q for q,p in enumerate(perm)) for row in word) for word in words]
        pm=words_model(remapped,[costs[p] for p in perm]);pc,_=synthesize(pm,spec)
        validate(pm,spec,pc);assert pc['cost']==oracle
        weighted.append({'case':case,'h':h,'m':m,'d':d,'cost':oracle,'minimum_loss':true_ell})
    lower=[]
    for d in range(7):
        h=d+1;m=2*d+1;v=[(1<<k)-1 for k in range(2*h)]
        x=tuple(v[::2]);y=tuple(v[1::2]);full=(1<<m)-1
        assert not subs(x,full,1)&subs(y,full,1)
        p=frontier(x,y,full,d);core=verify_frontier(x,y,full,d,p,m)
        assert core==full
        for tap in range(m):assert subs(x,full^(1<<tap),1)&subs(y,full^(1<<tap),1)
        lower.append({'d':d,'h':h,'essential_taps':m,'frontier_records':(d+1)**2})
    # A concrete three-tap synergy instance: any two taps fail under one silent deletion.
    model=words_model([(0,3),(1,7)],[1,1,1]);spec={'h':2,'d':1,'offsets':[0],'contexts':[0]}
    cert,_=synthesize(model,spec);assert cert['mask']==7 and cert['cost']==3
    validate(model,spec,cert);mut=[]
    def corrupt(label,fn):
        c=copy.deepcopy(cert);fn(c);expect_rejected(model,spec,c,label,mut)
    corrupt('omit required cross-class coverage',lambda c:c['coverage'].clear())
    corrupt('duplicate coverage pair',lambda c:c['coverage'].append(copy.deepcopy(c['coverage'][0])))
    corrupt('wrong coverage pair identifier',lambda c:c['coverage'][0]['pair'].__setitem__(0,1))
    corrupt('cost below actual selected cost',lambda c:c.__setitem__('cost',2))
    corrupt('mask outside declared tap universe',lambda c:c.__setitem__('mask',15))
    corrupt('nonintegral upper bound',lambda c:c['coverage'][0]['upper'][0].__setitem__(0,0.5))
    corrupt('negative boundary',lambda c:c['coverage'][0]['upper'][0].__setitem__(0,-1))
    corrupt('omitted deletion-state row',lambda c:c['coverage'][0]['upper'].pop())
    corrupt('unselected mismatch coordinate',lambda c:c['coverage'][0]['taps'][0].__setitem__(0,3))
    corrupt('false mismatch at equal coordinate',lambda c:c['coverage'][0]['taps'][0].__setitem__(0,1))
    def terminal_only(c):
        # Keep range, predecessor and sentinel rules valid; isolate strict C5.
        c['coverage'][0]['upper'][1][1]=2
        c['coverage'][0]['taps'][1][1]=None
    corrupt('terminal fails strict inequality',terminal_only)
    assert mut[-1]['reason']=='terminal upper bound does not prove separation'
    corrupt('short obstruction alignment',lambda c:c['obstructions'][0]['alignment'].clear())
    corrupt('forged disagreement clause',lambda c:c['obstructions'][0].__setitem__('clause',0))
    corrupt('remove optimality lower bound',lambda c:c['obstructions'].clear())
    corrupt('mismatched independent task',lambda c:c['spec'].__setitem__('d',0))
    corrupt('infeasible despite full-interface margin',lambda c:c.__setitem__('status','infeasible'))
    corrupt('missing margin below-budget coverage',lambda c:c['full_margin']['below'].clear())
    corrupt('minimum-loss count below certified margin',lambda c:c['full_margin'].__setitem__('loss',1))
    changed=copy.deepcopy(model);changed['classes'].append({'name':'alias','variants':['0']})
    expect_rejected(changed,spec,cert,'trusted model adds aliased class without new coverage',mut)
    # Missing seed inequality must not be accepted even if terminal remains below h.
    pm=words_model([(0,)*6+(0,3),(0,)*6+(1,7)],[1,1,1])
    ps={'h':8,'d':1,'offsets':[0],'contexts':[0]}
    bad,_=synthesize(pm,ps);bad['coverage'][0]['upper'][1][0]=1
    expect_rejected(pm,ps,bad,'predecessor deletion upper bound violated',mut)
    # All-deleted observations and initially identical classes are true null cases.
    edge=[]
    for words,h,d in [([(0,),(1,)],1,1), ([(1,1),(1,1)],2,0)]:
        em=words_model(words,[1]);sp={'h':h,'d':d,'offsets':[0],'contexts':[0]}
        ec,_=synthesize(em,sp);assert ec['status']=='infeasible';validate(em,sp,ec)
        edge.append({'h':h,'d':d,'status':ec['status'],'minimum_loss':ec['full_margin']['loss']})
    base=pairs(languages(model,spec));controls={}
    for mode in ('deletion','none','marked','marginal'):
        mask,_=exhaustive_optimum(base,[1,1,1],1,mode)
        controls[mode]={'mask':mask,'cost':mask.bit_count() if mask is not None else None,
                        'actual_coverage':mask is not None and not (subs((0,3),mask,1)&subs((1,7),mask,1))}
    assert controls['deletion']['cost']==3 and controls['marked']['cost']==2
    assert controls['none']['cost']==1 and controls['marginal']['cost'] is None
    # Count comparison permits no dependence on a matching-prefix scan in the checker.
    fixed=[]
    for h in (8,32,128,512):
        x=(0,)*(h-2)+(0,3);y=(0,)*(h-2)+(1,7)
        p=frontier(x,y,7,1);verify_frontier(x,y,7,1,p,3)
        assert len(p['upper'])*len(p['upper'][0])==4
        fixed.append({'h':h,'records':4,'kernel_taps':3})
    result={'seed':99173,'bitparallel_lcs_grid_checks':lcs_checks,'weighted_oracle_cases':weighted,'permutation_checks':120,
            'lower_bound_cases':lower,'invalid_mutations':mut,'negative_controls':controls,
            'null_cases':edge,'horizon_independence_cases':fixed,'result':'all assertions passed',
            'cpu_seconds':time.process_time()-t0,'wall_seconds':time.perf_counter()-w0,
            'process_peak_rss_kib':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,'workers':1}
    dest=Path(sys.argv[1]) if len(sys.argv)>1 else Path('results/contract-tests.json')
    dest.parent.mkdir(parents=True,exist_ok=True);dest.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({'result':result['result'],'weighted_cases':len(weighted),'mutations_rejected':len(mut),'cpu_seconds':result['cpu_seconds']}))
if __name__=='__main__':main()
