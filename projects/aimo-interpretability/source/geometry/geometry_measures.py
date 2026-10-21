"""Four fixed temporal features and four dimension-normalized geometric features."""
import numpy as np
RIDGE=1e-6

def temporal_features(trace):
    h=np.asarray(trace['entropy'],dtype=np.float64)
    if h.shape!=(128,) or not np.isfinite(h).all() or h.min() < -1e-7:raise ValueError('Expected 128 finite native-token entropy values')
    t=np.linspace(0.,1.,len(h));tt=t-t.mean();hh=h-h.mean()
    slope=float(np.dot(tt,hh)/np.dot(tt,tt));var=float(hh@hh)
    r2=float((np.dot(tt,hh)**2)/(np.dot(tt,tt)*var)) if var>1e-24 else 0.
    windows=np.convolve(h,np.ones(16)/16,mode='valid')
    features=[slope,float(np.clip(r2,0,1)),float(h[-32:].mean()-h[:32].mean()),float(windows.max()-h.mean())]
    return features

def geometry_from_gram(gram,adjacent):
    g=np.asarray(gram,dtype=np.float64);adj=np.asarray(adjacent,dtype=np.float64);n=len(g)
    if g.shape!=(n,n) or n<2 or adj.shape!=(n-1,) or not np.isfinite(g).all() or not np.isfinite(adj).all():raise ValueError('Invalid geometric arrays')
    if not np.allclose(g,g.T,atol=1e-12,rtol=0) or abs(np.trace(g)-1.)>1e-9:raise ValueError('Invalid normalized Gram matrix')
    if abs(g.sum())>1e-8 or np.any(adj < -1e-10) or np.any(adj>2+1e-10):raise ValueError('Invalid centering or cosine distances')
    eig=np.linalg.eigvalsh((g+g.T)/2)
    if eig.min() < -1e-9:raise ValueError('Non-positive-semidefinite Gram matrix')
    eig=np.maximum(eig,0.);eig/=eig.sum()
    positive=eig[eig>0]
    result=[float(-(positive*np.log(positive)).sum()/np.log(n)),float(eig[-1]),
            float(np.log(eig+RIDGE).mean()),float(adj.mean())]
    if not np.isfinite(result).all():raise ValueError('Nonfinite geometry features')
    return result

def geometry_from_hidden(hidden):
    h=np.asarray(hidden,dtype=np.float64)
    if h.ndim!=2 or len(h)<2 or not np.isfinite(h).all():raise ValueError('Invalid hidden-state tensor')
    norms=np.linalg.norm(h,axis=1,keepdims=True)
    if np.any(norms<1e-12):raise ValueError('Zero hidden-state token norm')
    u=h/norms;center=u-u.mean(axis=0,keepdims=True);g=center@center.T;energy=float(np.trace(g))
    if energy<1e-12:raise ValueError('Degenerate centered hidden-state geometry')
    g/=energy;g=(g+g.T)/2
    adjacent=np.clip(1.-np.sum(u[:-1]*u[1:],axis=1),0.,2.)
    return {'centered_gram':g.tolist(),'adjacent_distances':adjacent.tolist(),'features':geometry_from_gram(g,adjacent),'hidden_width':int(h.shape[1])}
