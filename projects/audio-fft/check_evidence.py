"""Independent measurement sanity checks and supplied-log agreement."""
from pathlib import Path
import json
import numpy as np
from scipy.signal import welch
from original_prototype import compute_spectrum

def checks():
    fs=8192
    t=np.arange(fs)/fs
    signal=np.sin(2*np.pi*256*t)
    f,m=compute_spectrum(signal,fs)
    assert abs(f[np.argmax(m)]-256)<1e-9, 'Known-frequency FFT peak failed'
    signal=.5*np.sin(2*np.pi*1024*t)+np.sin(2*np.pi*3072*t)
    f,p=welch(signal,fs=fs,nperseg=1024,noverlap=512)
    low=p[(f>900)&(f<1100)].sum();high=p[(f>2900)&(f<3200)].sum()
    assert abs(high/low-4)<1e-8, 'Known two-tone power ratio failed'
    result=json.loads((Path(__file__).parent/'results/results.json').read_text())
    expected={'engine_recording':{'dominant_freq':(199.65,.0051),'centroid':(3174.69,.0051),'flatness':(.0957,.000051),'entropy':(18.0734,.000051),'anomaly_rate':(.0301,.000051),'onset_density':(6.56,.0051)},
              'drum_recording':{'dominant_freq':(112.88,.0051),'centroid':(2494.54,.0051),'flatness':(.1300,.000051),'entropy':(15.5193,.000051),'anomaly_rate':(.4062,.000051),'onset_density':(5.45,.0051)}}
    for role,metrics in expected.items():
        for metric,(target,tol) in metrics.items():
            assert abs(result[role][metric]-target)<tol,(role,metric)
    assert abs(result['supplied_log_order']['heuristic_severity']-.471)<.0005
    assert result['supplied_log_order']['baseline']=='drum'
    assert result['intended_order']['baseline']=='engine recording'
    assert len(result['input_sha256'])==2
    print('PASS: known-frequency FFT, known power ratio, 12 supplied feature values, supplied severity and explicit file roles.')

if __name__=='__main__':
    checks()
