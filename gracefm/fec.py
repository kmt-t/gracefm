"""
誤り訂正と誤り検出。

畳み込み符号: 拘束長 7, 符号化率 1/2, 生成多項式 133, 171 (8進)。フレームごとに 6bit の 0 で終端。
  レジスタ reg = (入力 u << 6) | 状態 s。出力 = parity(reg & g)。次状態 = reg >> 1。
  → c0[t] = u[t] ^ u[t-2] ^ u[t-3] ^ u[t-5] ^ u[t-6]
     c1[t] = u[t] ^ u[t-1] ^ u[t-2] ^ u[t-3] ^ u[t-6]
  符号化ビットの順序: c0[0], c1[0], c0[1], c1[1], ...
復号: 軟判定ビタビ (軟値が正なら 0 らしい)。軟値は符号つき LLR_BITS bit の整数で、乗算を使わない (docs/FIXED.md)。
CRC: ヘッダの基本CRCは12bit (多項式 0x80F)、高域CRCは10bit (多項式 0x233)、初期値は全ビット1、MSB から。crc16 は 16bit CCITT (0x1021)。
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
# 期待される符号の組 (s0, s1) → 表の位置: (+,+)=0 (+,-)=1 (-,+)=2 (-,-)=3
_B0 = (1 - _S0[:, 0]) + (1 - _S0[:, 1]) // 2
_B1 = (1 - _S1[:, 0]) + (1 - _S1[:, 1]) // 2


def crc(bits, width, poly):
    """width bit の CRC (MSB から。初期値は全ビット1)"""
    mask = (1 << width) - 1
    reg = mask
    for b in np.asarray(bits, np.int64):
        top = (reg >> (width - 1)) & 1
        reg = (reg << 1) & mask
        if top ^ int(b):
            reg ^= poly
    return np.array([(reg >> (width - 1 - i)) & 1 for i in range(width)], np.int64)


def crc16(bits):
    return crc(bits, 16, 0x1021)


# ヘッダの検査 (フレームが短いので 10〜12 bit で足りる)
CRC_CORE = (12, 0x80F)       # 基本CRC: x^12 + x^11 + x^3 + x^2 + x + 1
CRC_HIGH = (10, 0x233)       # 高域CRC: x^10 + x^9 + x^5 + x^4 + x + 1


def crc_core(bits):
    return crc(bits, *CRC_CORE)


def crc_high(bits):
    return crc(bits, *CRC_HIGH)


# ---------------------------------------------------------------- 系統符号 (パリティだけを送る)
# 同じ (133,171) の符号語集合を、情報ビット x を符号語の第1系列 c0 として送る再帰形で使う。
# 情報ビット x は別の場所 (Haar係数部) に置き、ここでは第2系列 c1 (パリティ) と終端の 6 ビットだけを作る。
#   u[t] = x[t] ^ u[t-2] ^ u[t-3] ^ u[t-5] ^ u[t-6]      (c0[t] = x[t] になる入力 u)
#   c1[t] = u[t] ^ u[t-1] ^ u[t-2] ^ u[t-3] ^ u[t-6]
# 終端は u = 0 を 6 ビット続け、そのとき c0 になる x の 6 ビット (tail) も送る。

def _rsc_inputs(x):
    n = len(x)
    u = np.zeros(n + K - 1, np.int64)
    for t in range(n):
        u[t] = x[t] ^ (u[t - 2] if t >= 2 else 0) ^ (u[t - 3] if t >= 3 else 0) \
            ^ (u[t - 5] if t >= 5 else 0) ^ (u[t - 6] if t >= 6 else 0)
    return u


def rsc_parity(x):
    """x: 情報ビット (n,) → (パリティ (n+6,), 終端の x (6,))"""
    x = np.asarray(x, np.int64)
    n = len(x)
    u = _rsc_inputs(x)
    c = conv_encode(u[:n])           # u[:n] を (133,171) で符号化 → c0 は x に一致する
    assert np.array_equal(c[0::2][:n], x)
    return c[1::2], c[0::2][n:]


# ---------------------------------------------------------------- 整数のビタビ復号
# 軟値は符号つき LLR_BITS bit の整数 (正 = 0 らしい)。枝メトリックは期待される符号 ±1 との内積 (2 つの軟値の和・差) で、
# 経路メトリックは毎ステップで最大値を引いて正規化し、PM_BITS bit の符号つきの範囲に飽和させる。到達できない状態は PM_MIN から始める。
LLR_BITS = 8
LLR_MAX = (1 << (LLR_BITS - 1)) - 1
PM_BITS = 14
PM_MIN = -(1 << (PM_BITS - 1))


def viterbi_decode(soft, nbits):
    """soft: 長さ 2*(nbits+6) の整数の軟値 → 復号ビット (nbits,)"""
    soft = np.asarray(soft, np.int64)
    assert np.abs(soft).max(initial=0) <= LLR_MAX
    L = nbits + K - 1
    r = soft[: 2 * L].reshape(L, 2)
    pm = np.full(NSTATE, PM_MIN, np.int64)
    pm[0] = 0
    choice = np.zeros((L, NSTATE), np.int8)
    # 枝メトリックは 2 つの軟値の符号の組 (+,+) (+,-) (-,+) (-,-) の 4 通りしかないので、表にして引く
    sums = np.stack([r[:, 0] + r[:, 1], r[:, 0] - r[:, 1], -r[:, 0] + r[:, 1], -r[:, 0] - r[:, 1]], axis=1)
    forced = _U == 1
    for t in range(L):
        bm = sums[t]
        m0 = pm[_P0] + bm[_B0]
        m1 = pm[_P1] + bm[_B1]
        ch = m1 > m0
        pm = np.maximum(m0, m1)
        choice[t] = ch
        if t >= nbits:                                  # 終端区間は入力 0 のみ
            pm[forced] = PM_MIN
        pm = np.maximum(pm - pm.max(), PM_MIN)          # 正規化と飽和
    s = 0
    bits = np.zeros(L, np.int64)
    for t in range(L - 1, -1, -1):
        bits[t] = s >> (K - 2)
        s = ((s << 1) & (NSTATE - 1)) | int(choice[t, s])
    return bits[:nbits]


def rsc_decode(x_soft, parity_soft, tail_soft):
    """x_soft (n,), parity_soft (n+6,), tail_soft (6,): 整数の軟値 (正 = 0 らしい) → 訂正後の情報ビット (n,)"""
    n = len(x_soft)
    r = np.empty(2 * (n + K - 1), np.int64)
    r[0::2] = np.concatenate([np.asarray(x_soft, np.int64), np.asarray(tail_soft, np.int64)])
    r[1::2] = np.asarray(parity_soft, np.int64)
    u = viterbi_decode(r, n)
    return conv_encode(u)[0::2][:n]
