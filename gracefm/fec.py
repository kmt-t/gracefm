"""
誤り訂正と誤り検出。

畳み込み符号: 拘束長 7, 符号化率 1/2, 生成多項式 133, 171 (8進)。フレームごとに 6bit の 0 で終端。
  レジスタ reg = (入力 u << 6) | 状態 s。出力 = parity(reg & g)。次状態 = reg >> 1。
  → c0[t] = u[t] ^ u[t-2] ^ u[t-3] ^ u[t-5] ^ u[t-6]
     c1[t] = u[t] ^ u[t-1] ^ u[t-2] ^ u[t-3] ^ u[t-6]
  符号化ビットの順序: c0[0], c1[0], c0[1], c1[1], ...
復号: 軟判定ビタビ (軟値が正なら 0 らしい)。
CRC: CRC-16-CCITT (多項式 0x1021, 初期値 0xFFFF), MSB から。
"""
import numpy as np

K = 7
NSTATE = 1 << (K - 1)
G = (0o133, 0o171)
TAPS = ((0, 2, 3, 5, 6), (0, 1, 2, 3, 6))       # c0, c1 が参照する u[t - i] の i


def conv_encode(bits):
    u = np.concatenate([np.asarray(bits, np.int64), np.zeros(K - 1, np.int64)])
    out = np.empty(2 * len(u), np.int64)
    for j, taps in enumerate(TAPS):
        h = np.zeros(K, np.int64)
        h[list(taps)] = 1
        out[j::2] = np.convolve(u, h)[: len(u)] & 1
    return out


def _branch_table():
    out = np.zeros((NSTATE, 2, 2), np.int64)
    for s in range(NSTATE):
        for u in range(2):
            reg = (u << (K - 1)) | s
            for j, g in enumerate(G):
                out[s, u, j] = bin(reg & g).count("1") & 1
    return out


_OUT = _branch_table()
_NS = np.arange(NSTATE)
_U = _NS >> (K - 2)                             # 次状態 ns に入るときの入力ビット
_P0 = (_NS << 1) & (NSTATE - 1)                 # ns の前の状態 (2通り)
_P1 = _P0 | 1
_S0 = 1 - 2 * _OUT[_P0, _U]                     # (64, 2) 期待される符号 (+1 = bit0)
_S1 = 1 - 2 * _OUT[_P1, _U]


def viterbi_decode(soft, nbits):
    """soft: 長さ 2*(nbits+6) の軟値 → 復号ビット (nbits,)"""
    soft = np.asarray(soft, float)
    L = nbits + K - 1
    r = soft[: 2 * L].reshape(L, 2)
    pm = np.full(NSTATE, -np.inf)
    pm[0] = 0.0
    choice = np.zeros((L, NSTATE), np.int8)
    for t in range(L):
        m0 = pm[_P0] + _S0 @ r[t]
        m1 = pm[_P1] + _S1 @ r[t]
        ch = m1 > m0
        pm = np.where(ch, m1, m0)
        choice[t] = ch
        if t >= nbits:                          # 終端区間は入力 0 のみ
            pm[_U == 1] = -np.inf
    s = 0
    bits = np.zeros(L, np.int64)
    for t in range(L - 1, -1, -1):
        bits[t] = s >> (K - 2)
        s = ((s << 1) & (NSTATE - 1)) | int(choice[t, s])
    return bits[:nbits]


def crc16(bits):
    reg = 0xFFFF
    for b in np.asarray(bits, np.int64):
        top = (reg >> 15) & 1
        reg = (reg << 1) & 0xFFFF
        if top ^ int(b):
            reg ^= 0x1021
    return np.array([(reg >> (15 - i)) & 1 for i in range(16)], np.int64)
