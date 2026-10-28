"""
2系統の融合 (帯域ごとの逆分散重み)。すべて整数演算。

時刻合わせ後の PCM (符号つき24 bit整数) をブロック (block サンプル) の区間ごとに処理する。2系統のブロックの格子は同じ。
M と S は別々に融合する。区間の出力は、その区間の 2系統の値だけから決まる (未来を使わない)。
誤差分散は対数領域の整数 (log2 × 2^8、INF_LOG = 情報なし) で受け取り、重みは Q15 の整数で作る。
"""
import numpy as np

from .codec import FRAC, haar_forward, haar_inverse, ms_to_lr
from .dsp import inv1p2pow_q15

INF_LOG = 1 << 40
HALF = 1 << 14
ONE = 1 << 15


def weight_a(la, lb):
    """w_A = R_B / (R_A + R_B) = 1 / (1 + 2^(LA - LB)) (Q15)。LA、LB は log2 × 2^8。情報なし (INF_LOG) は重み 0 / 1 / 1/2"""
    la, lb = np.asarray(la, np.int64), np.asarray(lb, np.int64)
    d = np.clip(np.where((la >= INF_LOG) | (lb >= INF_LOG), 0, la - lb), -(16 << 8), 16 << 8)
    w = inv1p2pow_q15(d)
    w = np.where(la >= INF_LOG, np.where(lb >= INF_LOG, HALF, 0), np.where(lb >= INF_LOG, ONE, w))
    return w


def _to_ms(y, ns, seg):
    """PCM (n, 2) → M/S (小数 FRAC bit、codec と同じ) の (ns, seg, 2)"""
    y = np.pad(y, ((0, ns * seg - len(y)), (0, 0)))
    m = ((y[:, 0] + y[:, 1] + 4) >> 3).reshape(ns, seg)
    s = ((y[:, 0] - y[:, 1] + 4) >> 3).reshape(ns, seg)
    return np.stack([m, s], axis=2)


def fuse_band(yA, vA, yB, vB, seg, levels, rbA, rbB):
    """
    帯域ごとの融合。2系統のブロックの格子は同じなので、ブロック (seg サンプル) の区間を Haar 変換すると、
    各帯域の係数が両系統で 1対1 に対応する。係数ごとに、各系統のデコーダが見積もった誤差分散 R で逆分散重み付けする:
        w_A = R_B / (R_A + R_B)
    R は帯域ごと・半ブロックごとに見積もられる。係数が 2つ以上ある帯域は、前半の係数に前半の R、後半の係数に
    後半の R を使う (Haar の詳細係数の添字は時間位置に対応する)。係数 1つの最低域は両半分の重みの平均。
    送っていない帯域は R = ∞ (情報なし) で、その帯域は送っている方の系統だけで決まる。
    seg: ブロック長、levels: Haar の段数。rbA, rbB: (n, 2, 帯域数) StreamDecoder.rb_trace。返り値: (y (n, 2)、valid、区間ごとの M 最低域の w_A (Q15))
    """
    n = len(yA)
    nb = rbA.shape[2]
    assert nb == levels + 1, "帯域数と段数が合わない"
    ns = -(-n // seg)
    pad = ns * seg - n
    h = seg // 2
    msA, msB = _to_ms(yA, ns, seg), _to_ms(yB, ns, seg)
    va, vb = np.pad(vA, (0, pad))[::seg], np.pad(vB, (0, pad))[::seg]
    no_info = np.int64(INF_LOG)
    rA = np.pad(rbA, ((0, pad), (0, 0), (0, 0)), constant_values=no_info)
    rB = np.pad(rbB, ((0, pad), (0, 0), (0, 0)), constant_values=no_info)
    a1, a2, b1, b2 = rA[::seg], rA[h::seg], rB[::seg], rB[h::seg]
    only_a, only_b = va & ~vb, vb & ~va

    def override(w):
        return np.where(only_a[:, None], ONE, np.where(only_b[:, None], 0, w))

    out = np.zeros((ns, seg, 2), np.int64)
    trace = None
    for ci in range(2):
        bA = haar_forward(msA[:, :, ci], levels)
        bB = haar_forward(msB[:, :, ci], levels)
        bands = []
        for k in range(nb):
            nn = bA[k].shape[1]
            w1 = weight_a(a1[:, ci, k], b1[:, ci, k])[:, None]
            w2 = weight_a(a2[:, ci, k], b2[:, ci, k])[:, None]
            if nn == 1:
                w = override((w1 + w2) >> 1)
            else:
                w = np.concatenate([np.repeat(override(w1), nn // 2, axis=1), np.repeat(override(w2), nn // 2, axis=1)], axis=1)
            if ci == 0 and k == 0:
                trace = w[:, 0]
            bands.append((w * bA[k] + (ONE - w) * bB[k] + HALF) >> 15)
        out[:, :, ci] = haar_inverse(bands)
    valid = np.repeat(va | vb, seg)[:n]
    y = ms_to_lr(out[:, :, 0].reshape(-1)[:n], out[:, :, 1].reshape(-1)[:n]) * valid[:, None]
    return y, valid, trace
