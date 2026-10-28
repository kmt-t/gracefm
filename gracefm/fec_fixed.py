"""
整数だけで動くビタビ復号 (K=7、(133,171))。乗算を使わず、加算・比較・選択だけで書ける。

軟値は符号つき LLR_BITS bit の整数 (正 = 0 らしい)。枝メトリックは期待される符号 ±1 との内積 (2 つの軟値の和・差) で、
経路メトリックは毎ステップで最大値を引いて正規化し、PM_BITS bit の符号つきの範囲に飽和させる。
到達できない状態は PM_MIN から始める。幅の根拠は docs/FIXED.md を参照。
"""
import numpy as np

from . import fec

LLR_BITS = 6
LLR_MAX = (1 << (LLR_BITS - 1)) - 1
PM_BITS = 12
PM_MIN = -(1 << (PM_BITS - 1))


def viterbi_decode_int(soft, nbits):
    """soft: 長さ 2*(nbits+6) の整数の軟値 → 復号ビット (nbits,)"""
    soft = np.asarray(soft, np.int64)
    assert np.abs(soft).max(initial=0) <= LLR_MAX
    L = nbits + fec.K - 1
    r = soft[: 2 * L].reshape(L, 2)
    pm = np.full(fec.NSTATE, PM_MIN, np.int64)
    pm[0] = 0
    choice = np.zeros((L, fec.NSTATE), np.int8)
    for t in range(L):
        m0 = pm[fec._P0] + fec._S0 @ r[t]
        m1 = pm[fec._P1] + fec._S1 @ r[t]
        ch = m1 > m0
        pm = np.where(ch, m1, m0)
        choice[t] = ch
        if t >= nbits:                                  # 終端区間は入力 0 のみ
            pm[fec._U == 1] = PM_MIN
        pm = np.maximum(pm - pm.max(), PM_MIN)          # 正規化と飽和
    s = 0
    bits = np.zeros(L, np.int64)
    for t in range(L - 1, -1, -1):
        bits[t] = s >> (fec.K - 2)
        s = ((s << 1) & (fec.NSTATE - 1)) | int(choice[t, s])
    return bits[:nbits]


def rsc_decode_int(x_soft, parity_soft, tail_soft):
    """x_soft (n,), parity_soft (n+6,), tail_soft (6,): 整数の軟値 (正 = 0 らしい) → 訂正後の情報ビット (n,)"""
    n = len(x_soft)
    r = np.empty(2 * (n + fec.K - 1), np.int64)
    r[0::2] = np.concatenate([np.asarray(x_soft, np.int64), np.asarray(tail_soft, np.int64)])
    r[1::2] = np.asarray(parity_soft, np.int64)
    u = viterbi_decode_int(r, n)
    return fec.conv_encode(u)[0::2][:n]
