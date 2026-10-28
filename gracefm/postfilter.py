"""
出力段のポストフィルタ (DAC 前の再構成フィルタ)。すべて整数演算。

符号つき24 bit整数の PCM を、Lanczos 補間で 4 倍にオーバーサンプリングし、元のナイキスト周波数の LPF で鏡像を落としてから、
48 kHz へ再標本化して、符号つき32 bit整数にする。量子化区間への射影は行わない。フィルタ係数は符号つき18 bit
(Q16 または Q17 の整数、gracefm/tables.py) で、積和は 64 bit 整数 (DSP のアキュムレータ 48 bit に収まる範囲)。

遅延: Lanczos の先読み LANCZOS_A 入力サンプルと LPF の群遅延 (オーバーサンプル後の LPF_TAPS // 2 サンプル) を、
ブロックを待つ分とは別に加える。ここでは位相を補正して出力を入力と時刻合わせする。
"""
import numpy as np

from .tables import (LANCZOS_Q16, LPF_32K_Q17, LPF_48K_Q17, RESAMPLE_1_4_Q16, RESAMPLE_3_8_Q16)

OVERSAMPLE = 4
OUT_FS = 48000
LANCZOS_A = 8           # Lanczos 窓の半幅 [入力サンプル]
LPF_TAPS = 511          # オーバーサンプル後の線形位相 FIR (奇数)
INT32_MAX = 2 ** 31 - 1


def _fir_centered(x, h, shift):
    """x (n, ch) と h の畳み込みの中央 n 点 (線形位相)。結果を shift bit 右シフト (四捨五入)"""
    half = len(h) // 2
    out = np.stack([np.convolve(x[:, c], h)[half:half + len(x)] for c in range(x.shape[1])], axis=1)
    return (out + (1 << (shift - 1))) >> shift


def lanczos_upsample(x, oversample=OVERSAMPLE):
    """x: (n, ch) の整数 → (n·oversample, ch)。元の標本点は変えず、間を Lanczos で補間する。端は 0 とみなす"""
    z = np.zeros((len(x) * oversample, x.shape[1]), np.int64)
    z[::oversample] = x
    return _fir_centered(z, np.array(LANCZOS_Q16, np.int64), 16)


def postfilter(y, fs, out_fs=OUT_FS):
    """
    y: Haar 合成後の (n, ch) の符号つき24 bit整数 PCM、fs: そのサンプリング周波数 (32000 または 48000)。
    返り値: out_fs の符号つき32 bit整数 PCM (n·out_fs/fs, ch)。
    """
    assert out_fs == OUT_FS and fs in (32000, 48000)
    x = np.asarray(y, np.int64)
    if x.ndim == 1:
        x = x[:, None]
    x = x << 8                                                         # 24 bit → 32 bit
    up = lanczos_upsample(x)
    lpf = np.array(LPF_32K_Q17 if fs == 32000 else LPF_48K_Q17, np.int64)
    filt = _fir_centered(up, lpf, 17)
    # 128 kHz (または 192 kHz) → 48 kHz の再標本化: ゼロ挿入 (up) → FIR → 間引き (down)
    up_f, down_f, kernel = (3, 8, RESAMPLE_3_8_Q16) if fs == 32000 else (1, 4, RESAMPLE_1_4_Q16)
    stuffed = np.zeros((len(filt) * up_f, filt.shape[1]), np.int64)
    stuffed[::up_f] = filt
    resampled = _fir_centered(stuffed, np.array(kernel, np.int64), 16)[::down_f]
    n_out = len(x) * out_fs // fs
    out = resampled[:n_out]
    return np.clip(out, -INT32_MAX - 1, INT32_MAX)
