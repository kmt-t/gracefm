"""
音声符号化: M/S → ブロック内 Haar 多段分解 → 帯域ごとのブロック浮動小数点量子化。すべて整数演算。

PCM は符号つき24 bit整数 (±1 = 2^23)。係数は小数22 bit (±1 = 2^22) の整数で、M/S は M = (L+R)/2、S = (L-R)/2 を
最後の2 bit を四捨五入して作る。Haar の各段の出力は最大で 2^(段/2) 倍になり、4段の最低域は満点の直流で ±2^24 に達して、
乗算器の入力 25 bit 符号つきの上限 2^24 - 1 を 1 だけ超える。この 1 LSB (2^-22) は飽和で切る (saturate)。共有指数 s = e + 22 は、最小の刻みを s >= 1 に
制限して、アッテネータの半刻みも整数にする (e < -21 の細かい刻みは使わない。デコーダは s <= 0 でも右シフトで復号する)。
DSP に依存する演算は gracefm.dsp にある (docs/FIXED.md)。

すべての処理はブロック (= フレーム) の中で完結し、先読みはない。
配列の最後の軸がブロック内のサンプル (または係数) で、それより前の軸はブロックの並び
(ツールで一括処理するため) として扱う。
"""
import numpy as np

from .dsp import bit_length, mac_sq2_inv, round_shift, saturate, saturate_bits, shift_signed, sq_err_sum, ERR_FRAC_BITS
from .profiles import Profile, band_level


def qmax_of(b):
    return 2 ** (b - 1) - 1


def qmin_of(b, profile: Profile, ch: str, k: int):
    """Y帯域だけ負側に1値多い2の補数範囲を使い、全2^b点を利用する。"""
    return -(1 << (b - 1)) if profile.y_band(ch, k) else -qmax_of(b)


def offset_of(b, profile: Profile, ch: str, k: int):
    return -qmin_of(b, profile, ch, k)


def exp_range(k, b, profile: Profile):
    """帯域 k・仮数幅 b・プロファイルで固定する指数範囲 [emin, emax]。

    emax は、その帯域で取りうる最大振幅 2^(lev/2) (入力 |x| <= 1) を、最大の仮数 qmax で表せる最小の指数
    ceil(log2(2^(lev/2) × 2 / qmax)) で、整数だけで (lev // 2) + 3 - b と書ける。
    送受信で同じ値を計算する。フレームにはオフセット emin を送らず、eidx = e - emin だけを格納する。
    """
    lev = band_level(k, profile.levels)
    emax = (lev >> 1) + 3 - b
    emin = emax - (2 ** profile.exp_bits - 1)
    return emin, emax


class BlockData:
    """1ブロックぶんの量子化結果。mant[ch][k], eidx[ch][k] (0bit の帯域は None)"""

    def __init__(self, mant, eidx, attn=None):
        self.mant = mant
        self.eidx = eidx
        self.attn = attn if attn is not None else {ch: [None] * len(eidx[ch]) for ch in ("M", "S")}


def attenuator_expanded(attn, group, n):
    """係数ごとの 0/1 減衰量。区間長0の帯域は全係数 0。"""
    if not group:
        return np.zeros(n, np.int64)
    return np.repeat(np.asarray(attn, np.int64), group, axis=-1)


FRAC = 22                       # 係数の小数bit数 (±1 = 2^22)
PCM_BITS = 24                   # PCM の幅 (符号つき)


def haar_forward(x, levels):
    a = saturate(np.asarray(x, np.int64))
    details = []
    for _ in range(levels):
        e, o = a[..., 0::2], a[..., 1::2]
        details.append(mac_sq2_inv(e, o, -1))
        a = mac_sq2_inv(e, o, 1)
    return [a] + details[::-1]


def haar_inverse(bands):
    a = bands[0]
    for d in bands[1:]:
        x = np.empty(a.shape[:-1] + (a.shape[-1] * 2,), np.int64)
        x[..., 0::2] = mac_sq2_inv(a, d, 1)
        x[..., 1::2] = mac_sq2_inv(a, d, -1)
        a = x
    return a


def _shared_exponent(peak, qmax, emin, emax):
    """peak <= qmax * 2^s を満たす最小の s から指数 e = s - FRAC を決め、[emin, emax] に収める"""
    ratio = (peak + qmax - 1) // qmax                   # ceil(peak / qmax)
    s = bit_length(np.maximum(ratio, 1) - 1)
    return np.clip(s - FRAC, emin, emax)


