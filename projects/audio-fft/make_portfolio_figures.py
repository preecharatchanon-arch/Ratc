"""Readable paired views of the original FFT/STFT calculations, without changing analysis."""
from pathlib import Path
import argparse
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from scipy.signal import stft
from original_prototype import analyze_file

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--reference', required=True)
    parser.add_argument('--comparison', required=True)
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    paths = [Path(args.reference).resolve(), Path(args.comparison).resolve()]
    if paths[0] == paths[1]:
        raise ValueError('Choose two different recordings.')
    out = Path(args.output)
    out.mkdir(parents=True, exist_ok=True)
    results = [analyze_file(str(p)) for p in paths]
    labels = ['Reference', 'Comparison']
    colors = ['#087c86', '#c56b27']
    plt.rcParams.update({'font.size': 12, 'axes.spines.top': False,
                         'axes.spines.right': False, 'savefig.dpi': 160})
    fig, axes = plt.subplots(2, 1, figsize=(10, 7.5))
    for ax, result, role, color in zip(axes, results, labels, colors):
        g = result['global']
        ax.plot(g['freqs'], g['mag'], color=color, linewidth=0.9)
        ax.set(xlim=(0, 1000), xlabel='Frequency (Hz)', ylabel='FFT magnitude')
        ax.set_title(f"{role}: {Path(result['file']).name}", loc='left', fontsize=10)
        peak = g['dominant_freq']
        amp = g['dominant_amp']
        ax.scatter([peak], [amp], color=color, s=25, zorder=3)
        ax.annotate(f'{peak:.2f} Hz', (peak, amp), xytext=(35, -2),
                    textcoords='offset points', fontsize=14, fontweight='bold',
                    arrowprops={'arrowstyle': '-', 'color': color})
        ax.grid(alpha=0.16)
        ax.margins(y=0.2)
    fig.suptitle('FFT | dominant frequency structure', fontsize=19, fontweight='bold')
    fig.text(0.5, 0.015, 'Original Hann-window rFFT, zoomed to 0–1 kHz. Native sample rates; separate magnitude scales.',
             ha='center', fontsize=9)
    fig.tight_layout(rect=(0, .035, 1, .95))
    fig.savefig(out / 'original_fft_pair.png')
    plt.close(fig)

    fig, axes = plt.subplots(2, 1, figsize=(10, 7.5))
    for ax, result, role in zip(axes, results, labels):
        g = result['global']
        f, times, z = stft(g['x'], fs=g['fs'], window='hann',
                          nperseg=min(2048, len(g['x'])),
                          noverlap=min(1536, max(0, len(g['x']) // 10)), boundary=None)
        image = ax.pcolormesh(times, f / 1000, 20 * np.log10(np.abs(z) + 1e-10),
                             shading='auto', cmap='magma', vmin=-110, vmax=-25)
        ax.set(ylim=(0, 10), xlabel='Time (s)', ylabel='Frequency (kHz)')
        ax.set_title(f"{role}: {Path(result['file']).name}", loc='left', fontsize=10)
        fig.colorbar(image, ax=ax, label='Magnitude (dB)')
    fig.suptitle('STFT | frequency structure over time', fontsize=19, fontweight='bold')
    fig.text(0.5, 0.015, 'Original STFT: 2,048-sample Hann window, 1,536 overlap. Full recordings; common display colour scale.',
             ha='center', fontsize=9)
    fig.tight_layout(rect=(0, .035, 1, .95))
    fig.savefig(out / 'original_stft_pair.png')
    plt.close(fig)

if __name__ == '__main__':
    main()
