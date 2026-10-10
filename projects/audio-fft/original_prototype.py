"""Analysis functions from the author's supplied March 2026 Colab prototype.

The feature definitions and heuristics are preserved for reproduction.
The upload cell and plotting/printing runner are provided separately.
These heuristic scores are not validated engine-fault diagnoses.
"""
import numpy as np
from pydub import AudioSegment
from scipy.signal import find_peaks, get_window, stft, butter, filtfilt, savgol_filter

EPS = 1e-12

def next_pow2(n):
    return 1 if n <= 1 else 2 ** int(np.ceil(np.log2(n)))

def clamp01(x):
    return float(max(0.0, min(1.0, x)))

def safe_mean(x):
    x = np.asarray(x, dtype=float)
    return float(np.nanmean(x)) if len(x) else np.nan

def safe_std(x):
    x = np.asarray(x, dtype=float)
    return float(np.nanstd(x)) if len(x) else np.nan

def robust_zscore(x):
    x = np.asarray(x, dtype=float)
    med = np.nanmedian(x)
    mad = np.nanmedian(np.abs(x - med)) + EPS
    return 0.6745 * (x - med) / mad

def smooth_series(x, win=11, poly=2):
    x = np.asarray(x, dtype=float)
    if len(x) < 7:
        return x
    win = min(win, len(x) if len(x) % 2 == 1 else len(x) - 1)
    if win < 5:
        return x
    if win % 2 == 0:
        win += 1
    poly = min(poly, win - 2)
    return savgol_filter(x, window_length=win, polyorder=poly)

def load_audio(path):
    audio = AudioSegment.from_file(path)
    raw = np.array(audio.get_array_of_samples())
    if audio.channels > 1:
        raw = raw.reshape((-1, audio.channels)).mean(axis=1)
    scale = float(2 ** (8 * audio.sample_width - 1))
    x = raw.astype(np.float32) / scale
    x = np.nan_to_num(x)
    x = np.clip(x, -1.0, 1.0)
    return x, audio.frame_rate, audio.channels, audio.sample_width

def highpass(x, fs, cutoff=20.0, order=3):
    nyq = 0.5 * fs
    cutoff = min(cutoff, nyq * 0.95)
    b, a = butter(order, cutoff / nyq, btype="highpass")
    return filtfilt(b, a, x)

def compute_spectrum(x, fs, n_fft=None):
    x = np.asarray(x, dtype=np.float32)
    x = x - np.mean(x)
    if n_fft is None:
        n_fft = next_pow2(len(x))
    n_fft = max(n_fft, 512)
    window = get_window("hann", len(x), fftbins=True)
    xw = x * window
    spec = np.fft.rfft(xw, n=n_fft)
    mag = np.abs(spec)
    freqs = np.fft.rfftfreq(n_fft, d=1.0 / fs)
    return freqs, mag

def band_energy(freqs, mag, lo, hi):
    mask = (freqs >= lo) & (freqs < hi)
    return float(np.sum(mag[mask]) / (np.sum(mag) + EPS))

