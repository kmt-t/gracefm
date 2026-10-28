"""
DSP に依存する整数演算。ハードウェアが変わるときは、このモジュールの幅と演算だけを差し替える。

想定ハードウェア: Zynq-7010 の DSP48E1 (UG479 / UG953)。
  - 乗算器: 25 bit × 18 bit の符号つき (A ポートは下位25 bit、B ポートは18 bit)
  - アキュムレータ: 48 bit
  - プリアダー: 25 bit
gracefm.fixed の固定小数点演算は、ここで定義する幅と関数だけを使う。
"""
import numpy as np

MULT_BITS = 25                  # 乗算器の A 入力の幅 (符号つき)
CONST_BITS = 18                 # 乗算器の B 入力の幅 (符号つき)
ACC_BITS = 48                   # アキュムレータの幅 (符号つき)

MULT_MAX = (1 << (MULT_BITS - 1)) - 1
MULT_MIN = -(1 << (MULT_BITS - 1))

SQ2_SHIFT = 16
SQ2_INV = 46341                 # 1/√2 を 2^SQ2_SHIFT 倍した整数 (相対誤差 約1e-6)
assert SQ2_INV < (1 << (CONST_BITS - 1))
assert (MULT_MAX * SQ2_INV * 2) < (1 << (ACC_BITS - 1))


def saturate(v):
    """乗算器の入力幅 (符号つき25 bit) に飽和させる。設計上は起きない (保険)"""
    return np.minimum(np.maximum(v, MULT_MIN), MULT_MAX)


def saturate_bits(v, bits):
    """符号つき bits bit に飽和させる (対称: ±(2^(bits-1) - 1))"""
    lim = (1 << (bits - 1)) - 1
    return np.minimum(np.maximum(v, -lim), lim)


def mac_sq2_inv(p, q, sign=1):
    """(p + sign*q) / √2。p*C + sign*q*C をアキュムレータで足し合わせ、四捨五入して右シフトする"""
    acc = np.asarray(p, np.int64) * SQ2_INV + sign * np.asarray(q, np.int64) * SQ2_INV
    return saturate((acc + (1 << (SQ2_SHIFT - 1))) >> SQ2_SHIFT)


def round_shift(c, s):
    """c / 2^s の四捨五入 (s >= 1)。s は配列でもよい"""
    s = np.asarray(s, np.int64)
    return (np.asarray(c, np.int64) + (np.int64(1) << (s - 1))) >> s


def shift_signed(m, s):
    """m * 2^s。s < 0 のときは四捨五入つきの右シフト"""
    m = np.asarray(m, np.int64)
    s = np.asarray(s, np.int64)
    left = m << np.maximum(s, 0)
    right = round_shift(m, np.maximum(-s, 1))
    return np.where(s >= 0, left, right)


def bit_length(n):
    """n >= 0 の整数配列のbit長 (0 のとき 0)"""
    n = np.asarray(n, np.int64)
    out = np.zeros(n.shape, np.int64)
    for s in (32, 16, 8, 4, 2, 1):                       # 二分探索 (6 回)
        high = (n >> s) > 0
        out += s * high
        n = np.where(high, n >> s, n)
    return out + (n > 0)


ERR_FRAC_BITS = 8               # 誤差の二乗和を取るときの相対精度 (量子化刻みに対する bit 数)


def sq_err_sum(err, shift):
    """
    誤差 err の二乗和 (最後の軸で足す)。乗算器は 25 bit × 18 bit なので、err を右シフトして 18 bit符号つきに
    切り詰めてから二乗する (二乗は 18 × 18 bit)。shift は量子化刻みの bit 数から ERR_FRAC_BITS を引いた値 (0 以上)。
    刻みの異なる候補を比べるときは、同じ shift を使う。
    """
    r = np.minimum(np.maximum(np.asarray(err, np.int64) >> np.asarray(shift, np.int64),
                              -(1 << (CONST_BITS - 1))), (1 << (CONST_BITS - 1)) - 1)
    return np.sum(r * r, axis=-1)


# ---------------------------------------------------------------- log と exp (表を使わない)
LN2_Q15 = 22713                      # ln 2 を Q15 で
LOG2E_Q8_PER_LLR = 23637             # log2(e) × 2^8 / 4 を 2^8 倍した整数 (LLR は小数 2 bit): d_q8 = llr × 92.33
ONE = 1 << 15


def log2_q8(x):
    """正の整数 x の log2(x) × 2^8。最上位 bit の位置 + 正規化した仮数を 8 回二乗して得る小数 8 bit (乗算と比較だけ)"""
    x = int(x)
    msb = x.bit_length() - 1
    m = (x << 15) >> msb if msb <= 15 else x >> (msb - 15)           # 仮数 [1, 2) を Q15 で
    frac = 0
    for _ in range(8):
        m = (m * m) >> 15
        frac <<= 1
        if m >= 2 * ONE:
            m >>= 1
            frac |= 1
    return (msb << 8) + frac


def pow2_neg_q15(d_q8):
    """2^(-d) を Q15 で (d >= 0、Q8 の整数または配列)。小数部は e^(-t)、t = f·ln2 のマクローリン展開 (7 項)、整数部はシフト"""
    d = np.asarray(d_q8, np.int64)
    t = ((d & 255) * LN2_Q15) >> 8                                   # f · ln 2 (Q15)
    r = np.full(d.shape, ONE, np.int64)
    for k in range(7, 0, -1):
        r = ONE - (((t * r) >> 15) // k)                             # 1 - (t/k)(...)
    return r >> np.minimum(d >> 8, 31)


def inv1p2pow_q15(d_q8):
    """1 / (1 + 2^d) を Q15 で (d は符号つき、Q8 の整数または配列)。d < 0 は 1 - 1 / (1 + 2^|d|)"""
    d = np.asarray(d_q8, np.int64)
    x = pow2_neg_q15(np.minimum(np.abs(d), 16 << 8))                 # 2^(-|d|)
    w = (x << 15) // (x + ONE)                                       # d >= 0 のときの 1 / (1 + 2^|d|)
    return np.where(d >= 0, w, ONE - w)


def sigmoid_q15(llr):
    """整数 LLR (小数 2 bit、正 = 0 らしい) → ビットが 1 である確率 1 / (1 + e^LLR) を Q15 で"""
    return inv1p2pow_q15((np.asarray(llr, np.int64) * LOG2E_Q8_PER_LLR + 128) >> 8)
