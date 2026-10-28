"""
変調と復調 (QPSK、階層16QAM、Y方式)。すべて整数演算。シンボルは (I, Q) の整数の組で、配列の形は (n, 2)。
信号点は小数 FRAC bit の固定小数点 (±1 = 2^FRAC)、平均シンボルエネルギーは 1。

変調: ビット列 → (n, 2)。ビット列の並びは「全シンボルの強い位置 (符号) → 全シンボルの弱い位置 (位置の Gray 符号)」の順。
  フレーム先頭に既知のプリアンブル (QPSK 16シンボル) を付ける。プリアンブル以外のビット (端数の詰め物を含む) は、
  フレームごとに先頭から始める PRBS と排他的論理和をとって送る (スクランブル。送信スペクトルに線スペクトルが立たないように)。
復調: 軸ごとに独立な max-log の LLR (正 = 0 らしい) を整数で作る。LLR(bit) = (D1 - D0) / (2 σ²)。D は、そのビットが
  1 / 0 の信号点のうち受信点に最も近いものとの距離の二乗 (乗算器の幅 18 bit に収めるため、距離は右シフトして二乗する)。
  σ² (軸あたりの雑音分散) は、フレームごとに、受信点と最寄りの信号点との差から求める。
Y方式 (QASK): 1係数 = 1シンボル。位相の2 bit は (仮数の最上位 bit, そのパリティ)、半径が残りの仮数 (lower_bits)。
  象限は (パリティ → I軸の符号、最上位bit → Q軸の符号) に割り当てる。半径は、段 L に応じて (1 + a·(L - 中心)) / 規格化 で、
  a は隣接する半径の段の間隔 (分数 num/den)。
DSP に依存する幅は gracefm.dsp にある。
"""
from math import isqrt

import numpy as np

from .dsp import CONST_BITS

FRAC = 21
DIST_BITS = CONST_BITS - 1                      # 二乗する距離の幅 (符号を除く)
DIST_SHIFT = FRAC + 1 - DIST_BITS               # 距離 (Q FRAC、最大 約±2) を DIST_BITS bit に収める右シフト
LLR_BITS = 8
LLR_MAX = (1 << (LLR_BITS - 1)) - 1
LLR_FRAC = 2                                    # LLR の小数bit数 (整数 LLR = LLR × 2^LLR_FRAC)

HALF_AXIS_POINTS = {"qpsk": 1, "qam16h": 2}

_PRBS_CACHE = np.zeros(0, np.int64)


def prbs(n):
    """スクランブル系列: 1 + x^14 + x^15 (DVB と同じ)、初期値 100101010000000。フレームごとに先頭から使う"""
    global _PRBS_CACHE
    if len(_PRBS_CACHE) < n:
        reg = [1, 0, 0, 1, 0, 1, 0, 1, 0, 0, 0, 0, 0, 0, 0]
        out = np.empty(max(n, 4096), np.int64)
        for i in range(len(out)):
            b = reg[13] ^ reg[14]
            out[i] = b
            reg = [b] + reg[:14]
        _PRBS_CACHE = out
    return _PRBS_CACHE[:n]


def bits_per_symbol(mod):
    return 2 * HALF_AXIS_POINTS[mod].bit_length()


