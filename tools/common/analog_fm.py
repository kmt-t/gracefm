"""
比較用のアナログFM (モノラル) の送受信モデル。

最大偏移 ±75kHz、プリ/ディエンファシス 50µs (日本)、IF フィルタ ±100kHz、音声 15kHz ローパス (ゼロ位相の理想化)、
遅延検波。受信電力 (搬送波電力 = 1) と C/N0 [dB-Hz] から雑音を加える。雑音なしの往復で利得を合わせる。
"""
import numpy as np
from scipy.signal import bilinear, butter, lfilter, resample_poly, sosfiltfilt


class AnalogFM:
    def __init__(self, x, fs, up=12, dev=75e3, tau=50e-6, if_bw=100e3, audio_bw=15e3):
        self.x, self.fs, self.up, self.dev = x, fs, up, dev
        self.fs_rf = fs * up
        b_pre, a_pre = bilinear([tau, 1], [tau / 20, 1], fs)
        pre = lfilter(b_pre, a_pre, x)
        pre = pre / np.abs(pre).max()
        self.tx = np.exp(1j * 2 * np.pi * dev * np.cumsum(resample_poly(pre, up, 1)) / self.fs_rf)
        self.chan = butter(8, if_bw, fs=self.fs_rf, output="sos")
        self.lp = butter(8, audio_bw, fs=self.fs_rf, output="sos")
        self.de = bilinear([tau / 20, 1], [tau, 1], fs)
        ref = self._rx(self.tx)
        self.gain = np.dot(ref, x) / np.dot(ref, ref)

    def _rx(self, r):
        r = sosfiltfilt(self.chan, r.real) + 1j * sosfiltfilt(self.chan, r.imag)
        d = np.concatenate([[0.0], np.angle(r[1:] * np.conj(r[:-1]))]) * self.fs_rf / (2 * np.pi * self.dev)
        a = resample_poly(sosfiltfilt(self.lp, d), 1, self.up)[: len(self.x)]
        return lfilter(*self.de, a)

    def receive(self, cn0_db, rng, gains=None, seg=64, ghost=None):
        """
        gains: seg サンプル (音声のサンプリング周波数で) ごとの電力利得 (フェージング。理想的な AGC)
        ghost: 反射波のリスト [(遅れ [秒], 直接波に対する強さ [dB], 位相 [rad]), ...] (マルチパス)
        """
        sigma = np.sqrt(10 ** (-cn0_db / 10) * self.fs_rf / 2)          # 搬送波電力 = 1
        n = sigma * (rng.standard_normal(len(self.tx)) + 1j * rng.standard_normal(len(self.tx)))
        if gains is not None:
            g = np.repeat(np.maximum(np.asarray(gains), 1e-6), seg * self.up)
            g = np.pad(g, (0, max(0, len(n) - len(g))), mode="edge")[: len(n)]
            n = n / np.sqrt(g)
        sig = self.tx
        if ghost:
            F = np.fft.fft(self.tx)
            fr = np.fft.fftfreq(len(self.tx), 1 / self.fs_rf)
            sig = self.tx.copy()
            for dly, rel_db, ph in ghost:
                sig = sig + 10 ** (rel_db / 20) * np.exp(1j * ph) * np.fft.ifft(F * np.exp(-2j * np.pi * fr * dly))
        return self.gain * self._rx(sig + n)
