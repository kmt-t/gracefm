"""
欠落補間 (PLC)。届かなかった区間を LPC 外挿で埋め、hold_ms までは等倍、その後 fade_ms で 0 へ。
復帰時は xfade サンプルで外挿値から受信値へクロスフェードする。
"""
import numpy as np


def lpc(x, order):
    w = x * np.hanning(len(x))
    nfft = 1 << int(np.ceil(np.log2(2 * len(w))))
    r = np.fft.irfft(np.abs(np.fft.rfft(w, nfft)) ** 2)[: order + 1]
    a = np.zeros(order + 1)
    a[0] = 1.0
    if r[0] <= 1e-20:
        return a
    r[0] *= 1.0001
    err = r[0]
    for i in range(1, order + 1):
        acc = r[i] + np.dot(a[1:i], r[i - 1:0:-1])
        k = -acc / err
        a[1:i] = a[1:i] + k * a[i - 1:0:-1]
        a[i] = k
        err *= 1.0 - k * k
        if err <= 0:
            break
    a[1:] *= 0.998 ** np.arange(1, order + 1)
    return a


def extrapolate(hist, n, order):
    if len(hist) <= order:
        return np.zeros(n)
    a = lpc(hist, order)
    buf = list(hist[-order:])
    out = np.empty(n)
    coef = a[1:]
    for i in range(n):
        v = -np.dot(coef, buf[::-1])
        out[i] = v
        buf.append(v)
        buf.pop(0)
    return out


def conceal(y, valid, fs, order=16, hist_len=128, hold_ms=10.0, fade_ms=20.0, xfade=16):
    """y: (n, ch), valid: (n,) bool → 欠落区間を埋めた y"""
    out = y.copy()
    out[~valid] = 0.0
    hold = int(fs * hold_ms / 1000)
    fade = max(int(fs * fade_ms / 1000), 1)
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
        g = np.clip(1.0 - (t - hold) / fade, 0.0, 1.0)
        w = np.linspace(0.0, 1.0, k + 2)[1:-1]
        for c in range(y.shape[1]):
            pred = extrapolate(out[max(0, i - hist_len):i, c], L + k, order) * g
            out[i:j, c] = pred[:L]
            if k:
                out[j:j + k, c] = w * out[j:j + k, c] + (1 - w) * pred[L:]
        i = j
    return out
