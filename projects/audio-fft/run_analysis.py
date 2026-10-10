"""Run the author's original analysis and all 15 plots; also save the outputs."""
from pathlib import Path
from contextlib import redirect_stdout
import argparse
import io
import numpy as np
import matplotlib.pyplot as plt
from scipy.signal import stft
from original_prototype import analyze_file, score_file, compare_results, verdict_from_scores


def print_file_summary(tag, result, scores):
    g = result["global"]
    print("\n" + "=" * 70)
    print(tag)
    print("=" * 70)
    print(f"File           : {result['file']}")
    print(f"Sample rate    : {result['fs']} Hz")
    print(f"Channels       : {result['channels']}")
    print(f"Duration       : {g['duration']:.2f} s")
    print(f"Peak amplitude : {g['peak_amp']:.6f}")
    print(f"RMS            : {g['rms']:.6f}")
    print(f"Crest factor   : {g['crest_factor']:.3f}")
    print(f"Clipping ratio : {g['clipping_ratio']:.4f}")
    print(f"Dominant freq  : {g['dominant_freq']:.2f} Hz")
    print(f"Centroid       : {g['centroid']:.2f} Hz")
    print(f"Flatness       : {g['flatness']:.4f}")
    print(f"Entropy        : {g['entropy']:.4f}")
    print(f"Harmonic score : {g['harmonic_score']:.4f}")
    print(f"Peak count     : {g['peak_count']}")
    print(f"Anomaly rate   : {result['anomaly_rate']:.4f}")
    print(f"Onset density  : {result['onset_density']:.2f} / sec")
    print(f"Verdict        : {verdict_from_scores(scores)}")
    print("\nTop peaks:")
    if len(g["peak_freqs"]) == 0:
        print("  none found")
    else:
        for j in range(min(10, len(g["peak_freqs"]))):
            print(f"  {j+1:02d}. {g['peak_freqs'][j]:10.2f} Hz | amp {g['peak_amps'][j]:.6f}")
    print("\nBand energy share:")
    band_labels = ["0-60", "60-250", "250-500", "500-1k", "1k-3k", "3k-8k", "8k+"]
    for label, share in zip(band_labels, g["band_shares"]):
        print(f"  {label:>8}: {share:.4f}")
    if len(result["onset_times"]) > 0:
        print("\nTop detected hits:")
        for j in range(min(10, len(result["onset_times"]))):
            print(f"  hit {j+1:02d}: t={result['onset_times'][j]:7.3f}s | peak={result['hit_peaks'][j]:.4f} | decay~{result['hit_decays'][j]:.3f}s")


def save_and_show(filename, output_dir, show):
    plt.savefig(output_dir / filename, dpi=150)
    if show:
        plt.show()
    plt.close()


def plot_pair_time(series_name, ylabel, base_res, test_res, output_dir, show):
    plt.figure(figsize=(12, 4))
    plt.plot(base_res["frames"]["time"], base_res["frames"][series_name], label="baseline")
    plt.plot(test_res["frames"]["time"], test_res["frames"][series_name], label="test")
    plt.title(ylabel)
    plt.xlabel("Time (s)")
    plt.ylabel(ylabel)
    plt.legend()
    plt.tight_layout()
    save_and_show(f"comparison_{series_name}.png", output_dir, show)


