"""
出力段。受信した PCM を 48 kHz の符号つき32 bit整数にする。すべて整数演算で、DSP (gracefm/dsp.py) の幅に従う。

48 kHz 系はフィルタを通さず、32 kHz 系だけ 3/2 の再標本化をする (3 倍のゼロ挿入 → 95 タップの FIR → 2 分の 1)。
再構成は DAC に任せる。量子化区間への射影は行わない。

幅 (docs/FIXED.md): 信号は 25 bit (乗算器の A 入力。24 bit の PCM に 1 bit のガード)、係数は 18 bit 以内 (B 入力)、積和は 48 bit (アキュムレータ)。
累積の上限は、係数の絶対値の和 × 2^24 が 2^47 未満であることを tests/test_fixed.py で確かめる。

遅延: 32 kHz 系は FIR の群遅延 (96 kHz で RESAMPLE_DELAY サンプル) を、ブロックを待つ分とは別に加える。48 kHz 系は 0。
ここでは位相を補正して出力を入力と時刻合わせする。
"""
import numpy as np

from .dsp import round_shift, saturate
from .tables import RESAMPLE_3_2_Q16

OUT_FS = 48000
GUARD_BITS = 1          # 24 bit の PCM に足すガード (25 bit = 乗算器の A 入力)
OUT_SHIFT = 32 - 24 - GUARD_BITS                 # 出力 (32 bit) へ戻すシフト
RESAMPLE_DELAY = len(RESAMPLE_3_2_Q16) // 2      # 32 kHz 系の FIR の群遅延 [96 kHz のサンプル]


def _fir_centered(x, h, shift):
    """x (n, ch) と h の畳み込みの中央 n 点 (線形位相)。積和を shift bit 右シフト (四捨五入) し、25 bit に飽和させる"""
    half = len(h) // 2
    out = np.stack([np.convolve(x[:, c], h)[half:half + len(x)] for c in range(x.shape[1])], axis=1)
    return saturate(round_shift(out, shift))


def postfilter(y, fs, out_fs=OUT_FS):
    """
    y: 合成後の (n, ch) の符号つき24 bit整数 PCM、fs: そのサンプリング周波数 (32000 または 48000)。
    返り値: out_fs の符号つき32 bit整数 PCM (n·out_fs/fs, ch)。
    """
    assert out_fs == OUT_FS and fs in (32000, 48000)
    x = np.asarray(y, np.int64)
    if x.ndim == 1:
        x = x[:, None]
    x = x << GUARD_BITS                                                # 24 bit → 25 bit
    if fs == OUT_FS:
        return x << OUT_SHIFT
    stuffed = np.zeros((len(x) * 3, x.shape[1]), np.int64)
    stuffed[::3] = x
    return _fir_centered(stuffed, np.array(RESAMPLE_3_2_Q16, np.int64), 16)[::2] << OUT_SHIFT


def select_by_quality(y, alt, quality, block, use_alt=(1, 2), fade=16):
    """ブロックごとの品質コード (0 正常, 1 高域欠落, 2 欠落) に応じて、y と alt を切り替える。
    use_alt に入るコードのブロックでは alt を使う。切り替えは、そのブロックの先頭から fade サンプルの直線で行う (因果的)。
    重みは Q15 の整数。受信の既定出力では gracefm.iir.apply_alt から使われる。"""
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
