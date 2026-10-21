"""
比較用のアナログAM (中波放送) の送受信モデル。

DSB-AM (搬送波あり)、音声はピークで 100% 変調、音声帯域 7.5kHz (RF は ±7.5kHz)、包絡線検波。
受信電力 (搬送波 + 側波帯の合計) を 1 に正規化し、C/N0 [dB-Hz] から雑音を加える。雑音なしの往復で利得を合わせる。
中波の伝搬 (地表波・夜間の遠方局)、パルス性の雑音は含まない。
"""
import numpy as np
from scipy.signal import butter, sosfiltfilt


class AnalogAM:
    def __init__(self, x, fs, bw=7500.0):
        self.x, self.fs = x, fs
        self.lp = butter(8, bw, fs=fs, output="sos")
        a = sosfiltfilt(self.lp, x)
        a = a / np.abs(a).max()
        tx = 1.0 + a
        self.tx = tx / np.sqrt(np.mean(tx ** 2))
        ref = self._rx(self.tx.astype(complex))
        self.gain = np.dot(ref, x) / np.dot(ref, ref)

    def _rx(self, r):
        r = sosfiltfilt(self.lp, r.real) + 1j * sosfiltfilt(self.lp, r.imag)
        e = np.abs(r)
        return sosfiltfilt(self.lp, e - e.mean())

    def receive(self, cn0_db, rng):
        sigma = np.sqrt(10 ** (-cn0_db / 10) * self.fs / 2)
        n = sigma * (rng.standard_normal(len(self.tx)) + 1j * rng.standard_normal(len(self.tx)))
        return self.gain * self._rx(self.tx + n)
