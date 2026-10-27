"""合成試験信号 (サンプル音声とスペクトル測定の共通入力)。"""
import numpy as np


def make_demo(fs=48000, dur=10.0, seed=0):
    """弱点を突く合成試験信号: 大きい 55Hz + 小さい和音 (同じ最低域), キック/スネア, 静かなピアノ風 + 残響"""
    rng = np.random.default_rng(seed)
    n = int(fs * dur)
    t = np.arange(n) / fs
    L = np.zeros(n)
    R = np.zeros(n)
    sec1 = t < 6.0
    bass = 0.45 * np.sin(2 * np.pi * 55 * t) * (0.8 + 0.2 * np.sin(2 * np.pi * 0.5 * t)) * sec1
    pad = sum(np.sin(2 * np.pi * f0 * t + ph) for f0, ph in [(660, 0), (825, 1), (990, 2)]) * 0.006 * sec1
    L += bass + 1.2 * pad
    R += bass + 0.8 * pad
    for hit in np.arange(0.0, 6.0, 0.5):
        i0 = int(hit * fs)
        tt = np.arange(int(0.25 * fs)) / fs
        kick = 0.5 * np.sin(2 * np.pi * np.cumsum(50 + 70 * np.exp(-tt * 30)) / fs) * np.exp(-tt * 12)
        e = min(i0 + len(tt), n)
        L[i0:e] += kick[:e - i0]
        R[i0:e] += kick[:e - i0]
    for hit in np.arange(0.25, 6.0, 1.0):
        i0 = int(hit * fs)
        k = int(0.18 * fs)
        tt = np.arange(k) / fs
        env = np.exp(-tt * 25)
        body = 0.15 * np.sin(2 * np.pi * 190 * tt) * np.exp(-tt * 30)
        e = min(i0 + k, n)
        L[i0:e] += (np.diff(rng.standard_normal(k + 1)) * 0.12 * env + body)[:e - i0]
        R[i0:e] += (np.diff(rng.standard_normal(k + 1)) * 0.12 * env + body)[:e - i0]
    for j, f0 in enumerate([261.6, 329.6, 392.0, 523.3, 392.0, 329.6, 293.7, 261.6]):
        i0 = int((6.0 + j * 0.5) * fs)
        tt = np.arange(n - i0) / fs
        tone = sum((0.5 ** h) * np.sin(2 * np.pi * f0 * (h + 1) * tt) for h in range(6))
        tone *= 0.05 * np.exp(-tt * 3) * (1 - np.exp(-tt * 400))
        L[i0:] += tone
        R[i0:] += tone * 0.9
    for dly, g in [(0.031, 0.35), (0.047, 0.3), (0.071, 0.25), (0.113, 0.2), (0.167, 0.15)]:
        d = int(dly * fs)
        L2, R2 = np.zeros(n), np.zeros(n)
        L2[d:], R2[d:] = R[:-d] * g, L[:-d] * g
        L[t >= 6.0] += L2[t >= 6.0]
        R[t >= 6.0] += R2[t >= 6.0]
    x = np.stack([L, R], axis=1)
    return x * (0.89 / np.abs(x).max())
