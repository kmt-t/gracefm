"""
2系統の融合 (帯域ごとの逆分散重み)。

時刻合わせ後の PCM を半ブロック (block/2 サンプル) の区間ごとに処理する。系統 B は格子が半ブロック
ずれているので、各区間は必ず A の 1ブロックと B の 1ブロックの中に収まる (同じ時間区間を比べられる)。
M と S は別々に融合する。区間の出力は、その区間の 2系統の値だけから決まる (未来を使わない)。
"""
import numpy as np

from .codec import haar_forward, haar_inverse


def fuse_band(yA, vA, yB, vB, seg, rbA, rbB):
    """
    帯域ごとの融合 (band)。系統 B の格子は半ブロックずれているので、半ブロック (seg サンプル) の区間に対して
    各系統の出力を (段数 - 1) 段の Haar 変換にかけると、段数が (段数 - 1) 以下の帯域の係数は両系統とも
    自分のブロックの係数とそのまま対応する。最低域の 2帯域 (近似と最も粗い詳細) は区間の平均 1つにまとまる。
    帯域ごとに、各系統のデコーダが受信座標から見積もった係数あたりの誤差分散 R で逆分散重み付けする:
        w_A = (1/R_A) / (1/R_A + 1/R_B)
    送っていない帯域 (ビット数 0) は R = ∞ (情報なし) なので、その帯域は送っている方の系統だけで決まる。
    主系と副系でビットレートが違っても (副系が高域を送らなくても)、帯域ごとに正しく重みが付く。
    遅延は soft と同じ (区間の両系統の出力がそろえば出せる)。
    rbA, rbB: (n, 2, 帯域数) StreamDecoder.rb_trace。返り値: (y, valid, 区間ごとの M 最低域の w_A)
    """
    n = len(yA)
    nb = rbA.shape[2]
    lev = int(np.log2(seg))                         # 区間の Haar の段数 (= ブロックの段数 - 1)
    assert nb == lev + 2, "帯域数とブロック長が合わない"
    ns = -(-n // seg)
    pad = ns * seg - n

    def prep(y, v, rb):
        y = np.pad(y, ((0, pad), (0, 0)))
        v = np.pad(v, (0, pad))[::seg]
        rb = np.pad(rb, ((0, pad), (0, 0), (0, 0)), constant_values=np.nan)[::seg]   # (ns, 2, nb)
        # 区間の帯域 j: j = 0 は元の帯域 0 と 1 の和 (分散は平均)、j ≥ 1 は元の帯域 j + 1
        rf = np.concatenate([(rb[:, :, :1] + rb[:, :, 1:2]) / 2, rb[:, :, 2:]], axis=2)
        inv = np.where(np.isfinite(rf), 1.0 / np.maximum(rf, 1e-30), 0.0)
        ms = np.stack([(y[:, 0] + y[:, 1]) / 2, (y[:, 0] - y[:, 1]) / 2], axis=1).reshape(ns, seg, 2)
        return ms, v, inv

    msA, va, iA = prep(yA, vA, rbA)
    msB, vb, iB = prep(yB, vB, rbB)
    tot = iA + iB
    wA = np.where(tot > 0, iA / np.where(tot > 0, tot, 1.0), 0.5)          # (ns, 2, nb-1)
    wA = np.where((va & ~vb)[:, None, None], 1.0, np.where((vb & ~va)[:, None, None], 0.0, wA))
    out = np.zeros((ns, seg, 2))
    for ci in range(2):
        bA = haar_forward(msA[:, :, ci], lev)
        bB = haar_forward(msB[:, :, ci], lev)
        bands = [wA[:, ci, j][:, None] * bA[j] + (1 - wA[:, ci, j])[:, None] * bB[j] for j in range(lev + 1)]
        out[:, :, ci] = haar_inverse(bands)
    m, s = out[:, :, 0].reshape(-1)[:n], out[:, :, 1].reshape(-1)[:n]
    valid = np.repeat(va | vb, seg)[:n]
    y = np.stack([m + s, m - s], axis=1) * valid[:, None]
    return y, valid, wA[:, 0, 0]
