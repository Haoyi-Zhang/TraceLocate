"""Create the six original, fully specified, synthetic Mealy fixtures.

No imported netlist, simulation trace, proprietary design, or physical device is
used. Mutation names denote these table transformations, not analog fault models.
The fixed context scripts and campaign are independent of observed outcomes.
"""
from __future__ import annotations
import argparse,json
from pathlib import Path


def bits(values):
    assert all(v in (False,True,0,1) for v in values)
    return sum(int(v)<<i for i,v in enumerate(values))


def make(name,n,alpha,taps,variants,initial,classes,step):
    vv={}
    for v in variants:
        table=[]
        for q in range(n):
            row=[]
            for u in range(alpha):
                nq,output=step(q,u,v)
                assert 0<=nq<n and len(output)==len(taps)
                row.append({'next':nq,'row':bits(output)})
            table.append(row)
        vv[v]={'initial':initial.copy(),'table':table}
    patterns=([0],[0,1],[0,0,1,0,1,1,1]) if alpha==2 else ([0],[1,2,3,0],[1,1,3,2,0,2,3])
    contexts=[{'name':nm,'inputs':(pat*20)[:20]} for nm,pat in zip(['idle','alternating','mixed'],patterns)]
    return {'name':name,'origin':'original synthetic finite-state mechanism fixture',
            'row_convention':'output on a transition, after the stated successor computation',
            'taps':[{'name':t,'cost':1} for t in taps],
            'classes':[{'name':nm,'variants':vs} for nm,vs in classes],
            'variants':vv,'contexts':contexts}


def all_models():
    models=[]
    def count(q,u,v):
        delta={'nominal':1,'hold':0,'stride':2,'reverse':-1}[v] if u else 0
        nq=(q+delta)%4
        return nq,[nq&1,(nq>>1)&1,u and q+delta>=4,(q^nq)&1,((q^nq)>>1)&1,u]
    vs=['nominal','hold','stride','reverse']
    models.append(make('counter',4,2,['q0','q1','carry','change0','change1','enable'],vs,[0],[(v,[v]) for v in vs],count))
    def fifo(q,u,v):
        push=bool(u&1);pop=bool(u&2);take_pop=pop and q>0
        if v=='drop_pop':take_pop=False
        take_push=push and (q<3 or take_pop)
        if v=='drop_push':take_push=False
        if v=='no_replace':take_push=push and q<3
        nq=q+int(take_push)-int(take_pop)
        return nq,[nq&1,(nq>>1)&1,nq==0,nq==3,take_push,take_pop,push and not take_push,pop and not take_pop]
    vs=['nominal','drop_push','drop_pop','no_replace']
    models.append(make('fifo',4,4,['q0','q1','empty','full','push_ack','pop_ack','push_block','pop_block'],vs,[0],[(v,[v]) for v in vs],fifo))
    def arbiter(q,u,v):
        if not u:winner=None
        elif u==1:winner=0
        elif u==2:winner=1
        else:winner=0 if v=='fixed_low' else q
        if winner is not None and v=='wrong_grant':winner=1-winner
        nq=q if winner is None or v=='sticky' else 1-winner
        return nq,[winner==0,winner==1,nq,u==0,u==3,nq!=q]
    vs=['nominal','sticky','fixed_low','wrong_grant']
    models.append(make('arbiter',2,4,['grant0','grant1','pointer','idle','both','changed'],vs,[0,1],
                       [('nominal',['nominal']),('priority',['sticky','fixed_low']),('wrong_grant',['wrong_grant'])],arbiter))
    def credit(q,u,v):
        request=bool(u&1);returned=bool(u&2) and v!='lost_return'
        available=min(3,q+int(returned)) if v=='return_first' else q
        accept=request and available>0
        debit=2 if v=='double_consume' else 1
        nq=max(0,available-debit*int(accept))
        if v!='return_first':nq=min(3,nq+int(returned))
        return nq,[nq&1,(nq>>1)&1,nq==0,nq==3,accept,request and not accept,returned]
    vs=['nominal','lost_return','double_consume','return_first']
    models.append(make('credit',4,4,['credit0','credit1','empty','full','send_ack','send_block','return_seen'],vs,[1,2],[(v,[v]) for v in vs],credit))
    def handshake(q,u,v):
        start=bool(u&1);ready=bool(u&2)
        if q==0:nq=(2 if v=='skip_armed' else 1) if start else 0
        elif q==1:nq=2
        elif q==2:nq=3 if ready and v!='ignore_ready' else 2
        else:nq=3 if v=='sticky_done' else 0
        return nq,[nq&1,(nq>>1)&1,nq in (1,2),nq==3,nq==3 and q!=3,start]
    vs=['nominal','skip_armed','ignore_ready','sticky_done']
    models.append(make('handshake',4,4,['state0','state1','request','ack','ack_edge','start'],vs,[0],[(v,[v]) for v in vs],handshake))
    def lfsr(q,u,v):
        if v=='wrong_feedback':fb=((q>>1)^q)&1
        elif v=='rotate':fb=(q>>2)&1
        else:fb=((q>>2)^q)&1
        nq=q if not u or v=='hold' else ((q<<1)&7)|fb
        return nq,[nq&1,(nq>>1)&1,(nq>>2)&1,fb,nq==0,u,nq.bit_count()%2]
    vs=['nominal','wrong_feedback','hold','rotate']
    models.append(make('lfsr',8,2,['state0','state1','state2','feedback','zero','enable','parity'],vs,[1,3],[(v,[v]) for v in vs],lfsr))
    return models


def campaign(models):
    cases=[]
    for model in models:
        for h in (4,8,12):
            for d in (0,1,2):
                for offsets in ([0],[0,1]):
                    for contexts in ([0],[1],[2],[0,1,2]):
                        ident=f"{model['name']}-h{h}-d{d}-o{len(offsets)}-c"+''.join(map(str,contexts))
                        cases.append({'id':ident,'model':model['name'],
                                      'spec':{'h':h,'d':d,'offsets':offsets,'contexts':contexts}})
    return {'selection':'all six mechanisms; horizons 4,8,12; losses 0,1,2; known/uncertain offset; each of three scripts and their conjunction',
            'seed':None,'cases':cases}


def main():
    p=argparse.ArgumentParser();p.add_argument('--out',type=Path,default=Path('models'));args=p.parse_args()
    args.out.mkdir(parents=True,exist_ok=True);models=all_models()
    for model in models:(args.out/(model['name']+'.json')).write_text(json.dumps(model,indent=2)+'\n')
    (args.out/'campaign.json').write_text(json.dumps(campaign(models),indent=2)+'\n')
    print(json.dumps({'models':len(models),'cases':len(campaign(models)['cases'])}))
if __name__=='__main__':main()
