"""
2系統の融合 (帯域ごとの逆分散重み)。

時刻合わせ後の PCM をブロック (block サンプル) の区間ごとに処理する。2系統のブロックの格子は同じ。
M と S は別々に融合する。区間の出力は、その区間の 2系統の値だけから決まる (未来を使わない)。
"""
import numpy as np

from .codec import haar_forward, haar_inverse


def fuse_band(yA, vA, yB, vB, seg, rbA, rbB):
    """
    帯域ごとの融合 (band)。2系統のブロックの格子は同じなので、ブロック (seg サンプル) の区間を Haar 変換すると、
    各帯域の係数が両系統で 1対1 に対応する。係数ごとに、各系統のデコーダが受信座標から見積もった係数あたりの
    誤差分散 R で逆分散重み付けする:
        w_A = (1/R_A) / (1/R_A + 1/R_B)
    R は帯域ごと・半ブロックごとに見積もられる。係数が 2つ以上ある帯域は、前半の係数に前半の R、後半の係数に
    後半の R を使う (Haar の詳細係数の添字は時間位置に対応する)。係数 1つの最低域は両半分の平均。
    送っていない帯域 (ビット数 0) は R = ∞ (情報なし) なので、その帯域は送っている方の系統だけで決まる。
    主系と副系でビットレートが違っても (副系が高域を送らなくても)、帯域ごとに正しく重みが付く。
    遅延は soft と同じ (区間の両系統の出力がそろえば出せる)。
    rbA, rbB: (n, 2, 帯域数) StreamDecoder.rb_trace。返り値: (y, valid, 区間ごとの M 最低域の w_A)
    """
    n = len(yA)
    nb = rbA.shape[2]
    lev = int(np.log2(seg))                         # ブロックの Haar の段数
    assert nb == lev + 1, "帯域数とブロック長が合わない"
    ns = -(-n // seg)
    pad = ns * seg - n
    h = seg // 2

    def prep(y, v, rb):
        y = np.pad(y, ((0, pad), (0, 0)))
        v = np.pad(v, (0, pad))[::seg]
        rb = np.pad(rb, ((0, pad), (0, 0), (0, 0)), constant_values=np.nan)
        inv = np.where(np.isfinite(rb), 1.0 / np.maximum(rb, 1e-30), 0.0)
        ms = np.stack([(y[:, 0] + y[:, 1]) / 2, (y[:, 0] - y[:, 1]) / 2], axis=1).reshape(ns, seg, 2)
        return ms, v, inv[::seg], inv[h::seg]       # 前半・後半の 1/R: (ns, 2, nb)

    msA, va, a1, a2 = prep(yA, vA, rbA)
    msB, vb, b1, b2 = prep(yB, vB, rbB)

    def weight(ia, ib, only_a, only_b):
        tot = ia + ib
        w = np.where(tot > 0, ia / np.where(tot > 0, tot, 1.0), 0.5)
        return np.where(only_a[:, None], 1.0, np.where(only_b[:, None], 0.0, w))

    only_a, only_b = va & ~vb, vb & ~va
    out = np.zeros((ns, seg, 2))
    trace = None
    for ci in range(2):
        bA = haar_forward(msA[:, :, ci], lev)
        bB = haar_forward(msB[:, :, ci], lev)
        bands = []
        for k in range(nb):
            nn = bA[k].shape[1]
            if nn == 1:
                w = weight(((a1[:, ci, k] + a2[:, ci, k]) / 2)[:, None], ((b1[:, ci, k] + b2[:, ci, k]) / 2)[:, None], only_a, only_b)
            else:
                w = np.concatenate([np.repeat(weight(a1[:, ci, k][:, None], b1[:, ci, k][:, None], only_a, only_b), nn // 2, axis=1),
                                    np.repeat(weight(a2[:, ci, k][:, None], b2[:, ci, k][:, None], only_a, only_b), nn // 2, axis=1)], axis=1)
            if ci == 0 and k == 0:
                trace = w[:, 0]
            bands.append(w * bA[k] + (1 - w) * bB[k])
        out[:, :, ci] = haar_inverse(bands)
    m, s = out[:, :, 0].reshape(-1)[:n], out[:, :, 1].reshape(-1)[:n]
    valid = np.repeat(va | vb, seg)[:n]
    y = np.stack([m + s, m - s], axis=1) * valid[:, None]
    return y, valid, trace
