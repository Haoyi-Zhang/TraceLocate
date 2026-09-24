"""Standalone certificate consumer. Does not import the producer or compute LCS.

Usage: python src/check_certificate.py --model models/counter.json
       --certificate results/campaign/certificates/CASE_ID.json
       --instance models/campaign.json --case CASE_ID
The independently supplied task specification binds the claim being checked.

The trusted input is the supplied finite model, class partition, contexts,
initial states, offsets, costs and task. No cryptographic identity or translation
from RTL is asserted. This consumer checks the evidence relative to those inputs.
"""
from __future__ import annotations
import argparse,json
from pathlib import Path
from typing import Any

class InvalidCertificate(ValueError):pass

def need(test:bool,message:str)->None:
    if not test:raise InvalidCertificate(message)

def integer(x:Any)->bool:return type(x) is int

def replay(model:dict,spec:dict)->list:
    """A separately written recursive interpreter plus canonical deduplication."""
    need(isinstance(model,dict),'model must be an object')
    need(isinstance(model.get('name'),str),'model name')
    taps=model.get('taps');need(isinstance(taps,list) and 1<=len(taps)<=64,'tap count')
    for t in taps:
        need(isinstance(t,dict) and isinstance(t.get('name'),str),'tap declaration')
        need(integer(t.get('cost')) and t['cost']>0,'positive integral tap cost')
    need(len({t['name'] for t in taps})==len(taps),'duplicate tap name')
    h=spec.get('h');d=spec.get('d');offsets=spec.get('offsets');ctx=spec.get('contexts')
    need(integer(h) and 1<=h<=256,'horizon limit')
    need(integer(d) and 0<=d<=h,'loss budget')
    need(isinstance(offsets,list) and offsets and all(integer(o) and 0<=o<=8 for o in offsets),'offsets')
    need(len(set(offsets))==len(offsets),'duplicate offsets')
    need(isinstance(ctx,list) and ctx and all(integer(c) for c in ctx),'contexts')
    need(len(set(ctx))==len(ctx),'duplicate context')
    classes=model.get('classes');variants=model.get('variants');contexts=model.get('contexts')
    need(isinstance(classes,list) and 2<=len(classes)<=32,'class count')
    need(len({c['name'] for c in classes})==len(classes),'duplicate class')
    need(isinstance(variants,dict) and variants,'variants')
    need(isinstance(contexts,list),'context list')
    for vn,v in variants.items():
        need(isinstance(v,dict) and isinstance(v.get('table'),list) and v['table'],'transition table')
        n=len(v['table']);need(n<=4096,'state limit')
        alpha=len(v['table'][0]);need(alpha>0,'input alphabet')
        need(all(isinstance(row,list) and len(row)==alpha for row in v['table']),'non-total table')
        need(isinstance(v.get('initial'),list) and v['initial'],'initial states')
        need(all(integer(q) and 0<=q<n for q in v['initial']),'invalid initial state')
        for row in v['table']:
            for e in row:
                need(isinstance(e,dict) and integer(e.get('next')) and 0<=e['next']<n,'transition successor')
                need(integer(e.get('row')) and 0<=e['row']<(1<<len(taps)),'row outside declared taps')
    def run(table,q,inputs,pos,stop,acc):
        if pos==stop:return tuple(acc)
        u=inputs[pos];need(integer(u) and 0<=u<len(table[q]),'stimulus outside alphabet')
        e=table[q][u]
        return run(table,e['next'],inputs,pos+1,stop,acc+[e['row']])
    out=[]
    for ci in ctx:
        need(0<=ci<len(contexts),'context index');inputs=contexts[ci]['inputs']
        need(isinstance(inputs,list) and len(inputs)>=h+max(offsets),'stimulus too short')
        groups=[]
        for cls in classes:
            names=cls.get('variants');need(isinstance(names,list) and names,'empty fault class')
            allwords=[]
            for vn in names:
                need(vn in variants,'unknown variant')
                v=variants[vn]
                for q in v['initial']:
                    for offset in offsets:
                        w=run(v['table'],q,inputs,0,h+offset,[])
                        allwords.append(w[offset:])
            groups.append(sorted(set(allwords)))
        out.append(groups)
    ps=[]
    for c,groups in enumerate(out):
        for f in range(len(groups)):
            for g in range(f+1,len(groups)):
                for i,x in enumerate(groups[f]):
                    for j,y in enumerate(groups[g]):ps.append(((c,f,i,g,j),x,y))
    need(ps,'vacuous pair list')
    return ps

def verify_frontier(x:tuple,y:tuple,mask:int,d:int,proof:dict,m:int)->int:
    """Local upper-bound checks only: no snakes, LCS recurrence or optimization."""
    h=len(x);u=proof.get('upper');t=proof.get('taps')
    need(isinstance(u,list) and len(u)==d+1,'frontier row count')
    need(isinstance(t,list) and len(t)==d+1,'witness row count')
    core=0
    for a in range(d+1):
        need(isinstance(u[a],list) and len(u[a])==d+1,'frontier column count')
        need(isinstance(t[a],list) and len(t[a])==d+1,'witness column count')
        for b in range(d+1):
            i=u[a][b];need(integer(i) and a<=i<=h+a,'frontier range')
            j=i-a+b
            if a:need(i>=u[a-1][b]+1,'left-deletion upper bound')
            if b:need(i>=u[a][b-1],'right-deletion upper bound')
            p=t[a][b]
            if i<h and j<h:
                need(integer(p) and 0<=p<m and bool(mask>>p&1),'witness tap not selected')
                need(bool((x[i]^y[j])>>p&1),'boundary is not a witnessed mismatch')
                core |= 1<<p
            else:need(p is None,'outside boundary must use fixed sentinel')
    need(u[d][d]<h,'terminal upper bound does not prove separation')
    return core

