"""
音声符号化: M/S → 多段の帯域分割 → 帯域ごとのブロック浮動小数点量子化。すべて整数演算。
帯域分割はプロファイルで決まる。Haar はブロック内で完結し、LeGall 5/3 はブロックをまたぐ (analyze_stream、synthesize_stream)。

PCM は符号つき24 bit整数 (±1 = 2^23)。係数は小数22 bit (±1 = 2^22) の整数で、M/S は M = (L+R)/2、S = (L-R)/2 を
最後の2 bit を四捨五入して作る。Haar の各段の出力は最大で 2^(段/2) 倍になり、4段の最低域は満点の直流で ±2^24 に達して、
乗算器の入力 25 bit 符号つきの上限 2^24 - 1 を 1 だけ超える。この 1 LSB (2^-22) は飽和で切る (saturate)。共有指数 s = e + 22 は、最小の刻みを s >= 1 に
制限して、アッテネータの半刻みも整数にする (e < -21 の細かい刻みは使わない。デコーダは s <= 0 でも右シフトで復号する)。
DSP に依存する演算は gracefm.dsp にある (docs/FIXED.md)。

Haar のプロファイルでは、すべての処理はブロック (= フレーム) の中で完結し、先読みはない。
配列の最後の軸がブロック内のサンプル (または係数) で、それより前の軸はブロックの並び
(ツールで一括処理するため) として扱う。
"""
import numpy as np

from .dsp import (
    ERR_FRAC_BITS,
    bit_length,
    mac_sq2_inv,
    round_shift,
    saturate,
    saturate_bits,
    sq_err_sum,
)
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


def _next(x):
    """同じ格子の 1つ先の値。端は折り返す (対称拡張)"""
    return np.concatenate([x[..., 1:], x[..., -1:]], axis=-1)


def _prev(x):
    """同じ格子の 1つ前の値。端は折り返す (対称拡張)"""
    return np.concatenate([x[..., :1], x[..., :-1]], axis=-1)


def legall_forward(x, levels):
    """LeGall 5/3 の多段分解。x はストリーム全体 (最後の軸が時間)。リフティングは加算とシフトだけで、
    スケーリング (低域 ×√2、高域 ÷√2) を Haar と同じ乗算で行い、帯域の尺度を Haar にそろえる。"""
    a = saturate(np.asarray(x, np.int64))
    details = []
    for _ in range(levels):
        e, o = a[..., 0::2], a[..., 1::2]
        d = saturate(o - ((e + _next(e)) >> 1))
        low = saturate(e + ((_prev(d) + d + 2) >> 2))
        details.append(mac_sq2_inv(d, 0, 1))
        a = mac_sq2_inv(low, low, 1)
    return [a] + details[::-1]


def legall_inverse(bands):
    """legall_forward の逆変換"""
    a = bands[0]
    for scaled in bands[1:]:
        low = mac_sq2_inv(a, 0, 1)
        d = mac_sq2_inv(scaled, scaled, 1)
        e = saturate(low - ((_prev(d) + d + 2) >> 2))
        x = np.empty(a.shape[:-1] + (a.shape[-1] * 2,), np.int64)
        x[..., 0::2] = e
        x[..., 1::2] = saturate(d + ((e + _next(e)) >> 1))
        a = x
    return a


def _shared_exponent(peak, qmax, emin, emax):
    """peak <= qmax * 2^s を満たす最小の s から指数 e = s - FRAC を決め、[emin, emax] に収める"""
    ratio = (peak + qmax - 1) // qmax                   # ceil(peak / qmax)
    s = bit_length(np.maximum(ratio, 1) - 1)
    return np.clip(s - FRAC, emin, emax)


def quantize_band(c, ch, k, profile: Profile, clip_opt=True):
    """整数係数 c (..., ncoef) → (仮数 m, 指数インデックス, アッテネータ)。アッテネータの定義は gracefm.profiles の attenuator_group で決まる"""
    c = np.asarray(c, np.int64)
    b = (profile.bits_m if ch == "M" else profile.bits_s)[k]
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


