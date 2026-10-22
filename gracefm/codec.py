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
    指数 e はブロックごとに共有。m = clip(round(c / 2^e), -qmax, qmax)。
    clip_opt: 指数を 1 つ下げて少しクリップした方が誤差が小さければそちらを選ぶ
              (エンコーダ側だけの選択。デコーダは変わらない)。
    """
    qmax = qmax_of(b)
    emin, emax = exp_range(k, b, profile, ch)
    peak = np.abs(c).max(axis=-1)
    e = np.ceil(np.log2(np.maximum(peak, 1e-300) / qmax))
    e = np.clip(e, emin, emax)

    def q(ev):
        m = np.clip(np.round(c / np.exp2(ev)[..., None]), -qmax, qmax)
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
    emin, emax = exp_range(k, b, profile, ch)
    peak = np.max(np.abs(c), axis=-1)
    e0 = np.clip(np.ceil(np.log2(np.maximum(peak, 1e-300) / qmax)), emin, emax)
    cg = c.reshape(c.shape[:-1] + (-1, group))

    def candidate(e):
        st = np.exp2(e)[..., None, None]
        m0 = np.clip(np.round(cg / st), -qmax, qmax)
        m1 = np.clip(np.round(cg / (st * 0.5)), -qmax, qmax)
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


def cells(m, eidx, k, b, profile: Profile, ch="M", attn=None):
    """
    各係数について、元の係数が取り得る区間 [lo, hi] (量子化器の逆像。ポストフィルタの射影に使う)。

    飽和していない値 (|m| < qmax): 丸めの区間 [(m - 0.5)·step, (m + 0.5)·step]。
    飽和した値 (m = ±qmax): エンコーダは指数として e0 = ceil(log2(peak / qmax)) か、クリップを許す
      e0 - 1 のどちらかを選ぶ (quantize)。デコーダはどちらか区別できないので両方を含める。
      e0 のとき |c| <= qmax·step、e0 - 1 のとき |c| <= 2·qmax·step。さらに入力 |x| <= 1 から
      |c| <= 2^(lev/2) (exp_range の gain)。よって m = +qmax の区間は
      [(qmax - 0.5)·step, min(2·qmax·step, gain)] (m = -qmax は符号を反転)。
    指数は emax で頭打ちにならないよう emax を決めているので、合法な入力ではこの区間は必ず元の係数を含む
    (tests/test_gracefm.py::test_cells_contain_original)。
    """
    emin, _ = exp_range(k, b, profile, ch)
    qmax = qmax_of(b)
    gain = 2.0 ** (band_level(k, profile.levels) / 2)
    step = _step(m, eidx, emin)
    if attn is not None:
        step = step * np.exp2(-attenuator_expanded(attn, profile.attenuator_group(ch, k), np.shape(m)[-1]))
    lo = (m - 0.5) * step
    hi = (m + 0.5) * step
    top = np.minimum((4 if attn is not None else 2) * qmax * step, gain)
    hi = np.where(m == qmax, top, hi)
    lo = np.where(m == -qmax, -top, lo)
    return lo, hi


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
    """BlockData → {ch: [帯域係数]}, {ch: [(lo, hi) or None]}"""
    coefs, cell = {}, {}
    for ch, bits in (("M", profile.bits_m), ("S", profile.bits_s)):
        coefs[ch], cell[ch] = [], []
        for k, b in enumerate(bits):
            n = profile.ncoef(k)
            if b == 0:
                coefs[ch].append(np.zeros(n))
                cell[ch].append(None)
                continue
            m = bd.mant[ch][k]
            e = np.int64(bd.eidx[ch][k])
            a = bd.attn[ch][k]
            coefs[ch].append(dequantize(m, e, k, b, profile, ch, a))
            cell[ch].append(cells(m, e, k, b, profile, ch, a))
    return coefs, cell


def ms_to_lr(M, S):
    return np.stack([M + S, M - S], axis=-1)


def decode_block(bd: BlockData, profile: Profile):
    """BlockData → (block, 2) L/R"""
    coefs, _ = decode_coeffs(bd, profile)
    return ms_to_lr(haar_inverse(coefs["M"]), haar_inverse(coefs["S"]))
