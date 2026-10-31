"""出力段の切り替え先の因果 IIR (整数のみ)。区間 (biquad) を直接形 II の転置で直列に通す。
係数は tables.py の ALT_IIR_*_Q28 (Q28、a0 = 1)。状態と積は 64 bit 整数に収まる (PCM 24 bit の入力)。"""
import numpy as np

from .tables import ALT_IIR_32K_Q28, ALT_IIR_48K_Q28

Q = 28
HALF = 1 << (Q - 1)
PCM_MAX = (1 << 23) - 1
PCM_MIN = -(1 << 23)


def alt_sections(fs):
    """サンプリング周波数に対応する切り替え先の IIR の区間"""
    return ALT_IIR_32K_Q28 if fs == 32000 else ALT_IIR_48K_Q28


def iir_filter(x, sections):
    """x: (n, ch) の整数 (PCM の範囲)。区間の列 sections に通した (n, ch) の整数を返す (因果、遅延は群遅延の分だけ)。"""
    x = np.asarray(x, np.int64)
    n, ch = x.shape
    out = np.empty((n, ch), np.int64)
    states = [[np.zeros(ch, np.int64), np.zeros(ch, np.int64)] for _ in sections]   # (s1, s2) を区間ごとに
    coefs = [tuple(np.int64(c) for c in sec) for sec in sections]
    for k in range(n):
        v = x[k]
        for j, (b0, b1, b2, a1, a2) in enumerate(coefs):
            s = states[j]
            acc = b0 * v + s[0]                                # 2^Q 倍の尺度
            y = (acc + HALF) >> Q
            y = np.clip(y, PCM_MIN, PCM_MAX)
            s[0] = b1 * v - a1 * y + s[1]
            s[1] = b2 * v - a2 * y
            v = y
        out[k] = v
    return out


# 群遅延 (1 kHz で、32 kHz 系 3.26 サンプル、48 kHz 系 5.03 サンプル) を整数サンプルに丸めた遅延。出力全体をこの分だけ遅らせて揃える。
ALT_DELAY = {32000: 3, 48000: 5}


def apply_alt(y, quality, fs, block):
    """受信の出力 y (n, ch) に、欠落・高域欠落のブロック (quality が 1 か 2) だけ IIR の出力を切り替える。
    出力は ALT_DELAY サンプル遅れる (切り替えの有無によらず全体を揃える)。切り替えは 1 ms のクロスフェード。"""
    from .postfilter import select_by_quality
    y = np.asarray(y, np.int64)
    d = ALT_DELAY[fs]
    alt = iir_filter(y, alt_sections(fs))                    # 因果: 入力 y の位置に揃っている
    delayed = np.concatenate([np.zeros((d,) + y.shape[1:], np.int64), y[:len(y) - d]])
    return select_by_quality(delayed, alt, quality, block, use_alt=(1, 2), fade=fs // 1000)
