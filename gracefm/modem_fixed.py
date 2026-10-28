"""
整数だけで動く変調・復調 (QPSK、階層16QAM)。信号点は小数 FRAC bit の固定小数点 (±1 = 2^FRAC、平均シンボルエネルギー 1)。

変調: ビット列 → (I, Q) の整数。ビット列の並びは gracefm.modem と同じで、「全シンボルの強い位置 (符号) →
  全シンボルの弱い位置 (位置の Gray 符号)」の順。
復調: 軸ごとに独立な max-log の LLR (正 = 0 らしい) を整数で作る。LLR(bit) = (D1 - D0) / (2 σ²)。D は、そのビットが
  1 / 0 の信号点のうち受信点に最も近いものとの距離の二乗 (乗算器の幅 18 bit に収めるため、距離は右シフトして二乗する)。
  σ² (軸あたりの雑音分散) は、フレームごとに、受信点と最寄りの信号点との差から求める。除算は整数の除算 (ハードウェアでは
  除算器か逆数のテーブル)。
DSP に依存する幅は gracefm.dsp にある。
"""
from math import isqrt

import numpy as np

from .dsp import CONST_BITS

FRAC = 21
DIST_BITS = CONST_BITS - 1                      # 二乗する距離の幅 (符号を除く)
LLR_BITS = 6
LLR_MAX = (1 << (LLR_BITS - 1)) - 1
LLR_FRAC = 2                                    # LLR の小数bit数 (整数 LLR = LLR × 2^LLR_FRAC)

HALF_AXIS_POINTS = {"qpsk": 1, "qam16h": 2}


def bits_per_symbol(mod):
    return 2 * HALF_AXIS_POINTS[mod].bit_length()


def axis_points(mod, alpha):
    """1軸の信号点の値 (整数、Q FRAC) とラベル (符号ビット, 位置ビット...)。alpha は整数"""
    L = HALF_AXIS_POINTS[mod]
    a = alpha if L > 1 else 1
    nlp = L.bit_length() - 1
    pos = [a + 2 * i for i in range(L)]
    r = isqrt(((2 * sum(p * p for p in pos)) << (2 * FRAC)) // L)       # √(2 × 平均エネルギー) × 2^FRAC
    mags = [(p << (2 * FRAC)) // r for p in pos]
    vals, labels = [], []
    for hp in (0, 1):
        for idx in range(L):
            g = idx ^ (idx >> 1)
            vals.append((1 - 2 * hp) * mags[idx])
            labels.append([hp] + [(g >> (nlp - 1 - j)) & 1 for j in range(nlp)])
    g2i = [0] * L
    for i in range(L):
        g2i[i ^ (i >> 1)] = i
    return np.array(vals, np.int64), np.array(labels, np.int64), nlp, mags, g2i


PREAMBLE_BITS = np.array([1, 1, 1, -1, -1, 1, 1, -1, 1, -1, -1, -1, 1, 1, -1, 1], np.int64)
_P = (1 << FRAC) * 46341 >> 16                  # 1/√2 を Q FRAC で
PREAMBLE_I = PREAMBLE_BITS * _P
PREAMBLE_Q = np.roll(PREAMBLE_BITS, 5) * _P
N_PREAMBLE = len(PREAMBLE_BITS)


def modulate(bits, nsym, mod="qpsk", alpha=1):
    """ビット列 → (I, Q)。プリアンブル (N_PREAMBLE シンボル) を先頭に付ける"""
    _, _, nlp, mags, g2i = axis_points(mod, alpha)
    nslot = 2 * nsym
    buf = np.zeros(nslot * (1 + nlp), np.int64)
    buf[: len(bits)] = bits
    hp = buf[:nslot]
    code = np.zeros(nslot, np.int64)
    for j in range(nlp):
        code = (code << 1) | buf[nslot * (1 + j): nslot * (2 + j)]
    mag = np.array(mags, np.int64)[np.array(g2i, np.int64)[code]]
    v = np.where(hp == 1, -mag, mag)
    return np.concatenate([PREAMBLE_I, v[0::2]]), np.concatenate([PREAMBLE_Q, v[1::2]])


DIST_SHIFT = FRAC + 1 - DIST_BITS              # 距離 (Q FRAC、最大 約±2) を DIST_BITS bit に収める右シフト


def _sq(d):
    """距離 d (Q FRAC) の二乗。乗算器の幅に収めるため、d を右シフトして DIST_BITS bit にしてから二乗する"""
    r = np.clip(d >> DIST_SHIFT, -(1 << DIST_BITS), (1 << DIST_BITS) - 1)
    return r * r


def demodulate(i_sym, q_sym, n_bits, mod="qpsk", alpha=1):
    """
    プリアンブルを除いた (I, Q) → (LLR (整数、送信順)、硬判定ビット、軸あたりの雑音分散 (距離を DIST_SHIFT bit 縮めた単位の二乗))
    """
    vals, lab, nlp = axis_points(mod, alpha)[:3]
    i_sym, q_sym = np.asarray(i_sym, np.int64), np.asarray(q_sym, np.int64)
    y = np.stack([i_sym, q_sym], axis=1)                        # (n, 2)
    nsym = len(i_sym)
    near = vals[np.abs(y[..., None] - vals[None, None, :]).argmin(axis=-1)]
    res = y - near
    var = int(_sq(res).sum() // max(2 * nsym, 1))                # 軸あたりの雑音分散
    var = max(var, 1)
    dist = _sq(y[..., None] - vals[None, None, :])               # (n, 2, 2L)
    nslot = 2 * nsym
    llr = np.zeros(nslot * (1 + nlp), np.int64)
    hard = np.zeros(nslot * (1 + nlp), np.int64)
    best = np.argmin(dist, axis=-1)                              # (n, 2)
    for level in range(1 + nlp):
        bit1 = (lab[:, level] == 1)
        d1 = np.where(bit1[None, None, :], dist, np.iinfo(np.int64).max).min(axis=-1)
        d0 = np.where(~bit1[None, None, :], dist, np.iinfo(np.int64).max).min(axis=-1)
        v = np.clip(((d1 - d0) << LLR_FRAC) // (2 * var), -LLR_MAX, LLR_MAX)
        h = lab[best, level]
        llr[nslot * level: nslot * (level + 1)] = v.reshape(-1)
        hard[nslot * level: nslot * (level + 1)] = h.reshape(-1)
    return llr[:n_bits], hard[:n_bits], var