def quantize(c, k, b, profile: Profile, clip_opt=True, ch="M"):
    """整数係数 c (..., ncoef) → (仮数 m, 指数インデックス, アッテネータ)。アッテネータの定義は gracefm.profiles の attenuator_group で決まる"""
    c = np.asarray(c, np.int64)
    group = profile.attenuator_group(ch, k)
    qmax, qmin = qmax_of(b), qmin_of(b, profile, ch, k)
    emin, emax = exp_range(k, b, profile)
    peak = np.abs(c).max(axis=-1)
    e_floor = max(emin, 1 - FRAC)                       # 刻みの最小は s = 1
    e0 = _shared_exponent(peak, qmax, e_floor, emax)
    cg = c.reshape(c.shape[:-1] + (-1, group)) if group else c[..., None, :]

    err_shift = np.maximum(e0 + FRAC - ERR_FRAC_BITS, 0)[..., None, None]     # 候補どうしで同じ尺度の誤差を比べる

    def candidate(e):
        s = (e + FRAC)[..., None, None]
        m0 = np.minimum(np.maximum(round_shift(cg, s), qmin), qmax)
        err0 = sq_err_sum(cg - (m0 << s), err_shift)
        if not group:
            return m0.reshape(c.shape), np.zeros(c.shape[:-1] + (0,), np.int64), err0.sum(axis=-1)
        m1 = np.minimum(np.maximum(round_shift(cg, s - 1), qmin), qmax)
        err1 = sq_err_sum(cg - (m1 << (s - 1)), err_shift)
        attn = (err1 < err0).astype(np.int64)
        chosen = np.where(attn[..., None], m1, m0)
        return chosen.reshape(c.shape), attn, np.minimum(err0, err1).sum(axis=-1)

    m, a, err = candidate(e0)
    if clip_opt:
        e1 = np.maximum(e0 - 1, e_floor)
        m1, a1, err1 = candidate(e1)
        better = err1 < err
        e0 = np.where(better, e1, e0)
        m = np.where(better[..., None], m1, m)
        a = np.where(better[..., None], a1, a)
    return m.astype(np.int64), (e0 - emin).astype(np.int64), a


def dequantize(m, eidx, k, b, profile: Profile, ch="M", attn=None):
    emin, _ = exp_range(k, b, profile)
    s = int(eidx) + emin + FRAC
    if attn is None or not len(attn):
        return saturate(shift_signed(m, s))
    group = profile.attenuator_group(ch, k)
    shift = s - np.repeat(np.asarray(attn, np.int64), group, axis=-1)
    return saturate(shift_signed(m, shift))


def encode_block(x, profile: Profile, clip_opt=True) -> BlockData:
    """x: (block, 2) の L/R、符号つき24 bit整数 (|x| < 2^23)"""
    x = np.asarray(x, np.int64)
    ms = {"M": (x[:, 0] + x[:, 1] + 2) >> 2, "S": (x[:, 0] - x[:, 1] + 2) >> 2}      # 24 bit PCM → 22 bit小数 (M=(L+R)/2)
    mant, eidx, attn = {}, {}, {}
    for ch, bits in (("M", profile.bits_m), ("S", profile.bits_s)):
        bands = haar_forward(ms[ch], profile.levels)
        mant[ch], eidx[ch], attn[ch] = [], [], []
        for k, (c, b) in enumerate(zip(bands, bits)):
            if b == 0:
                mant[ch].append(None)
                eidx[ch].append(None)
                attn[ch].append(None)
                continue
            m, e, a = quantize(c, k, b, profile, clip_opt, ch)
            mant[ch].append(m)
            eidx[ch].append(int(e))
            attn[ch].append(a)
    return BlockData(mant, eidx, attn)


def decode_block(bd: BlockData, profile: Profile):
    """BlockData → (block, 2) の L/R、符号つき24 bit整数"""
    coefs = decode_coeffs(bd, profile)
    return ms_to_lr(haar_inverse(coefs["M"]), haar_inverse(coefs["S"]))


def roundtrip(x, profile: Profile):
    """通信路なしの符号化と復号 (ブロックごと)。x は (n, 2) の符号つき24 bit整数"""
    n = profile.block
    nfr = -(-len(x) // n)
    xp = np.pad(np.asarray(x, np.int64), ((0, nfr * n - len(x)), (0, 0)))
    out = np.zeros_like(xp)
    for i in range(nfr):
        out[i * n:(i + 1) * n] = decode_block(encode_block(xp[i * n:(i + 1) * n], profile), profile)
    return out[:len(x)]


def decode_coeffs(bd: BlockData, profile: Profile):
    """BlockData → {ch: [帯域係数 (整数、小数22 bit)]}"""
    coefs = {}
    for ch, bits in (("M", profile.bits_m), ("S", profile.bits_s)):
        coefs[ch] = []
        for k, b in enumerate(bits):
            if b == 0:
                coefs[ch].append(np.zeros(profile.ncoef(k), np.int64))
            else:
                coefs[ch].append(dequantize(bd.mant[ch][k], bd.eidx[ch][k], k, b, profile, ch, bd.attn[ch][k]))
    return coefs


def ms_to_lr(M, S):
    """M/S (小数22 bit) → L/R (符号つき24 bit PCM)。L = M + S、R = M - S"""
    return saturate_bits(np.stack([(M + S) << 1, (M - S) << 1], axis=-1), PCM_BITS)
