"""
欠落補間 (PLC)。すべて整数演算。届かなかった区間を LPC 外挿で埋め、hold_ms までは等倍、その後 fade_ms で 0 へ。
復帰時は xfade サンプルで外挿値から受信値へクロスフェードする。

LPC は、ハン窓をかけた履歴の自己相関 (窓かけ後の値を 15 bit に正規化して積和) から Levinson-Durbin で求める。
係数は Q15、反射係数は Q15、予測誤差は整数。DSP の乗算器の幅は gracefm.dsp を参照。
"""
import numpy as np

from .dsp import bit_length, saturate_bits
from .tables import HANN128_Q15

PCM_BITS = 24


def lpc(x, order):
    """x: 整数の履歴 → LPC 係数 a[0..order] (Q15、a[0] = 1)"""
    x = np.asarray(x, np.int64)
    n = len(x)
    hann = np.array(HANN128_Q15, np.int64)
    win = hann[(np.arange(n) * (len(hann) - 1)) // max(n - 1, 1)]
    w = (x * win) >> 15
    shift = max(0, int(bit_length(np.array([np.abs(w).max()]))[0]) - 15)           # 15 bit に正規化 (積は 30 bit)
    w = w >> shift
    r = np.array([int((w[: n - k] * w[k:]).sum()) for k in range(order + 1)], np.int64)
    a = np.zeros(order + 1, np.int64)
    a[0] = 1 << 15
    if r[0] <= 0:
        return a
    r[0] += r[0] >> 13                                                              # 白色雑音補正 (約 1.0001 倍)
    err = int(r[0])
    for i in range(1, order + 1):
        acc = int(r[i]) * (1 << 15) + int((a[1:i] * r[i - 1:0:-1]).sum())
        q = abs(acc) // err                                                             # 反射係数 -acc/err (Q15、0 方向へ丸める)
        k = int(np.clip(-q if acc >= 0 else q, -(1 << 15) + 1, (1 << 15) - 1))
        a[1:i] = a[1:i] + ((k * a[i - 1:0:-1]) >> 15)
        a[i] = k
        err = (err * ((1 << 15) - ((k * k) >> 15))) >> 15
        if err <= 0:
            break
    bw = 1 << 15                                                                   # 帯域拡張 0.998^i (反復乗算、Q15)
    for i in range(1, order + 1):
        bw = (bw * 32702) >> 15
        a[i] = (a[i] * bw) >> 15
    return a


def extrapolate(hist, n, order):
    hist = np.asarray(hist, np.int64)
    if len(hist) <= order:
        return np.zeros(n, np.int64)
    a = lpc(hist, order)
    buf = list(int(v) for v in hist[-order:])
    out = np.empty(n, np.int64)
    coef = [int(v) for v in a[1:]]
    for i in range(n):
        acc = 0
        for j, c in enumerate(coef):
            acc += c * buf[-1 - j]
        v = int(saturate_bits(np.array([-(acc >> 15)]), PCM_BITS)[0])
        out[i] = v
        buf.append(v)
        buf.pop(0)
    return out


def conceal(y, valid, fs, order=16, hist_len=128, hold_ms=10, fade_ms=20, xfade=16):
    """y: (n, ch) の整数、valid: (n,) bool → 欠落区間を埋めた y"""
    out = np.asarray(y, np.int64).copy()
    out[~valid] = 0
    hold = fs * hold_ms // 1000
    fade = max(fs * fade_ms // 1000, 1)
    n = len(y)
    i = 0
    while i < n:
        if valid[i]:
            i += 1
            continue
        j = i
        while j < n and not valid[j]:
            j += 1
        L = j - i
        k = min(xfade, n - j)
        t = np.arange(L + k)
        g = np.clip((1 << 15) - (((t - hold) << 15) // fade), 0, 1 << 15)
        w = (np.arange(1, k + 1) << 15) // (k + 1)
        for c in range(y.shape[1]):
            pred = (extrapolate(out[max(0, i - hist_len):i, c], L + k, order) * g) >> 15
            out[i:j, c] = pred[:L]
            if k:
                out[j:j + k, c] = (w * out[j:j + k, c] + ((1 << 15) - w) * pred[L:] + (1 << 14)) >> 15
        i = j
    return out


def crossfade_switch(y, patterns, block, order=16, hist_len=128, xfade=16):
    """
    情報のある (系統, 成分, 帯域) の組が変わったブロックの先頭 xfade サンプルを、直前の出力の LPC 外挿から
    新しい出力へクロスフェードでつなぐ。主系が落ちて副系だけになる、高域CRCが不一致で高域が消える、などの
    切り替えで、波形の段差 (インパルス) が出るのを抑える。先読みを使わないので遅延は増えない。
    y: (n, ch) の整数。patterns: ブロックごとの組 (全て届かないブロックは all-False)。どちらも届くブロックだけ対象。
    """
    out = np.asarray(y, np.int64).copy()
    nb = min(len(patterns), len(y) // block)
    for i in range(1, nb):
        if patterns[i] != patterns[i - 1] and any(patterns[i]) and any(patterns[i - 1]):
            s = i * block
            k = min(xfade, len(y) - s)
            w = (np.arange(1, k + 1) << 15) // (k + 1)
            for c in range(y.shape[1]):
                pred = extrapolate(out[max(0, s - hist_len):s, c], k, order)
                out[s:s + k, c] = (w * out[s:s + k, c] + ((1 << 15) - w) * pred + (1 << 14)) >> 15
    return out
