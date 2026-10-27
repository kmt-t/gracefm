"""
音声符号化: M/S → ブロック内 Haar 多段分解 → 帯域ごとのブロック浮動小数点量子化。

すべての処理はブロック (= フレーム) の中で完結し、先読みはない。
配列の最後の軸がブロック内のサンプル (または係数) で、それより前の軸はブロックの並び
(ツールで一括処理するため) として扱う。
"""
import numpy as np

from .profiles import Profile, band_level

SQ2 = np.sqrt(2.0)


# ---------------------------------------------------------------- Haar (正規直交)

def haar_forward(x, levels):
    """x: (..., N) → [近似 (最低域), 詳細 (低い方) ..., 詳細 (最高域)]"""
    a = np.asarray(x, dtype=float)
    details = []
    for _ in range(levels):
        e, o = a[..., 0::2], a[..., 1::2]
        details.append((e - o) / SQ2)
        a = (e + o) / SQ2
    return [a] + details[::-1]


def haar_inverse(bands):
    a = bands[0]
    for d in bands[1:]:
        x = np.empty(a.shape[:-1] + (a.shape[-1] * 2,))
        x[..., 0::2] = (a + d) / SQ2
        x[..., 1::2] = (a - d) / SQ2
        a = x
    return a


# ---------------------------------------------------------------- ブロック浮動小数点量子化

def qmax_of(b):
    return 2 ** (b - 1) - 1


def hybrid_band(profile: Profile, ch: str, k: int) -> bool:
    return profile.hybrid and ch in profile.hybrid_channels and k >= profile.hybrid_start_k


def qmin_of(b, profile: Profile, ch: str, k: int):
    """実験高域だけ負側に1値多い2の補数範囲を使い、全2^b点を利用する。"""
    return -(1 << (b - 1)) if hybrid_band(profile, ch, k) else -qmax_of(b)


def offset_of(b, profile: Profile, ch: str, k: int):
    return -qmin_of(b, profile, ch, k)


def exp_range(k, b, profile: Profile, ch="M"):
    """帯域 k・仮数幅 b・プロファイルで固定する指数範囲 [emin, emax]。

    送受信で同じ値を計算する。フレームにはオフセット emin を送らず、
    eidx = e - emin だけを格納する。
    """
    lev = band_level(k, profile.levels)
    gain = 2.0 ** (lev / 2)                     # その帯域で取りうる最大振幅 (入力 |x|<=1)
    emax = int(np.ceil(np.log2(gain * 2.0 / qmax_of(b))))
    width = profile.exponent_bits(ch, k)
    offset = profile.exponent_offset(ch, k)
    emin = emax - (2 ** width - 1) if offset is None else offset
    return emin, emin + (2 ** width - 1)


def quantize(c, k, b, profile: Profile, clip_opt=True, ch="M"):
    """
    c: (..., ncoef) → (仮数 m (..., ncoef) int, 指数インデックス eidx (...) int)
    指数 e はブロックごとに共有。通常は m = clip(round(c / 2^e), -qmax, qmax)。
    実験用ハイブリッド高域だけ負端を -2^(b-1) として全2^b値を使う。
    clip_opt: 指数を 1 つ下げて少しクリップした方が誤差が小さければそちらを選ぶ
              (エンコーダ側だけの選択。デコーダは変わらない)。
    """
    qmax = qmax_of(b)
    qmin = qmin_of(b, profile, ch, k)
    emin, emax = exp_range(k, b, profile, ch)
    peak = np.abs(c).max(axis=-1)
    e = np.ceil(np.log2(np.maximum(peak, 1e-300) / qmax))
    e = np.clip(e, emin, emax)

    def q(ev):
        m = np.clip(np.round(c / np.exp2(ev)[..., None]), qmin, qmax)
        return m, ((c - m * np.exp2(ev)[..., None]) ** 2).sum(axis=-1)

    m, err = q(e)
    if clip_opt:
        e2 = np.maximum(e - 1, emin)
        m2, err2 = q(e2)
        better = err2 < err
        e = np.where(better, e2, e)
        m = np.where(better[..., None], m2, m)
    return m.astype(np.int64), (e - emin).astype(np.int64)


