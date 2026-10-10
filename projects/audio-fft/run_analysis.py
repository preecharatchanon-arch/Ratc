"""Reproduce the supplied prototype and export explicitly labelled evidence.

python run_analysis.py --reference /path/reference.wav --comparison /path/test.wav
Requires ffmpeg on PATH. Audio sources are downloaded by the reader separately.
"""
from pathlib import Path
import argparse
import csv
import hashlib
import json
import platform
import subprocess
import sys
from datetime import datetime, timezone
import numpy as np
import scipy
from scipy.signal import resample_poly, stft, welch
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from original_prototype import analyze_file, score_file, compare_results, verdict_from_scores, load_audio, highpass

ROOT = Path(__file__).resolve().parent
NAVY, TEAL, ORANGE = '#132b46', '#007f87', '#bd5f27'
plt.rcParams.update({'font.family':'DejaVu Sans','font.size':16,'axes.labelsize':17,
                     'axes.titlesize':19,'axes.titleweight':'bold','axes.spines.top':False,
                     'axes.spines.right':False,'axes.edgecolor':'#becbd4','text.color':NAVY,
                     'axes.labelcolor':NAVY,'xtick.color':NAVY,'ytick.color':NAVY,
                     'figure.facecolor':'white','axes.facecolor':'white'})

def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def summary(result):
    g=result['global']
    return {'file':Path(result['file']).name,'sample_rate_hz':result['fs'],'channels':result['channels'],
            'duration_s':g['duration'],**{k:g[k] for k in ['peak_amp','rms','crest_factor','clipping_ratio','dominant_freq','centroid','flatness','entropy','harmonic_score','peak_count','roll95']},
            'magnitude_band_shares':g['band_shares'],'anomaly_rate':result['anomaly_rate'],
            'onset_density':result['onset_density'],'prototype_verdict':verdict_from_scores(score_file(result)),
            'top_peak_frequencies_hz':g['peak_freqs'][:10].tolist(),
            'top_peak_magnitudes':g['peak_amps'][:10].tolist()}

def print_original(tag,result):
    g=result['global'];s=summary(result)
    print('\n'+'='*70+'\n'+tag+'\n'+'='*70)
    for label,key in [('File','file'),('Sample rate','sample_rate_hz'),('Channels','channels'),('Duration','duration_s'),('Peak amplitude','peak_amp'),('RMS','rms'),('Crest factor','crest_factor'),('Clipping ratio','clipping_ratio'),('Dominant freq','dominant_freq'),('Centroid','centroid'),('Flatness','flatness'),('Entropy','entropy'),('Harmonic score','harmonic_score'),('Peak count','peak_count'),('Anomaly rate','anomaly_rate'),('Onset density','onset_density'),('Prototype verdict','prototype_verdict')]:
        print(f'{label:20}: {s[key]}')
    print('Top peaks (Hz, unnormalised magnitude):')
    for f,a in zip(g['peak_freqs'][:10],g['peak_amps'][:10]):
        print(f'  {f:.2f} Hz | {a:.6f}')
    print('Magnitude band shares (original code labels these energy):',g['band_shares'])
    print('First ten onset estimates (time, peak, original decay estimate):')
    for t,p,d in zip(result['onset_times'][:10],result['hit_peaks'][:10],result['hit_decays'][:10]):
        print(f'  {t:.3f}s | {p:.6f} | {d:.6f}s')

