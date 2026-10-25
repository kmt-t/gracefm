"""
出力段のポストフィルタ (DAC 前の再構成フィルタ)。

Haar 合成後の PCM を int32 にし、Lanczos 補間で 8 倍にオーバーサンプリングし、
元のナイキスト周波数の LPF で鏡像を落としてから、48 kHz / int32 へダウンサンプルする。
量子化区間への射影は行わない。フィルタ演算は float64 で行い (int32 は float64 で厳密に表せる)、
入力と出力の境界でだけ int32 に丸める。

遅延: Lanczos の先読み LANCZOS_A 入力サンプルと LPF の群遅延 (オーバーサンプル後の
LPF_TAPS // 2 サンプル) を、ブロックを待つ分とは別に加える。ここでは位相を補正して出力を入力と時刻合わせする。
"""
import numpy as np
from scipy.signal import firwin, oaconvolve, resample_poly

OVERSAMPLE = 8
OUT_FS = 48000
LANCZOS_A = 8           # Lanczos 窓の半幅 [入力サンプル]。大きいほど高域の振幅誤差が小さい
LPF_TAPS = 1023         # オーバーサンプル後の線形位相 FIR (奇数)
INT32_MAX = 2 ** 31 - 1


def to_int32(y):
    """±1 に正規化した float PCM → int32 (範囲外は飽和)"""
    return np.clip(np.round(np.asarray(y, float) * INT32_MAX), -INT32_MAX - 1, INT32_MAX).astype(np.int32)


def lanczos_kernel(oversample=OVERSAMPLE, a=LANCZOS_A):
    """オーバーサンプル後のレートでの Lanczos 補間核 (長さ 2·a·oversample + 1)"""
    n = np.arange(-a * oversample, a * oversample + 1) / oversample
    return np.sinc(n) * np.sinc(n / a)


def lanczos_upsample(x, oversample=OVERSAMPLE, a=LANCZOS_A):
    """x: (n, ch) → (n·oversample, ch)。元の標本点は変えず、間を Lanczos で補間する。端は 0 とみなす"""
    x = np.asarray(x, float)
    z = np.zeros((len(x) * oversample,) + x.shape[1:])
    z[::oversample] = x
    h = lanczos_kernel(oversample, a)
    half = len(h) // 2
    return oaconvolve(z, h[:, None], axes=0)[half:half + len(z)]


def postfilter(y, fs, out_fs=OUT_FS, oversample=OVERSAMPLE, a=LANCZOS_A):
    """
    y: Haar 合成後の (n, ch) float PCM (±1) または int32、fs: そのサンプリング周波数。
    返り値: out_fs の int32 PCM (n·out_fs/fs, ch)。
    """
    y = np.asarray(y)
    if y.dtype == np.int32:
        x = y.astype(float)
    else:
        x = to_int32(y).astype(float)
    if x.ndim == 1:
        x = x[:, None]
    up = lanczos_upsample(x, oversample, a)
    fs_up = fs * oversample
    # 元のナイキスト周波数 (帯域端の 2% 手前を通過域端とする) の線形位相 LPF で鏡像を落とす
    lpf = firwin(LPF_TAPS, 0.98 * fs / 2, window=("kaiser", 9.0), fs=fs_up)
    half = LPF_TAPS // 2
    filt = oaconvolve(up, lpf[:, None], axes=0)[half:half + len(up)]
    g = np.gcd(out_fs, fs_up)
    down = resample_poly(filt, out_fs // g, fs_up // g, axis=0, window=("kaiser", 9.0))
    n_out = int(round(len(x) * out_fs / fs))
    down = down[:n_out]
    return np.clip(np.round(down), -INT32_MAX - 1, INT32_MAX).astype(np.int32)
