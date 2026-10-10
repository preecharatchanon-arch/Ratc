import numpy as np
from control_math import coefficients,sketch_coefficients,energy_curves,response_metrics

def verify_math():
    rng=np.random.default_rng(910333)
    Q,_=np.linalg.qr(rng.normal(size=(160,100)));R,_=np.linalg.qr(rng.normal(size=(100,100)))
    singular=np.geomspace(3,.03,100);A=np.diag(singular)@R.T;B=Q@A
    G=A@A.T;H=B@B.T;K=B@A.T;C,w=coefficients(G);S,_=sketch_coefficients(G,rng)
    curves,spec=energy_curves(G,H,K,C,S)
    assert np.allclose(C.T@G@C,np.eye(100),atol=1e-9)
    for row in curves:
        n=min(row['k'],100);expected=float(np.square(singular[:n]).sum()/np.square(singular).sum())
        assert abs(row['transfer_capture']-expected)<1e-10
        assert abs(row['heldout_self_oracle_capture']-expected)<1e-10
    # Held-out anchor can rotate the sensitive parameter directions.
    B2=B[:,::-1];K2=B2@A.T
    changed,_=energy_curves(G,H,K2,C,S)
    assert changed[3]['transfer_capture']<curves[3]['transfer_capture']
    f=rng.normal(size=(8,10));p=.7*f;r=.3*f
    q=response_metrics(np.zeros_like(f),f,p,r)
    assert abs(q['retention']-.7)<1e-12 and abs(q['remainder_ratio']-.3)<1e-12 and q['additivity_error']<1e-12
    # Even finite responses cannot be erased by a paired contrast.
    even=2*f;plus=f+even;minus=-f+even
    assert np.allclose((plus-minus)/2,f) and np.linalg.norm(plus)>np.linalg.norm(f)
    # Two linear slices do not certify one autonomous/naturally reachable state.
    return {'known_spectrum_max_error':max(abs(x['fit_capture']-x['transfer_capture']) for x in curves),
            'anchor_rotation_detected':True,'finite_additivity_and_even_response_fixture':True}

if __name__=='__main__':print(verify_math())