def quantize_attenuated(c, k, b, profile: Profile, clip_opt=True, ch="M"):
    """共有指数に加え、各区間で量子化刻みを 1 または 1/2 にする。"""
    group = profile.attenuator_group(ch, k)
    if not group:
        m, e = quantize(c, k, b, profile, clip_opt, ch)
        return m, e, np.zeros(np.shape(c)[:-1] + (0,), np.int64)
    c = np.asarray(c)
    qmax = qmax_of(b)
    qmin = qmin_of(b, profile, ch, k)
    emin, emax = exp_range(k, b, profile, ch)
    peak = np.max(np.abs(c), axis=-1)
    e0 = np.clip(np.ceil(np.log2(np.maximum(peak, 1e-300) / qmax)), emin, emax)
    cg = c.reshape(c.shape[:-1] + (-1, group))

    def candidate(e):
        st = np.exp2(e)[..., None, None]
        m0 = np.clip(np.round(cg / st), qmin, qmax)
        m1 = np.clip(np.round(cg / (st * 0.5)), qmin, qmax)
        err0 = np.sum((cg - m0 * st) ** 2, axis=-1)
        err1 = np.sum((cg - m1 * st * 0.5) ** 2, axis=-1)
        attn = (err1 < err0).astype(np.int64)
        chosen = np.where(attn[..., None], m1, m0)
        total = np.sum(np.minimum(err0, err1), axis=-1)
        return chosen.reshape(c.shape).astype(np.int64), attn, total

    m, a, err = candidate(e0)
    if clip_opt:
        e1 = np.maximum(e0 - 1, emin)
        m1, a1, err1 = candidate(e1)
        better = err1 < err
        e0 = np.where(better, e1, e0)
        m = np.where(better[..., None], m1, m)
        a = np.where(better[..., None], a1, a)
    return m, (e0 - emin).astype(np.int64), a


def attenuator_expanded(attn, group, n):
    """係数ごとの 0/1 減衰量。従来フレームは全係数 0。"""
    if not group:
        return np.zeros(n, np.int64)
    return np.repeat(np.asarray(attn, np.int64), group, axis=-1)


def _step(m, eidx, emin):
    """量子化ステップ。eidx はブロックで1つ (スカラー/(...)) か、係数ごと (m と同じ形)"""
    st = np.exp2(np.asarray(eidx, dtype=float) + emin)
    return st if st.shape == np.shape(m) else st[..., None]


def dequantize(m, eidx, k, b, profile: Profile, ch="M", attn=None):
    emin, _ = exp_range(k, b, profile, ch)
    step = _step(m, eidx, emin)
    if attn is not None:
        step = step * np.exp2(-attenuator_expanded(attn, profile.attenuator_group(ch, k), np.shape(m)[-1]))
    return m * step


# ---------------------------------------------------------------- ブロック単位のエンコーダ / デコーダ

class BlockData:
    """1ブロックぶんの量子化結果。mant[ch][k], eidx[ch][k] (0bit の帯域は None)"""

    def __init__(self, mant, eidx, attn=None):
        self.mant = mant
        self.eidx = eidx
        self.attn = attn if attn is not None else {ch: [None] * len(eidx[ch]) for ch in ("M", "S")}


def encode_block(x, profile: Profile, clip_opt=True) -> BlockData:
    """x: (block, 2) L/R, 振幅は ±1 以内"""
    ms = {"M": (x[:, 0] + x[:, 1]) / 2, "S": (x[:, 0] - x[:, 1]) / 2}
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
            m, e, a = quantize_attenuated(c, k, b, profile, clip_opt, ch)
            mant[ch].append(m)
            eidx[ch].append(int(e))
            attn[ch].append(a)
    return BlockData(mant, eidx, attn)


def decode_coeffs(bd: BlockData, profile: Profile):
    """BlockData → {ch: [帯域係数]}"""
    coefs = {}
    for ch, bits in (("M", profile.bits_m), ("S", profile.bits_s)):
        coefs[ch] = []
        for k, b in enumerate(bits):
            n = profile.ncoef(k)
            if b == 0:
                coefs[ch].append(np.zeros(n))
                continue
            coefs[ch].append(dequantize(bd.mant[ch][k], np.int64(bd.eidx[ch][k]), k, b, profile, ch, bd.attn[ch][k]))
    return coefs


def ms_to_lr(M, S):
    return np.stack([M + S, M - S], axis=-1)


def decode_block(bd: BlockData, profile: Profile):
    """BlockData → (block, 2) L/R"""
    coefs = decode_coeffs(bd, profile)
    return ms_to_lr(haar_inverse(coefs["M"]), haar_inverse(coefs["S"]))


def roundtrip(x, profile: Profile):
    """通信路なしの符号化と復号 (ブロックごと)。x は (n, 2) の L/R"""
    nfr = int(np.ceil(len(x) / profile.block))
    xp = np.pad(x, ((0, nfr * profile.block - len(x)), (0, 0)))
    out = np.zeros_like(xp)
    for i in range(nfr):
        out[i * profile.block:(i + 1) * profile.block] = decode_block(
            encode_block(xp[i * profile.block:(i + 1) * profile.block], profile), profile)
    return out[:len(x)]