def plot_single_wave_and_fft(result, title_prefix, output_dir, show):
    g = result["global"]
    t = np.arange(len(g["x"])) / g["fs"]
    prefix = title_prefix.lower()

    plt.figure(figsize=(12, 4))
    plt.plot(t, g["x"])
    plt.title(f"{title_prefix} - Waveform")
    plt.xlabel("Time (s)")
    plt.ylabel("Amplitude")
    plt.tight_layout()
    save_and_show(f"{prefix}_waveform.png", output_dir, show)

    plt.figure(figsize=(12, 4.5))
    plt.plot(g["freqs"], g["mag"])
    plt.title(f"{title_prefix} - FFT Spectrum")
    plt.xlabel("Frequency (Hz)")
    plt.ylabel("Magnitude")
    plt.xlim(0, min(g["fs"] / 2, 10000))
    plt.tight_layout()
    save_and_show(f"{prefix}_fft_spectrum.png", output_dir, show)

    plt.figure(figsize=(12, 4.5))
    plt.plot(g["freqs"], g["mag"])
    if len(g["peak_freqs"]) > 0:
        for fpk, apk in zip(g["peak_freqs"][:12], g["peak_amps"][:12]):
            plt.scatter([fpk], [apk])
            plt.text(fpk, apk, f"{fpk:.0f}", fontsize=8)
    plt.title(f"{title_prefix} - Main Peaks")
    plt.xlabel("Frequency (Hz)")
    plt.ylabel("Magnitude")
    plt.xlim(0, min(g["fs"] / 2, 10000))
    plt.tight_layout()
    save_and_show(f"{prefix}_main_peaks.png", output_dir, show)

    f, tt, Zxx = stft(
        g["x"], fs=g["fs"], window="hann",
        nperseg=min(2048, len(g["x"])),
        noverlap=min(1536, max(0, len(g["x"]) // 10)),
        boundary=None,
    )
    S = np.abs(Zxx)
    plt.figure(figsize=(12, 4.8))
    plt.pcolormesh(tt, f, 20 * np.log10(S + 1e-10), shading="auto")
    plt.title(f"{title_prefix} - Spectrogram")
    plt.xlabel("Time (s)")
    plt.ylabel("Frequency (Hz)")
    plt.ylim(0, min(g["fs"] / 2, 10000))
    plt.colorbar(label="dB")
    plt.tight_layout()
    save_and_show(f"{prefix}_spectrogram.png", output_dir, show)


def run(baseline_file, test_file, output_dir, show=True):
    baseline_file = Path(baseline_file).resolve()
    test_file = Path(test_file).resolve()
    if baseline_file == test_file:
        raise ValueError("Choose two different recordings.")
    output_dir = Path(output_dir).resolve()
    project_dir = Path(__file__).resolve().parent if "__file__" in globals() else None
    if project_dir and any(output_dir.is_relative_to(project_dir / name) for name in ["results", "figures"]):
        raise ValueError("Choose an output directory outside the archived results/ and figures/.")
    output_dir.mkdir(parents=True, exist_ok=True)

    base_res = analyze_file(str(baseline_file))
    test_res = analyze_file(str(test_file))
    base_scores = score_file(base_res)
    test_scores = score_file(test_res)
    shifts, hints, severity = compare_results(base_res, test_res)

    report = io.StringIO()
    with redirect_stdout(report):
        print_file_summary("BASELINE / REFERENCE", base_res, base_scores)
        print_file_summary("TEST / SUSPECT", test_res, test_scores)
        print("\n" + "=" * 70)
        print("BASELINE VS TEST COMPARISON")
        print("=" * 70)
        print(f"Overall severity score: {severity:.3f}")
        print("\nRelative shifts (test vs baseline):")
        for k, v in shifts.items():
            print(f"  {k:>16}: {v:+.3f}")
        print("\nLikely issues:")
        for h in hints:
            print(" -", h)
    text = report.getvalue()
    print(text, end="")
    (output_dir / "analysis.txt").write_text(text + "\nDone.\n", encoding="utf-8")

    plot_single_wave_and_fft(base_res, "Baseline", output_dir, show)
    plot_single_wave_and_fft(test_res, "Test", output_dir, show)
    plot_pair_time("rms", "RMS over time", base_res, test_res, output_dir, show)
    plot_pair_time("centroid", "Spectral centroid over time", base_res, test_res, output_dir, show)
    plot_pair_time("flatness", "Spectral flatness over time", base_res, test_res, output_dir, show)
    plot_pair_time("spectral_flux", "Spectral flux over time", base_res, test_res, output_dir, show)
    plot_pair_time("harmonic_score", "Harmonic score over time", base_res, test_res, output_dir, show)

    plt.figure(figsize=(12, 4))
    plt.plot(base_res["frames"]["time"], base_res["frames"]["anomaly_score"], label="baseline")
    plt.plot(test_res["frames"]["time"], test_res["frames"]["anomaly_score"], label="test")
    plt.axhline(base_res["anomaly_threshold"], linestyle="--")
    plt.title("Anomaly score comparison")
    plt.xlabel("Time (s)")
    plt.ylabel("Score")
    plt.legend()
    plt.tight_layout()
    save_and_show("comparison_anomaly_score.png", output_dir, show)

    plt.figure(figsize=(12, 4))
    plt.plot(base_res["frames"]["time"], base_res["flux_z"], label="baseline")
    plt.plot(test_res["frames"]["time"], test_res["flux_z"], label="test")
    plt.title("Onset / transient detector comparison")
    plt.xlabel("Time (s)")
    plt.ylabel("Flux z-score")
    plt.legend()
    plt.tight_layout()
    save_and_show("comparison_onset_detector.png", output_dir, show)
    print("\nDone.")
    print("Saved text and all 15 graphs to:", output_dir)
    return base_res, test_res


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reference", "--engine", dest="reference", required=True)
    parser.add_argument("--comparison", required=True)
    parser.add_argument("--output", default="audio_fft_results")
    args = parser.parse_args()
    run(args.reference, args.comparison, args.output, show=False)
