"""Check a finite all-input equal-output invariant, independently of trace synthesis."""
from __future__ import annotations
import argparse,json
from pathlib import Path


def require(condition, message):
    if not condition:
        raise ValueError(message)


def check(model,certificate):
    require(certificate['model']==model['name'], 'model mismatch')
    left,right=certificate['variants'];a=model['variants'][left];b=model['variants'][right]
    rel={tuple(s) for s in certificate['relation']}
    require(len(rel)==len(certificate['relation']) and bool(rel), 'empty or repeated relation')
    initial=tuple(certificate['initial'])
    require(initial in rel and initial[0] in a['initial'] and initial[1] in b['initial'], 'initial witness')
    transitions=0
    for q,r in sorted(rel):
        require(0<=q<len(a['table']) and 0<=r<len(b['table']), 'state range')
        la=a['table'][q];lb=b['table'][r];require(len(la)==len(lb)>0, 'input alphabet')
        for ea,eb in zip(la,lb):
            require(ea['row']==eb['row'], 'output difference')
            require((ea['next'],eb['next']) in rel, 'relation not inductive')
            transitions+=1
    # At least one declared cross-class comparison is covered by this witness.
    class_pairs=[]
    for i,c in enumerate(model['classes']):
        if left not in c['variants']:continue
        for j,e in enumerate(model['classes']):
            if i!=j and right in e['variants']:class_pairs.append([c['name'],e['name']])
    require(bool(class_pairs), 'no cross-class implication')
    return {'accepted':True,'relation_states':len(rel),'checked_transitions':transitions,
            'classes':class_pairs,'conclusion':'the witnessed initial executions agree for every input word and horizon'}


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--model',type=Path,default=Path('models/lfsr.json'))
    p.add_argument('--certificate',type=Path,default=Path('models/alias-witness.json'))
    p.add_argument('--out',type=Path);a=p.parse_args()
    result=check(json.loads(a.model.read_text()),json.loads(a.certificate.read_text()))
    if a.out:a.out.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result,sort_keys=True))
if __name__=='__main__':main()