def harmonic_search(peak_freqs, fs):
    best_f0 = np.nan
    best_score = 0.0
    matched = []
    if len(peak_freqs) == 0:
        return best_f0, best_score, matched
    candidate_pool = peak_freqs[(peak_freqs >= 20) & (peak_freqs <= min(2000, fs / 4))]
    candidate_pool = candidate_pool[:20] if len(candidate_pool) > 20 else candidate_pool
    for f0 in candidate_pool:
        if f0 <= 0:
            continue
        max_h = int((fs / 2) // f0)
        max_h = max(2, min(max_h, 12))
        hits = []
        checks = 0
        for k in range(2, max_h + 1):
            expected = k * f0
            tol = max(4.0, 0.03 * expected)
            checks += 1
            close = peak_freqs[np.abs(peak_freqs - expected) <= tol]
            if len(close) > 0:
                hits.append(float(close[0]))
        score = len(hits) / max(1, checks)
        if score > best_score:
            best_score = score
            best_f0 = float(f0)
            matched = hits
    return best_f0, float(best_score), matched

def extract_global_features(x, fs):
    x = highpass(x, fs, cutoff=20.0, order=3)
    peak_amp = float(np.max(np.abs(x)))
    rms = float(np.sqrt(np.mean(x ** 2)))
    dc_offset = float(np.mean(x))
    crest_factor = float(peak_amp / (rms + EPS))
    clipping_ratio = float(np.mean(np.abs(x) >= 0.98))
    zcr = float(np.mean(np.abs(np.diff(np.signbit(x)))))
    freqs, mag = compute_spectrum(x, fs, n_fft=next_pow2(len(x)))
    p = mag / (np.sum(mag) + EPS)
    dom_i = int(np.argmax(mag))
    dominant_freq = float(freqs[dom_i])
    dominant_amp = float(mag[dom_i])
    centroid = float(np.sum(freqs * p))
    spread = float(np.sqrt(np.sum(((freqs - centroid) ** 2) * p)))
    flatness = float(np.exp(np.mean(np.log(mag + EPS))) / (np.mean(mag) + EPS))
    entropy = float(-np.sum(p * np.log2(p + EPS)))
    crest_spectrum = float(np.max(mag) / (np.mean(mag) + EPS))
    cdf = np.cumsum(p)
    def rolloff(frac):
        idx = int(np.searchsorted(cdf, frac))
        idx = min(idx, len(freqs) - 1)
        return float(freqs[idx])
    roll50 = rolloff(0.50)
    roll85 = rolloff(0.85)
    roll95 = rolloff(0.95)
    valid = freqs > 0
    if np.sum(valid) >= 8:
        slope = float(np.polyfit(np.log10(freqs[valid]), np.log10(mag[valid] + EPS), 1)[0])
    else:
        slope = np.nan
    noise_floor = float(np.median(mag))
    prominence = max(np.max(mag) * 0.03, noise_floor * 3.0, EPS)
    distance_bins = max(1, int(20 / max(freqs[1] - freqs[0], 1e-9))) if len(freqs) > 1 else 1
    peaks, _ = find_peaks(mag, prominence=prominence, distance=distance_bins)
    peak_freqs = freqs[peaks] if len(peaks) else np.array([])
    peak_amps = mag[peaks] if len(peaks) else np.array([])
    if len(peaks) > 0:
        order = np.argsort(peak_amps)[::-1]
        peak_freqs = peak_freqs[order]
        peak_amps = peak_amps[order]
    best_f0, harmonic_score, matched_harmonics = harmonic_search(peak_freqs, fs)
    bands = [(0, 60), (60, 250), (250, 500), (500, 1000), (1000, 3000), (3000, 8000), (8000, fs / 2)]
    band_shares = [band_energy(freqs, mag, lo, hi) for lo, hi in bands]
    return {
        "x": x, "fs": fs, "duration": len(x) / fs, "samples": len(x),
        "peak_amp": peak_amp, "rms": rms, "dc_offset": dc_offset,
        "crest_factor": crest_factor, "clipping_ratio": clipping_ratio, "zcr": zcr,
        "freqs": freqs, "mag": mag, "dominant_freq": dominant_freq, "dominant_amp": dominant_amp,
        "centroid": centroid, "spread": spread, "flatness": flatness, "entropy": entropy,
        "crest_spectrum": crest_spectrum, "roll50": roll50, "roll85": roll85, "roll95": roll95,
        "slope": slope, "noise_floor": noise_floor, "peak_count": int(len(peaks)),
        "peak_freqs": peak_freqs, "peak_amps": peak_amps, "best_f0": best_f0,
        "harmonic_score": harmonic_score, "matched_harmonics": matched_harmonics,
        "band_shares": band_shares,
    }

def frame_features(x, fs, frame_sec=0.03, hop_sec=0.01):
    frame_len = max(256, int(frame_sec * fs))
    hop_len = max(64, int(hop_sec * fs))
    names = ["time", "rms", "zcr", "dominant_freq", "centroid", "spread", "flatness", "entropy", "crest", "spectral_flux", "peak_count", "harmonic_score"]
    values = {name: [] for name in names}
    prev_mag_norm = None
    for start in range(0, len(x) - frame_len + 1, hop_len):
        frame = x[start:start + frame_len]
        frame = frame - np.mean(frame)
        freqs, mag = compute_spectrum(frame, fs, n_fft=next_pow2(frame_len))
        p = mag / (np.sum(mag) + EPS)
        dom_i = int(np.argmax(mag))
        dom = float(freqs[dom_i])
        centroid = float(np.sum(freqs * p))
        spread = float(np.sqrt(np.sum(((freqs - centroid) ** 2) * p)))
        flatness = float(np.exp(np.mean(np.log(mag + EPS))) / (np.mean(mag) + EPS))
        entropy = float(-np.sum(p * np.log2(p + EPS)))
        crest = float(np.max(mag) / (np.mean(mag) + EPS))
        noise_floor = float(np.median(mag))
        prominence = max(np.max(mag) * 0.03, noise_floor * 3.0, EPS)
        distance_bins = max(1, int(20 / max(freqs[1] - freqs[0], 1e-9))) if len(freqs) > 1 else 1
        peaks, _ = find_peaks(mag, prominence=prominence, distance=distance_bins)
        peak_freqs = freqs[peaks] if len(peaks) else np.array([])
        peak_amps = mag[peaks] if len(peaks) else np.array([])
        if len(peaks) > 0:
            order = np.argsort(peak_amps)[::-1]
            peak_freqs = peak_freqs[order]
        _, harmonic_score, _ = harmonic_search(peak_freqs, fs)
        mag_norm = mag / (np.sum(mag) + EPS)
        if prev_mag_norm is None:
            flux = 0.0
        else:
            flux = float(np.sum(np.maximum(mag_norm - prev_mag_norm, 0.0)))
        prev_mag_norm = mag_norm
        rms = float(np.sqrt(np.mean(frame ** 2)))
        zcr = float(np.mean(np.abs(np.diff(np.signbit(frame)))))
        row = [((start + frame_len / 2) / fs), rms, zcr, dom, centroid, spread, flatness, entropy, crest, flux, int(len(peaks)), harmonic_score]
        for key, value in zip(names, row):
            values[key].append(value)
    return {key: np.array(value) for key, value in values.items()}

def analyze_file(path):
    x, fs, channels, sample_width = load_audio(path)
    x = highpass(x, fs, cutoff=20.0, order=3)
    g = extract_global_features(x, fs)
    fr = frame_features(g["x"], fs, frame_sec=0.03, hop_sec=0.01)
    Z = np.vstack([robust_zscore(fr[key]) for key in ["rms", "zcr", "dominant_freq", "centroid", "flatness", "entropy", "crest", "spectral_flux", "peak_count", "harmonic_score"]]).T
    anomaly_score = np.nanmax(np.abs(Z), axis=1)
    fr["anomaly_score"] = anomaly_score
    threshold = 4.0
    anomaly_idx = np.where(anomaly_score > threshold)[0]
    anomaly_rate = float(len(anomaly_idx) / max(1, len(anomaly_score)))
    flux_sm = smooth_series(fr["spectral_flux"], win=9, poly=2) if len(fr["spectral_flux"]) >= 9 else fr["spectral_flux"]
    flux_z = robust_zscore(flux_sm)
    onset_idx, _ = find_peaks(flux_z, prominence=1.2, distance=max(2, int(0.08 / 0.01)))
    onset_times = fr["time"][onset_idx]
    onset_density = float(len(onset_times) / max(g["duration"], EPS))
    def estimate_decay_time(x, fs, onset_time, search_sec=0.7, rel_level=0.25):
        start = int(onset_time * fs)
        end = min(len(x), start + int(search_sec * fs))
        if start >= len(x) - 1 or end <= start + 10:
            return np.nan, np.nan
        seg = x[start:end]
        env = np.abs(seg)
        peak = float(np.max(env))
        if peak <= EPS:
            return np.nan, np.nan
        thr = peak * rel_level
        hit = np.where(env <= thr)[0]
        decay = float(hit[0] / fs) if len(hit) else float((end - start) / fs)
        return peak, decay
    hit_peaks = []
    hit_decays = []
    for t0 in onset_times:
        p, d = estimate_decay_time(g["x"], fs, t0)
        hit_peaks.append(p)
        hit_decays.append(d)
    return {
        "file": path, "fs": fs, "channels": channels, "sample_width": sample_width,
        "global": g, "frames": fr, "anomaly_rate": anomaly_rate, "anomaly_threshold": threshold,
        "anomaly_idx": anomaly_idx, "onset_idx": onset_idx, "onset_times": onset_times,
        "onset_density": onset_density, "hit_peaks": np.array(hit_peaks, dtype=float),
        "hit_decays": np.array(hit_decays, dtype=float), "flux_z": flux_z,
    }

def score_file(result):
    g = result["global"]
    fr = result["frames"]
    mean_flux = safe_mean(fr["spectral_flux"])
    mean_harm = safe_mean(fr["harmonic_score"])
    mean_flat = safe_mean(fr["flatness"])
    mean_entropy = safe_mean(fr["entropy"])
    mean_crest = safe_mean(fr["crest"])
    dom_std = safe_std(fr["dominant_freq"])
    anomaly_rate = result["anomaly_rate"]
    onset_density = result["onset_density"]
    high_band = g["band_shares"][5] + g["band_shares"][6]
    low_band = g["band_shares"][0] + g["band_shares"][1]
    high_low_ratio = float((high_band + EPS) / (low_band + EPS))
    percussive_score = (
        0.25 * clamp01(mean_flux / 0.05) + 0.20 * clamp01(onset_density / 8.0) +
        0.15 * clamp01(mean_crest / 12.0) + 0.15 * clamp01(anomaly_rate / 0.25) +
        0.10 * clamp01(mean_entropy / 12.0) + 0.15 * (1.0 - clamp01(mean_harm)))
    continuous_score = (
        0.35 * clamp01(mean_harm) + 0.15 * (1.0 - clamp01(mean_flux / 0.05)) +
        0.10 * (1.0 - clamp01(onset_density / 8.0)) + 0.10 * (1.0 - clamp01(mean_flat / 0.5)))
    noise_score = (
        0.25 * clamp01(mean_flat / 0.3) + 0.20 * clamp01(mean_entropy / 12.0) +
        0.20 * clamp01(high_low_ratio / 1.2) + 0.20 * clamp01(g["centroid"] / 4000.0) +
        0.15 * clamp01(g["roll95"] / (g["fs"] / 2)))
    instability_score = (
        0.35 * clamp01(dom_std / 20.0) + 0.25 * clamp01(mean_flux / 0.05) +
        0.20 * clamp01(anomaly_rate / 0.25) + 0.20 * clamp01(safe_std(fr["harmonic_score"]) / 0.35))
    return {
        "percussive_score": percussive_score, "continuous_score": continuous_score,
        "noise_score": noise_score, "instability_score": instability_score,
        "mean_flux": mean_flux, "mean_harm": mean_harm, "mean_flat": mean_flat,
        "mean_entropy": mean_entropy, "mean_crest": mean_crest, "dom_std": dom_std,
        "high_low_ratio": high_low_ratio, "anomaly_rate": anomaly_rate, "onset_density": onset_density,
    }

def verdict_from_scores(scores):
    p, c, n, u = (scores[key] for key in ["percussive_score", "continuous_score", "noise_score", "instability_score"])
    if p > c + 0.12 and p > 0.45:
        base = "Likely percussive / drum-like"
    elif c > p + 0.12 and c > 0.40:
        base = "Likely continuous / tonal / mechanical"
    else:
        base = "Mixed or ambiguous"
    flags = []
    if n > 0.55:
        flags.append("noisy / rough")
    if u > 0.55:
        flags.append("unstable over time")
    if not flags:
        flags.append("fairly stable")
    return base + " | " + ", ".join(flags)

def compare_results(base_res, test_res):
    b, t = base_res["global"], test_res["global"]
    bs, ts = score_file(base_res), score_file(test_res)
    def rel_change(a, b):
        return float((b - a) / (abs(a) + EPS))
    shifts = {key: rel_change(b[key], t[key]) for key in ["dominant_freq", "centroid", "flatness", "entropy", "crest_factor", "harmonic_score", "peak_count", "roll95"]}
    shifts.update({"anomaly_rate": rel_change(base_res["anomaly_rate"], test_res["anomaly_rate"]),
                   "onset_density": rel_change(base_res["onset_density"], test_res["onset_density"]),
                   "high_low_ratio": rel_change(bs["high_low_ratio"], ts["high_low_ratio"])})
    hints = []
    if t["harmonic_score"] < b["harmonic_score"] - 0.15 or t["harmonic_score"] < 0.35:
        hints.append("possible irregular timing / missing structure")
    if t["flatness"] > b["flatness"] + 0.08 or t["noise_floor"] > b["noise_floor"] * 1.25:
        hints.append("possible extra noise / wear / roughness")
    if ts["high_low_ratio"] > bs["high_low_ratio"] * 1.2 or t["centroid"] > b["centroid"] * 1.15:
        hints.append("more high-frequency energy than baseline")
    if test_res["onset_density"] > base_res["onset_density"] * 1.5:
        hints.append("more transient impacts / knocks / drum-like events")
    if test_res["anomaly_rate"] > base_res["anomaly_rate"] * 1.5:
        hints.append("time-varying instability increased")
    if abs(t["dominant_freq"] - b["dominant_freq"]) > max(15.0, 0.12 * b["dominant_freq"]):
        hints.append("main frequency shifted noticeably")
    if t["crest_factor"] > b["crest_factor"] * 1.2:
        hints.append("more spiky / impulsive waveform")
    if not hints:
        hints.append("no strong fault signature compared to baseline")
    severity = (
        0.25 * clamp01(abs(shifts["harmonic_score"])) + 0.20 * clamp01(abs(shifts["flatness"])) +
        0.15 * clamp01(abs(shifts["centroid"])) + 0.15 * clamp01(abs(shifts["anomaly_rate"])) +
        0.10 * clamp01(abs(shifts["onset_density"])) + 0.15 * clamp01(abs(shifts["high_low_ratio"])))
    return shifts, hints, severity