def make_figures(engine,comparison,out):
    fig,ax=plt.subplots(figsize=(12,5.3),layout='constrained')
    for r,label,color in [(engine,'Reference',TEAL),(comparison,'Comparison',ORANGE)]:
        g=r['global'];w=np.hanning(len(g['x'])+1)[:-1]
        a=2*g['mag']/w.sum()
        ax.plot(g['freqs'],a,label=label,color=color,lw=1.35,alpha=.9)
        idx=int(np.argmax(g['mag']));f=float(g['freqs'][idx]);v=float(a[idx])
        ax.annotate(f'{f:.2f} Hz',(f,v),xytext=(f+80,v*1.08),color=color,fontsize=17,
                    arrowprops={'arrowstyle':'-','color':color})
    peak_height=max(2*r['global']['mag'].max()/np.hanning(len(r['global']['x'])+1)[:-1].sum() for r in [engine,comparison])
    ax.set(xlim=(0,1600),ylim=(0,peak_height*1.25),xlabel='Frequency (Hz)',ylabel='Window-normalised FFT amplitude',title='Different sounds, different frequency structure')
    ax.grid(axis='both',alpha=.18);ax.legend(frameon=False,fontsize=14,loc='upper right')
    fig.text(.5,-.028,'Full recordings · Hann window · two-file demonstration; no fault labels',ha='center',fontsize=13,color='#4c6074')
    fig.savefig(out/'fft_comparison.png',dpi=170,bbox_inches='tight');plt.close(fig)

    fs=44100
    ys=[]
    for r in [engine,comparison]:
        y,rate,_,_=load_audio(r['file'])
        y=highpass(y,rate,20.0,3)
        if rate!=fs:
            from math import gcd
            d=gcd(rate,fs);y=resample_poly(y,fs//d,rate//d)
        ys.append(y)
    n=min(map(len,ys));duration=n/fs
    ys=[y[:n] for y in ys]
    fig,axes=plt.subplots(2,1,figsize=(12,5.5),sharex=True,sharey=True,layout='constrained')
    for ax,y,label in zip(axes,ys,['Reference','Comparison']):
        y=y/(np.sqrt(np.mean(y*y))+1e-12)
        f,t,z=stft(y,fs=fs,window='hann',nperseg=2048,noverlap=1536,boundary=None,padded=False)
        im=ax.pcolormesh(t,f/1000,20*np.log10(np.abs(z)+1e-12),shading='auto',vmin=-70,vmax=0,cmap='magma',rasterized=True)
        ax.set_ylim(0,4);ax.set_ylabel('kHz');ax.text(.015,.85,label,transform=ax.transAxes,color='white',weight='bold',fontsize=16)
    axes[0].set_title('How frequency content changes through time')
    axes[-1].set_xlabel('Time (s)');fig.colorbar(im,ax=axes,label='dB relative to unit RMS',pad=.018)
    fig.text(.5,-.025,f'Same first {duration:.2f} s · 44.1 kHz · 2,048-sample Hann window · 512-sample hop',ha='center',fontsize=13,color='#4c6074')
    fig.savefig(out/'stft_comparison.png',dpi=170,bbox_inches='tight');plt.close(fig)

    # An audited, separately labelled band-power calculation on matched support.
    bands=[(0,60),(60,250),(250,500),(500,1000),(1000,3000),(3000,8000),(8000,fs/2)]
    labels=['0–60','60–250','250–500','500–1k','1k–3k','3k–8k','8k+']
    powers=[]
    for y in ys:
        f,p=welch(y,fs=fs,window='hann',nperseg=4096,noverlap=2048,nfft=4096,detrend='constant',scaling='density')
        fractions=[float(p[(f>=a)&(f<b)].sum()/p.sum()) for a,b in bands]
        powers.append(fractions)
    fig,ax=plt.subplots(figsize=(12,5.2),layout='constrained')
    x=np.arange(len(labels))
    for i,(vals,label,color) in enumerate(zip(powers,['Reference','Comparison'],[TEAL,ORANGE])):
        ax.bar(x+(i-.5)*.38,100*np.array(vals),width=.38,label=label,color=color)
    ax.set_xticks(x,labels);ax.set(ylabel='Share of estimated signal power (%)',xlabel='Frequency band (Hz)',title='Band power on a common measurement grid')
    ax.legend(frameon=False);ax.grid(axis='y',alpha=.16)
    fig.text(.5,-.025,'Welch PSD · matched duration and sample rate · separate from the original magnitude-based metric',ha='center',fontsize=12,color='#4c6074')
    fig.savefig(out/'band_power_comparison.png',dpi=170,bbox_inches='tight');plt.close(fig)
    return {'common_sample_rate_hz':fs,'matched_duration_s':duration,'method':'Welch PSD; one 20 Hz high-pass; 4096 samples; 50% overlap; shared frequency grid',
            'bands_hz':bands,'reference_power_shares':powers[0],'comparison_power_shares':powers[1]}

def run(engine_path,comparison_path,out):
    engine_path=Path(engine_path).resolve()
    comparison_path=Path(comparison_path).resolve()
    if engine_path==comparison_path:
        raise ValueError('Choose two different recordings for reference and comparison.')
    for path in [engine_path,comparison_path]:
        if not path.is_file():
            raise FileNotFoundError(f'Recording not found: {path}')
    if any(Path(out).resolve().is_relative_to(ROOT / name) for name in ['results','figures']):
        raise ValueError('The results/ and figures/ directories hold archived example evidence. Choose another output directory.')
    out=Path(out);out.mkdir(parents=True,exist_ok=True)
    figures=out/'figures';figures.mkdir(parents=True,exist_ok=True)
    engine=analyze_file(str(engine_path));comparison=analyze_file(str(comparison_path))
    # Compare the explicitly selected roles and also export the reversed order.
    log_shift,log_hints,log_severity=compare_results(comparison,engine)
    intended_shift,intended_hints,intended_severity=compare_results(engine,comparison)
    fixed=make_figures(engine,comparison,figures)
    payload={'schema_version':2,'analysis_run_utc':datetime.now(timezone.utc).isoformat(),'project_origin':'2026-03-23 (author-reported)',
        'reference_recording':summary(engine),'comparison_recording':summary(comparison),
        'reversed_order':{'baseline':'comparison','test':'reference','relative_shifts':log_shift,'heuristic_hints':log_hints,'heuristic_severity':log_severity},
        'selected_order':{'baseline':'reference','test':'comparison','relative_shifts':intended_shift,'heuristic_hints':intended_hints,'heuristic_severity':intended_severity},
        'matched_support_power_audit':fixed,
        'input_sha256':{'reference':digest(engine_path),'comparison':digest(comparison_path)},
        'environment':{'python':platform.python_version(),'numpy':np.__version__,'scipy':scipy.__version__,'matplotlib':matplotlib.__version__,'ffmpeg':subprocess.check_output(['ffmpeg','-version'],text=True).splitlines()[0]},
        'interpretation':'Two user-selected recordings. File roles do not establish content or health labels. Original scores are hand-tuned heuristics, not probabilities.'}
    (out/'results.json').write_text(json.dumps(payload,indent=2,ensure_ascii=False,allow_nan=False)+'\n')
    with (out/'global_features.csv').open('w',newline='') as f:
        w=csv.writer(f);w.writerow(['metric','reference_recording','comparison_recording','definition'])
        for key in ['duration_s','sample_rate_hz','dominant_freq','rms','crest_factor','centroid','flatness','entropy','harmonic_score','peak_count','anomaly_rate','onset_density']:
            w.writerow([key,payload['reference_recording'][key],payload['comparison_recording'][key],'Original prototype definition'])
    for label,r in [('reference',engine),('comparison',comparison)]:
        with (out/f'{label}_frame_features.csv').open('w',newline='') as f:
            w=csv.writer(f);keys=list(r['frames']);w.writerow(keys)
            w.writerows(zip(*(r['frames'][key] for key in keys)))
    import contextlib
    with (out/'prototype_reproduction.txt').open('w') as f,contextlib.redirect_stdout(f):
        print('REVERSED ORDER: comparison baseline, reference test.\nNot validated engine fault inference.')
        print_original('BASELINE (comparison)',comparison)
        print_original('TEST (reference)',engine)
        print('\nRelative shifts:',json.dumps(log_shift,indent=2))
        print('Original heuristic severity:',log_severity)
        print('Original heuristic hints:',log_hints)
        print('\nSELECTED ORDER: reference baseline, comparison test')
        print('Relative shifts:',json.dumps(intended_shift,indent=2))
        print('Original heuristic severity:',intended_severity)
        print('Original heuristic hints:',intended_hints)
    print(json.dumps({'reference_file':engine_path.name,'comparison_file':comparison_path.name,
                     'reference_dominant_hz':engine['global']['dominant_freq'],'comparison_dominant_hz':comparison['global']['dominant_freq'],
                     'selected_order_severity':intended_severity,'matched_duration_s':fixed['matched_duration_s']},indent=2))
    return payload

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--reference','--engine',dest='reference',required=True,type=Path,help='Reference audio file; --engine is a compatibility alias')
    p.add_argument('--comparison',required=True,type=Path,help='Comparison audio file')
    p.add_argument('--output',type=Path,help='Results directory; defaults to a new runs/<UTC timestamp>/results directory')
    a=p.parse_args()
    out=a.output or ROOT/'runs'/datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')/'results'
    run(a.reference,a.comparison,out)