def complete_coverage(ps:list,mask:int,d:int,proofs:Any,m:int)->list[int]:
    need(isinstance(proofs,list) and len(proofs)==len(ps),'coverage pair count')
    cores=[]
    for (pid,x,y),p in zip(ps,proofs):
        need(isinstance(p,dict) and p.get('pair')==list(pid),'coverage pair order or identity')
        cores.append(verify_frontier(x,y,mask,d,p,m))
    return cores

def matching(ps:dict,w:dict,mask:int,k:int)->int:
    pid=w.get('pair');need(isinstance(pid,list) and len(pid)==5 and all(integer(z) for z in pid),'witness pair format')
    need(tuple(pid) in ps,'unknown witness pair')
    x,y=ps[tuple(pid)];a=w.get('alignment')
    need(isinstance(a,list) and len(a)==k,'alignment length')
    previous=(-1,-1);difference=0
    for cell in a:
        need(isinstance(cell,list) and len(cell)==2 and all(integer(z) for z in cell),'alignment cell')
        i,j=cell;need(previous[0]<i<len(x) and previous[1]<j<len(y),'alignment order/range')
        need(((x[i]^y[j])&mask)==0,'alignment does not match selected taps')
        difference |= x[i]^y[j];previous=(i,j)
    return difference

def validate(model:dict,spec:dict,cert:dict)->dict:
    ps=replay(model,spec);byid={pid:(x,y) for pid,x,y in ps}
    m=len(model['taps']);full=(1<<m)-1;h=spec['h'];d=spec['d']
    need(isinstance(cert,dict) and cert.get('model')==model['name'],'model declaration')
    need(cert.get('spec')==spec,'task mismatch')
    margin=cert.get('full_margin');need(isinstance(margin,dict),'missing full-tap margin')
    ell=margin.get('loss');need(integer(ell) and 0<=ell<=h,'minimum-loss range')
    need(margin.get('mask')==full,'margin must use all declared taps')
    matching(byid,margin,full,h-ell)
    if ell:complete_coverage(ps,full,ell-1,margin.get('below'),m)
    else:need(margin.get('below')==[],'zero-loss witness has no below-zero proof')
    status=cert.get('status')
    if status=='infeasible':
        need(ell<=d,'full-tap collision outside requested budget')
        need(cert.get('mask') is None and cert.get('cost') is None,'infeasible mask/cost')
        need(cert.get('coverage')==[] and cert.get('obstructions')==[],'unexpected infeasible evidence')
        return {'status':'infeasible','pairs':len(ps),'full_minimum_loss':ell}
    need(status=='feasible','unknown status')
    need(m<=12,'optimality checking is bounded to 12 taps')
    mask=cert.get('mask');need(integer(mask) and 0<=mask<=full,'mask range')
    costs=[t['cost'] for t in model['taps']]
    actual=sum(w for p,w in enumerate(costs) if mask>>p&1)
    need(integer(cert.get('cost')) and cert['cost']==actual,'claimed cost')
    cores=complete_coverage(ps,mask,d,cert.get('coverage'),m)
    obstruction=cert.get('obstructions');need(isinstance(obstruction,list),'obstruction list')
    clauses=[]
    for w in obstruction:
        # The matching is judged without assuming any tap: its disagreement
        # set is a necessary clause for every robust interface.
        need(isinstance(w,dict),'obstruction record')
        c=matching(byid,w,0,h-d)
        need(integer(w.get('clause')) and c==w['clause'] and c>0,'unsound obstruction clause')
        need(bool(mask&c),'returned mask violates a necessary clause');clauses.append(c)
    cheaper=0
    for s in range(full+1):
        w=sum(v for p,v in enumerate(costs) if s>>p&1)
        if w<actual:
            cheaper+=1
            need(any((s&c)==0 for c in clauses),'a cheaper mask survives the lower-bound certificate')
    return {'status':'feasible','pairs':len(ps),'cost':actual,'cheaper_masks_checked':cheaper,
            'max_pair_core':max(c.bit_count() for c in cores),'full_minimum_loss':ell}

def main()->None:
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--model',type=Path,required=True);p.add_argument('--certificate',type=Path,required=True)
    p.add_argument('--instance',type=Path,required=True);p.add_argument('--case',required=True)
    args=p.parse_args()
    model=json.loads(args.model.read_text());cert=json.loads(args.certificate.read_text())
    campaign=json.loads(args.instance.read_text());matches=[c for c in campaign['cases'] if c['id']==args.case]
    need(len(matches)==1,'case identifier must resolve exactly once')
    need(matches[0]['model']==model['name'],'campaign model mismatch')
    result=validate(model,matches[0]['spec'],cert)
    print(json.dumps({'accepted':True,'case':args.case,**result},sort_keys=True))
if __name__=='__main__':
    try:main()
    except (InvalidCertificate,KeyError,TypeError,IndexError,ValueError,RecursionError) as e:
        raise SystemExit('REJECT: '+str(e))
