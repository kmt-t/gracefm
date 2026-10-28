"""
整数だけで動くコーデック経路 (ブロック浮動小数点量子化 + Haar)。

DSP に依存する演算 (乗算器の幅、1/√2 の乗算、シフト、飽和) は gracefm.dsp にあり、このモジュールはそれだけを使う。
ハードウェアの仕様は docs/FIXED.md を参照。

PCM は符号つき24 bit整数 (±1 = 2^23)。係数は小数21 bit (±1 = 2^21) の整数で、M/S は M = (L+R)/2、S = (L-R)/2 を
最後の3 bit を四捨五入して作る。Haar の各段の出力は最大で 2^(段/2) 倍になり、4段の最低域で最大 ±2^23 に達する
(乗算器の入力 25 bit 符号つきの範囲に余裕がある) ので、飽和は起きない。共有指数 s = e + 21 は、最小の刻みを s >= 1 に
制限して、アッテネータの半刻みも整数にする (e < -20 の細かい刻みは使わない。デコーダは s <= 0 でも右シフトで復号する)。
BlockData は gracefm.codec と同じなので、フレーム化 (framing)・変調以降はそのまま使える。
"""
import numpy as np

from .codec import BlockData, exp_range, qmax_of, qmin_of
from .dsp import ERR_FRAC_BITS, bit_length, mac_sq2_inv, round_shift, saturate, saturate_bits, shift_signed, sq_err_sum
from .profiles import Profile

FRAC = 21                       # 係数の小数bit数 (±1 = 2^21)
PCM_BITS = 24                   # PCM の幅 (符号つき)


def haar_forward_int(x, levels):
    a = saturate(np.asarray(x, np.int64))
    details = []
    for _ in range(levels):
        e, o = a[..., 0::2], a[..., 1::2]
        details.append(mac_sq2_inv(e, o, -1))
        a = mac_sq2_inv(e, o, 1)
    return [a] + details[::-1]


def haar_inverse_int(bands):
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


def quantize_int(c, k, b, profile: Profile, clip_opt=True, ch="M"):
    """整数係数 c (..., ncoef) → (仮数 m, 指数インデックス, アッテネータ)。アッテネータの定義は codec.quantize_attenuated と同じ"""
    c = np.asarray(c, np.int64)
    group = profile.attenuator_group(ch, k)
    qmax, qmin = qmax_of(b), qmin_of(b, profile, ch, k)
    emin, emax = exp_range(k, b, profile, ch)
    peak = np.abs(c).max(axis=-1)
    e_floor = max(emin, 1 - FRAC)                       # 刻みの最小は s = 1
    e0 = _shared_exponent(peak, qmax, e_floor, emax)
    cg = c.reshape(c.shape[:-1] + (-1, group)) if group else c[..., None, :]

    err_shift = np.maximum(e0 + FRAC - ERR_FRAC_BITS, 0)[..., None, None]     # 候補どうしで同じ尺度の誤差を比べる

    def candidate(e):
        s = (e + FRAC)[..., None, None]
        m0 = np.clip(round_shift(cg, s), qmin, qmax)
        err0 = sq_err_sum(cg - (m0 << s), err_shift)
        if not group:
            return m0.reshape(c.shape), np.zeros(c.shape[:-1] + (0,), np.int64), err0.sum(axis=-1)
        m1 = np.clip(round_shift(cg, s - 1), qmin, qmax)
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


def dequantize_int(m, eidx, k, b, profile: Profile, ch="M", attn=None):
    emin, _ = exp_range(k, b, profile, ch)
    s = int(eidx) + emin + FRAC
    if attn is None or not len(attn):
        return saturate(shift_signed(m, s))
    group = profile.attenuator_group(ch, k)
    shift = s - np.repeat(np.asarray(attn, np.int64), group, axis=-1)
    return saturate(shift_signed(m, shift))


def encode_block_int(x, profile: Profile, clip_opt=True) -> BlockData:
    """x: (block, 2) の L/R、符号つき24 bit整数 (|x| < 2^23)"""
    x = np.asarray(x, np.int64)
    ms = {"M": (x[:, 0] + x[:, 1] + 4) >> 3, "S": (x[:, 0] - x[:, 1] + 4) >> 3}      # 24 bit PCM → 21 bit小数 (M=(L+R)/2)
    mant, eidx, attn = {}, {}, {}
    for ch, bits in (("M", profile.bits_m), ("S", profile.bits_s)):
        bands = haar_forward_int(ms[ch], profile.levels)
        mant[ch], eidx[ch], attn[ch] = [], [], []
        for k, (c, b) in enumerate(zip(bands, bits)):
            if b == 0:
                mant[ch].append(None)
                eidx[ch].append(None)
                attn[ch].append(None)
                continue
            m, e, a = quantize_int(c, k, b, profile, clip_opt, ch)
            mant[ch].append(m)
            eidx[ch].append(int(e))
            attn[ch].append(a)
    return BlockData(mant, eidx, attn)


def decode_block_int(bd: BlockData, profile: Profile):
    """BlockData → (block, 2) の L/R、符号つき24 bit整数 (四捨五入)"""
    out = {}
    for ch, bits in (("M", profile.bits_m), ("S", profile.bits_s)):
        bands = []
        for k, b in enumerate(bits):
            if b == 0:
                bands.append(np.zeros(profile.ncoef(k), np.int64))
            else:
                bands.append(dequantize_int(bd.mant[ch][k], bd.eidx[ch][k], k, b, profile, ch, bd.attn[ch][k]))
        out[ch] = haar_inverse_int(bands)
    return saturate_bits(np.stack([(out["M"] + out["S"]) << 2, (out["M"] - out["S"]) << 2], axis=-1), PCM_BITS)


def roundtrip_int(x, profile: Profile):
    """通信路なしの符号化と復号 (ブロックごと)。x は (n, 2) の符号つき24 bit整数"""
    n = profile.block
    nfr = -(-len(x) // n)
    xp = np.pad(np.asarray(x, np.int64), ((0, nfr * n - len(x)), (0, 0)))
    out = np.zeros_like(xp)
    for i in range(nfr):
        out[i * n:(i + 1) * n] = decode_block_int(encode_block_int(xp[i * n:(i + 1) * n], profile), profile)
    return out[:len(x)]
