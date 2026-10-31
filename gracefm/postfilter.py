"""
出力段のポストフィルタ (DAC 前の再構成フィルタ)。すべて整数演算で、DSP (gracefm/dsp.py) の幅に従う。

符号つき24 bit整数の PCM に 1 bit のガードを足して 25 bit にし、Lanczos 補間で 4 倍にオーバーサンプリングする。
元のナイキスト周波数の LPF で鏡像を落としてから、48 kHz へ再標本化して、符号つき32 bit整数にする。
量子化区間への射影は行わない。

幅 (docs/FIXED.md): 信号は 25 bit (乗算器の A 入力)、係数は 18 bit 以内 (B 入力)、積和は 48 bit (アキュムレータ)。
各段の出力は 25 bit に飽和させる (Lanczos のオーバーシュートは入力の約 1.76 倍まで出るため)。
累積の上限は、係数の絶対値の和 × 2^24 が 2^47 未満であることを tests/test_fixed.py で確かめる。

遅延: Lanczos の先読み LANCZOS_A 入力サンプルと LPF の群遅延 (オーバーサンプル後の LPF_TAPS // 2 サンプル) を、
ブロックを待つ分とは別に加える。ここでは位相を補正して出力を入力と時刻合わせする。
"""
import numpy as np

from .dsp import round_shift, saturate
from .tables import (
    LANCZOS_Q16,
    LPF_32K_Q17,
    LPF_48K_Q17,
    RESAMPLE_1_4_Q16,
    RESAMPLE_3_8_Q16,
)

OVERSAMPLE = 4
OUT_FS = 48000
LANCZOS_A = 8           # Lanczos 窓の半幅 [入力サンプル]
LPF_TAPS = 511          # オーバーサンプル後の線形位相 FIR (奇数)
GUARD_BITS = 1          # 24 bit の PCM に足すガード (25 bit = 乗算器の A 入力)
OUT_SHIFT = 32 - 24 - GUARD_BITS                 # 出力 (32 bit) へ戻すシフト


def _fir_centered(x, h, shift):
    """x (n, ch) と h の畳み込みの中央 n 点 (線形位相)。積和を shift bit 右シフト (四捨五入) し、25 bit に飽和させる"""
    half = len(h) // 2
    out = np.stack([np.convolve(x[:, c], h)[half:half + len(x)] for c in range(x.shape[1])], axis=1)
    return saturate(round_shift(out, shift))


def lanczos_upsample(x, oversample=OVERSAMPLE):
    """x: (n, ch) の 25 bit 整数 → (n·oversample, ch)。元の標本点は変えず、間を Lanczos で補間する。端は 0 とみなす"""
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
    x = x << GUARD_BITS                                                # 24 bit → 25 bit
    up = lanczos_upsample(x)
    lpf = np.array(LPF_32K_Q17 if fs == 32000 else LPF_48K_Q17, np.int64)
    filt = _fir_centered(up, lpf, 17)
    # 128 kHz (または 192 kHz) → 48 kHz の再標本化: ゼロ挿入 (up) → FIR → 間引き (down)
    up_f, down_f, kernel = (3, 8, RESAMPLE_3_8_Q16) if fs == 32000 else (1, 4, RESAMPLE_1_4_Q16)
    stuffed = np.zeros((len(filt) * up_f, filt.shape[1]), np.int64)
    stuffed[::up_f] = filt
    resampled = _fir_centered(stuffed, np.array(kernel, np.int64), 16)[::down_f]
    n_out = len(x) * out_fs // fs
    return resampled[:n_out] << OUT_SHIFT


def select_by_quality(y, alt, quality, block, use_alt=(1, 2), fade=16):
    """ブロックごとの品質コード (0 正常, 1 高域欠落, 2 欠落) に応じて、y と alt を切り替える。
    use_alt に入るコードのブロックでは alt を使う。切り替えは、そのブロックの先頭から fade サンプルの直線で行う (因果的)。
    重みは Q15 の整数。fade は 2 のべき乗にする。既定の出力には使わない (呼び出し側が選ぶ)。"""
    y = np.asarray(y, np.int64)
    alt = np.asarray(alt, np.int64)
    n = len(y)
    out = y.copy()                                             # コードのない末尾の端数サンプルは y のまま
    w = 0                                                      # Q15 の重み (0 = y, 32768 = alt)
    for i, q in enumerate(quality):
        s0 = i * block
        if s0 >= n:
            break
        s1 = min(n, s0 + block)
        target = 32768 if int(q) in use_alt else 0
        m = np.minimum(np.arange(1, s1 - s0 + 1, dtype=np.int64), fade)
        r = (w + ((target - w) * m) // fade)[:, None]          # 各サンプルの重み
        out[s0:s1] = (y[s0:s1] * (32768 - r) + alt[s0:s1] * r + 16384) >> 15
        w = int(r[-1, 0])
    return out
