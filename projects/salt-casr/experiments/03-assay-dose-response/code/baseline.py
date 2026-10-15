"""Unchanged fixed-baseline definitions from sensory-continuation/analyse.py (020252a)."""

import numpy as np
import pandas as pd
from sklearn.ensemble import ExtraTreesClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

AA = 'ACDEFGHIKLMNPQRSTVWY'

KD = dict(zip(AA, [1.8,2.5,-3.5,-3.5,2.8,-.4,-3.2,4.5,-3.9,3.8,1.9,-3.5,-1.6,-3.5,-4.5,-.8,-.7,4.2,-.9,-1.3]))

def distance(a,b):
    prior=list(range(len(b)+1))
    for i,x in enumerate(a,1):
        cur=[i]
        for j,y in enumerate(b,1):cur.append(min(cur[-1]+1,prior[j]+1,prior[j-1]+(x!=y)))
        prior=cur
    return prior[-1]

def groups(d,refs=False):
    parent=list(range(len(d)))
    def find(i):
        while parent[i]!=i: parent[i]=parent[parent[i]];i=parent[i]
        return i
    def union(a,b): parent[find(a)]=find(b)
    sequences=d.sequence.tolist();edges=[]
    for i,a in enumerate(sequences):
        for j in range(i):
            b=sequences[j]
            if abs(len(a)-len(b))>.2*max(len(a),len(b))+1e-9: continue
            sim=1-distance(a,b)/max(len(a),len(b))
            if sim>=.8-1e-12:union(i,j);edges.append((i,j))
    if refs:
        seen={}
        for i,tokens in enumerate(d.doi_tokens):
            assert tokens,'Reference-blocked cohort contains no-DOI record'
            for token in tokens.split(';'):
                if token in seen:union(i,seen[token])
                else:seen[token]=i
    roots=[find(i) for i in range(len(d))]
    labels={g:k for k,g in enumerate(sorted(set(roots)))}
    return np.array([labels[g] for g in roots]),edges

def features(seqs):
    rows=[]
    for s in seqs:
        n=len(s)
        charge=1/(1+10**(7-9.69))-1/(1+10**(2.34-7))
        for a,pka in [('H',6),('K',10.5),('R',12.5)]:charge+=s.count(a)/(1+10**(7-pka))
        for a,pka in [('D',3.9),('E',4.1),('C',8.3),('Y',10.1)]:charge-=s.count(a)/(1+10**(pka-7))
        rows.append([n,charge,charge/n,*[s.count(a)/n for a in AA],
            np.mean([KD[a] for a in s]),int(s[0] in 'DE'),int(s[-1] in 'DE'),
            int(s[0] in 'KRH'),int(s[-1] in 'KRH')])
    return np.array(rows,dtype=float)

def fit_predict(name,x,y,train,test):
    if name=='extra_trees':
        model=ExtraTreesClassifier(n_estimators=512,min_samples_leaf=2,max_features='sqrt',class_weight='balanced',random_state=777,n_jobs=2)
        cols=np.arange(x.shape[1])
    else:
        model=make_pipeline(StandardScaler(),LogisticRegression(C=1,class_weight='balanced',max_iter=2000,random_state=777))
        cols=np.array([0]) if name=='length_only' else np.array([0,1,2]) if name=='charge_length' else np.arange(x.shape[1])
    model.fit(x[train][:,cols],y[train])
    return model.predict_proba(x[test][:,cols])[:,1]