def analyze(x, profile: Profile):
    """x: (block, 2) の L/R、符号つき24 bit整数 (|x| < 2^23) → {ch: [帯域の係数 (整数、小数22 bit)]}。M/S 分離と Haar 多段分解"""
    x = np.asarray(x, np.int64)
    ms = {"M": (x[:, 0] + x[:, 1] + 2) >> 2, "S": (x[:, 0] - x[:, 1] + 2) >> 2}      # 24 bit PCM → 22 bit小数 (M=(L+R)/2)
    return {ch: haar_forward(ms[ch], profile.levels) for ch in ("M", "S")}


def quantize(bands, profile: Profile, clip_opt=True) -> BlockData:
    """analyze の出力 → BlockData (帯域ごとの仮数・指数・アッテネータ)。b = 0 の帯域は None"""
    mant, eidx, attn = {}, {}, {}
    for ch, bits in (("M", profile.bits_m), ("S", profile.bits_s)):
        mant[ch], eidx[ch], attn[ch] = [], [], []
        for k, (c, b) in enumerate(zip(bands[ch], bits)):
            if b == 0:
                mant[ch].append(None)
                eidx[ch].append(None)
                attn[ch].append(None)
                continue
            m, e, a = quantize_band(c, ch, k, profile, clip_opt)
            mant[ch].append(m)
            eidx[ch].append(int(e))
            attn[ch].append(a)
    return BlockData(mant, eidx, attn)


def encode_block(x, profile: Profile, clip_opt=True) -> BlockData:
    """x: (block, 2) の L/R、符号つき24 bit整数 (|x| < 2^23)。analyze → quantize。ブロック内で完結する帯域分割だけ"""
    _require_block_transform(profile)
    return quantize(analyze(x, profile), profile, clip_opt)


def _require_block_transform(profile: Profile):
    if profile.overlapped:
        raise ValueError(f"{profile.name} の帯域分割はブロックをまたぐので、ストリーム単位で処理してください")


def analyze_stream(x, profile: Profile):
    """x: (block × フレーム数, 2) の L/R → フレームごとの {ch: [帯域の係数]}。ブロックをまたぐ帯域分割を使う。
    フレーム j の係数はブロック終端の encoder_lookahead サンプル先までに依存する (実機は、その分を待ってから符号化する)。"""
    x = np.asarray(x, np.int64)
    ms = {"M": (x[:, 0] + x[:, 1] + 2) >> 2, "S": (x[:, 0] - x[:, 1] + 2) >> 2}
    full = {ch: legall_forward(ms[ch], profile.levels) for ch in ms}
    nfr = len(x) // profile.block
    counts = [profile.ncoef(k) for k in range(profile.nbands)]
    return [{ch: [b[j * c:(j + 1) * c] for b, c in zip(full[ch], counts)] for ch in full} for j in range(nfr)]


def overlap_valid(frame_valid, profile: Profile, n):
    """届かなかったフレームの係数は前後のブロックにも影響するので、影響する範囲のサンプルを無効にする。
    frame_valid: フレームごとの有効フラグ。返り値: n サンプルの有効フラグ (フレームの後ろは無効)"""
    before = profile.synth_reach_before
    bad = np.repeat(~np.asarray(frame_valid, bool), profile.block).astype(np.int64)
    touched = np.convolve(bad, np.ones(before + profile.synth_reach_after + 1, np.int64))[before:before + len(bad)]
    return np.pad(touched == 0, (0, max(n - len(bad), 0)))[:n]


def synthesize_stream(frames):
    """フレームごとの {ch: [帯域係数]} → (block × フレーム数, 2) の L/R、符号つき24 bit整数。analyze_stream の逆"""
    joined = {ch: [np.concatenate(band) for band in zip(*(f[ch] for f in frames))] for ch in ("M", "S")}
    return ms_to_lr(legall_inverse(joined["M"]), legall_inverse(joined["S"]))


def synthesize(coefs):
    """{ch: [帯域係数]} → (block, 2) の L/R、符号つき24 bit整数。Haar の逆変換と M/S の逆変換 (analyze の逆)"""
    return ms_to_lr(haar_inverse(coefs["M"]), haar_inverse(coefs["S"]))


def ms_to_lr(M, S):
    """M/S (小数22 bit) → L/R (符号つき24 bit PCM)。L = M + S、R = M - S"""
    return saturate_bits(np.stack([(M + S) << 1, (M - S) << 1], axis=-1), PCM_BITS)
