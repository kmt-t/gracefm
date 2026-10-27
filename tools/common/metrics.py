"""
評価用の指標。

snr_db / seg_snr_db : 一般的な SNR とセグメンタル SNR (20ms 窓, [-10, 80]dB にクリップ)
BandMetric          : 聴感帯域 (0-100-200-400-750-1.5k-3k-6k-12k-20kHz) ごとに、
                      STFT の各フレームで SNR = 10log10((信号 + 床) / ノイズ) を求め
                      [-10, cap] dB にクリップして平均したもの。床 = -90dB, cap = 40dB。
                      誤差の「量」を見る目安で、高域のざらつきなど「質」は捉えきれない。
"""
import numpy as np

EDGES = [0, 100, 200, 400, 750, 1500, 3000, 6000, 12000, 20000]


def snr_db(ref, test):
    return 10 * np.log10(np.sum(ref ** 2) / max(np.sum((ref - test) ** 2), 1e-30))


def seg_snr_db(ref, test, fs, win_ms=20.0, floor_db=-60.0):
    w = int(fs * win_ms / 1000)
    vals = []
    for i in range(0, len(ref) - w, w):
        r = ref[i:i + w]
        p = np.mean(r ** 2)
        if 10 * np.log10(p + 1e-30) < floor_db:
            continue
        e = np.mean((r - test[i:i + w]) ** 2)
        vals.append(np.clip(10 * np.log10(p / max(e, 1e-30)), -10, 80))
    return float(np.mean(vals)) if vals else float("nan")


class BandMetric:
    def __init__(self, x, fs, nfft=1024, floor_db=-90.0, cap_db=40.0):
        self.nfft = nfft
        self.hop = nfft // 2
        self.win = np.hanning(nfft)
        f = np.fft.rfftfreq(nfft, 1 / fs)
        self.groups = [(f >= lo) & (f < hi) for lo, hi in zip(EDGES[:-1], EDGES[1:]) if lo < fs / 2]
        self.cap = cap_db
        ref = self._bandpow(np.sin(2 * np.pi * 1000 * np.arange(nfft * 4) / fs)).max()
        self.S = sum(self._bandpow(x[:, c]) for c in range(x.shape[1])) + ref * 10 ** (floor_db / 10)

    def _bandpow(self, y):
        nfr = (len(y) - self.nfft) // self.hop + 1
        idx = np.arange(self.nfft)[None, :] + self.hop * np.arange(nfr)[:, None]
        P = np.abs(np.fft.rfft(y[idx] * self.win, axis=1)) ** 2
        return np.stack([P[:, g].sum(1) for g in self.groups], axis=1)

    def __call__(self, err):
        """err: (n, ch) の誤差波形"""
        N = sum(self._bandpow(err[:, c]) for c in range(err.shape[1]))
        return float(np.clip(10 * np.log10(self.S / np.maximum(N, 1e-30)), -10, self.cap).mean())


def thd(y, fs, f0, fmax=15000.0, skip=0.1):
    """
    正弦波を通した出力 y (1次元) の歪み率。返り値: (THD [%], THD+N [%])
      THD   = √(高調波 2〜 (fmax まで) の電力) / 基本波の振幅
      THD+N = √(20Hz〜fmax の、基本波以外の全電力) / 基本波の振幅
    先頭と末尾の skip 秒を除き、ブラックマン・ハリス窓の FFT で求める (基本波・高調波は ±3 ビンを合計)。
    """
    from scipy.signal.windows import blackmanharris
    n0 = int(skip * fs)
    y = np.asarray(y, float)[n0: len(y) - n0]
    w = blackmanharris(len(y))
    P = np.abs(np.fft.rfft(y * w)) ** 2
    f = np.fft.rfftfreq(len(y), 1 / fs)
    df = f[1]

    def band(fc):
        i = int(round(fc / df))
        return slice(max(i - 3, 0), i + 4)
    fund = P[band(f0)].sum()
    harm = sum(P[band(h * f0)].sum() for h in range(2, int(fmax // f0) + 1))
    inb = (f >= 20) & (f <= fmax)
    mask = inb.copy()
    mask[band(f0)] = False
    return 100 * np.sqrt(harm / fund), 100 * np.sqrt(P[mask].sum() / fund)