def n_symbols(n_tx, n_coded, mod):
    bps = bits_per_symbol(mod)
    return max(-(-n_tx // bps), -(-n_coded // 2))


INV_SQRT2 = isqrt(1 << (2 * FRAC - 1))          # 1/√2 を Q FRAC で

PREAMBLE_BITS = np.array([1, 1, 1, -1, -1, 1, 1, -1, 1, -1, -1, -1, 1, 1, -1, 1], np.int64)
PREAMBLE = np.stack([PREAMBLE_BITS * INV_SQRT2, np.roll(PREAMBLE_BITS, 5) * INV_SQRT2], axis=1)    # (16, 2)
N_PREAMBLE = len(PREAMBLE)


def axis_points(mod, alpha):
    """1軸の信号点の値 (整数、Q FRAC)、ラベル (符号ビット, 位置ビット...)、位置ビット数、大きさの表、Gray→位置の表。alpha は整数"""
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


def modulate(bits, nsym, mod="qpsk", alpha=1):
    """ビット列 → (n, 2) の整数。プリアンブル (N_PREAMBLE シンボル) を先頭に付ける"""
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
    return np.concatenate([PREAMBLE, np.stack([v[0::2], v[1::2]], axis=1)])


def _sq(d):
    """距離 d (Q FRAC) の二乗。乗算器の幅に収めるため、d を右シフトして DIST_BITS bit にしてから二乗する"""
    r = np.clip(d >> DIST_SHIFT, -(1 << DIST_BITS), (1 << DIST_BITS) - 1)
    return r * r


def demodulate(sym, n_bits, mod="qpsk", alpha=1):
    """
    プリアンブルを除いた (n, 2) の受信シンボル → (LLR (整数、送信順)、硬判定ビット、軸あたりの雑音分散)
    分散の単位は、距離を DIST_SHIFT bit 縮めた単位の二乗。
    """
    vals, lab, nlp = axis_points(mod, alpha)[:3]
    y = np.asarray(sym, np.int64)                                # (n, 2)
    nsym = len(y)
    near = vals[np.abs(y[..., None] - vals[None, None, :]).argmin(axis=-1)]
    var = max(int(_sq(y - near).sum() // max(2 * nsym, 1)), 1)
    dist = _sq(y[..., None] - vals[None, None, :])               # (n, 2, 2L)
    nslot = 2 * nsym
    llr = np.zeros(nslot * (1 + nlp), np.int64)
    hard = np.zeros(nslot * (1 + nlp), np.int64)
    best = np.argmin(dist, axis=-1)                              # (n, 2)
    big = np.iinfo(np.int64).max
    for level in range(1 + nlp):
        bit1 = (lab[:, level] == 1)
        d1 = np.where(bit1[None, None, :], dist, big).min(axis=-1)
        d0 = np.where(~bit1[None, None, :], dist, big).min(axis=-1)
        llr[nslot * level: nslot * (level + 1)] = np.clip(((d1 - d0) << LLR_FRAC) // (2 * var), -LLR_MAX, LLR_MAX).reshape(-1)
        hard[nslot * level: nslot * (level + 1)] = lab[best, level].reshape(-1)
    return llr[:n_bits], hard[:n_bits], var


# ---------------------------------------------------------------- Y方式 (QASK)
_QUADRANT = np.array([0, 1, 3, 2])          # 2*最上位bit + パリティ → 象限番号 (0: ++, 1: -+, 2: --, 3: +-)
_QUADRANT_BITS = np.argsort(_QUADRANT)      # 象限番号 → 2*最上位bit + パリティ
_QUADRANT_SIGN = np.array([[1, 1], [-1, 1], [-1, -1], [1, -1]], np.int64)       # 象限番号 → (I, Q) の符号


def y_radii(step, lower_bits=6):
    """半径の段 L = 0 … 2^lower_bits - 1 の半径 (Q FRAC)。step = (分子, 分母)"""
    num, den = step
    levels = 1 << lower_bits
    scale = isqrt((((12 * den * den + num * num * (levels * levels - 1)) << (2 * FRAC)) // (12 * den * den)))
    ls = np.arange(levels, dtype=np.int64)
    top = 2 * den + num * (2 * ls - (levels - 1))
    return (top << (2 * FRAC)) // (2 * den * scale), scale


def y_modulate(u, parity, step=(2, 105), scramble=None, lower_bits=6):
    """u = 最上位bit·2^lower_bits + 半径の段 (0〜2^(lower_bits+1)-1)、parity = 最上位bitのパリティ (0/1) → (n, 2)"""
    u = np.asarray(u, np.int64)
    parity = np.asarray(parity, np.int64)
    levels = 1 << lower_bits
    if np.any((u < 0) | (u >= 2 * levels)) or np.any((parity < 0) | (parity > 1)):
        raise ValueError("Y仮数またはパリティが範囲外です")
    msb, L = u // levels, u % levels
    if scramble is not None:
        mask = np.asarray(scramble, np.int64).reshape(-1, 3)
        if len(mask) != len(u):
            raise ValueError("スクランブル長が係数数と一致しません")
        msb = msb ^ mask[:, 0]
        parity = parity ^ mask[:, 1]
        L = np.where(mask[:, 2] != 0, levels - 1 - L, L)
    radius = y_radii(step, lower_bits)[0][L]
    sign = _QUADRANT_SIGN[_QUADRANT[2 * msb + parity]]
    return np.stack([sign[:, 0] * radius, sign[:, 1] * radius], axis=1) * INV_SQRT2 >> FRAC


def _magnitude(y):
    """|z| (Q FRAC)。距離を DIST_SHIFT bit 縮めて二乗和の整数平方根を取る (ハードウェアでは CORDIC など)"""
    r = y >> DIST_SHIFT
    return isqrt_array((r * r).sum(axis=-1)) << DIST_SHIFT


def isqrt_array(v):
    return np.array([isqrt(int(x)) for x in np.asarray(v).reshape(-1)], np.int64).reshape(np.shape(v))


def y_slice(values, step=(2, 105), lower_bits=6):
    """受信点を最も近いY方式の信号点 (象限・半径の段) に判定する → (象限番号, 半径の段)。スクランブルの影響を受けない"""
    y = np.asarray(values, np.int64)
    quadrant = np.where(y[:, 0] >= 0, np.where(y[:, 1] >= 0, 0, 3), np.where(y[:, 1] >= 0, 1, 2))
    radii = y_radii(step, lower_bits)[0]
    mag = _magnitude(y)
    level = np.abs(mag[:, None] - radii[None, :]).argmin(axis=1)
    return quadrant, level


def y_points(quadrant, level, step=(2, 105), lower_bits=6):
    """象限番号と半径の段 → 信号点 (n, 2) (Q FRAC)"""
    radius = y_radii(step, lower_bits)[0][np.asarray(level, np.int64)]
    sign = _QUADRANT_SIGN[np.asarray(quadrant, np.int64)]
    return (sign * radius[:, None] * INV_SQRT2) >> FRAC


def y_phase_llr(sym, step=(2, 105), scramble=None, var=1, lower_bits=6):
    """
    専用シンボルの位相だけから、最上位bitとパリティの LLR (整数、正 = 0 らしい) を返す。
    象限は (パリティ → I軸の符号、最上位bit → Q軸の符号) なので、2 つの bit は独立で、LLR = 2 · 軸の値 · (半径/√2) / σ²。
    半径は受信点の大きさを、取りうる範囲に制限した値。var は軸あたりの雑音分散 (demodulate と同じ単位)。
    """
    y = np.asarray(sym, np.int64)
    mask = np.zeros((len(y), 3), np.int64) if scramble is None else np.asarray(scramble, np.int64).reshape(-1, 3)
    if len(mask) != len(y):
        raise ValueError("スクランブル長が係数数と一致しません")
    radii = y_radii(step, lower_bits)[0]
    r = np.clip(_magnitude(y), radii[0], radii[-1])
    unit = (r * INV_SQRT2) >> FRAC                                  # 1軸の大きさ (Q FRAC)
    llr_par = np.clip(((((y[:, 0] >> DIST_SHIFT) * (unit >> DIST_SHIFT)) << (LLR_FRAC + 1)) // max(var, 1)), -LLR_MAX, LLR_MAX)
    llr_msb = np.clip(((((y[:, 1] >> DIST_SHIFT) * (unit >> DIST_SHIFT)) << (LLR_FRAC + 1)) // max(var, 1)), -LLR_MAX, LLR_MAX)
    # 送信側で msb・parity をスクランブルのマスクで反転しているので、LLR の符号も戻す
    llr_msb = np.where(mask[:, 0] == 1, -llr_msb, llr_msb)
    llr_par = np.where(mask[:, 1] == 1, -llr_par, llr_par)
    return llr_msb, llr_par


MANT_FRAC = 1                                                           # Y の半径の推定値の小数bit数 (段 6 bit + 小数 1 bit = 7 bit)


def y_demodulate(sym, msb, parity, step=(2, 105), scramble=None, var=1, lower_bits=6, phase_only=False):
    """
    最上位bitとパリティ (ヘッダ部のFECで確定した値) で象限を決め、半径の段の推定値を返す。
    返り値: (u = 最上位bit·2^lower_bits + 半径の段の推定値 (小数 MANT_FRAC bit の整数), 半径の段の誤差分散 (同じ小数bit数の二乗))
    段の推定値は、受信から求めた観測値を、取りうる段の一様な事前分布へ向けて縮める (ウィナー型): 利得 = 事前分散 / (事前分散 + 雑音)。
    """
    y = np.asarray(sym, np.int64)
    msb = np.asarray(msb, np.int64)
    parity = np.asarray(parity, np.int64)
    if len(y) != len(msb) or len(y) != len(parity):
        raise ValueError("Y帯域のシンボル数が一致しません")
    mask = np.zeros((len(y), 3), np.int64) if scramble is None else np.asarray(scramble, np.int64).reshape(-1, 3)
    levels = 1 << lower_bits
    radii, scale = y_radii(step, lower_bits)
    quadrant = _QUADRANT[2 * (msb ^ mask[:, 0]) + (parity ^ mask[:, 1])]
    sign = _QUADRANT_SIGN[quadrant]
    proj = ((sign[:, 0] * y[:, 0] + sign[:, 1] * y[:, 1]) * INV_SQRT2) >> FRAC          # 象限の軸への射影 (Q FRAC)
    num, den = step
    # 観測された段 = (proj × scale − 1) / a + 中心。a = num/den、中心 = (levels − 1)/2。小数 MANT_FRAC bit
    scaled = (proj * scale) >> FRAC                                                     # proj × scale (Q FRAC)
    obs = ((((scaled - (1 << FRAC)) * den) << MANT_FRAC) + ((num << FRAC) >> 1)) // (num << FRAC) + (((levels - 1) << MANT_FRAC) >> 1)
    obs = np.where(mask[:, 2] != 0, ((levels - 1) << MANT_FRAC) - obs, obs)
    center = ((levels - 1) << MANT_FRAC) >> 1
    # 雑音の段あたりの分散 = σ² × scale² / a² (σ² は demodulate と同じ単位 → Q FRAC の二乗へ戻す)
    sigma2 = (max(var, 1) << (2 * DIST_SHIFT))                                          # (Q FRAC)² 単位
    noise = ((sigma2 >> FRAC) * ((scale * scale) >> FRAC) >> FRAC) * den * den // (num * num)
    noise_l = (noise << (2 * MANT_FRAC)) >> FRAC                                       # 段² を小数 MANT_FRAC 桁の二乗で
    prior = ((levels * levels - 1) << (2 * MANT_FRAC)) // 12
    gain = 0 if phase_only else (prior << 15) // (prior + noise_l + 1)                 # Q15
    est = np.clip(center + ((gain * (obs - center) + (1 << 14)) >> 15), 0, (levels - 1) << MANT_FRAC)
    variance = (gain * noise_l) >> 15
    return (msb * levels << MANT_FRAC) + est, np.full(len(y), variance, np.int64)
