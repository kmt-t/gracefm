#!/usr/bin/env python3
"""
整数実装の定数表 (gracefm/tables.py) を作る。設計時に一度だけ実行する道具で、浮動小数点を使う。
出力された表は整数で、ハードウェアでは ROM になる。

  python tools/gen/gen_tables.py
"""
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def sigmoid_q15(llr_bits=8, llr_frac=2):
    """整数 LLR (正 = 0 らしい) → ビットが 1 である確率 (Q15)。LLR の実数値 = 整数 / 2^llr_frac"""
    lim = (1 << (llr_bits - 1)) - 1
    return [round(32768 / (1 + math.exp(l / (1 << llr_frac)))) for l in range(-lim, lim + 1)]


def log2_frac_q8():
    """x = 1 + i/256 (i = 0..255) の log2(x) (Q8)"""
    return [round(256 * math.log2(1 + i / 256)) for i in range(256)]


def pow2_neg_q15():
    """2^(-i/16) (Q15), i = 0..15"""
    return [round(32768 * 2 ** (-i / 16)) for i in range(16)]


def hann128_q15():
    """np.hanning(128) (Q15)"""
    n = 128
    return [round(32768 * 0.5 * (1 - math.cos(2 * math.pi * i / (n - 1)))) for i in range(n)]


def lpc_bandwidth_q15(order=16):
    """0.998^i (Q15), i = 0..order"""
    return [round(32768 * 0.998 ** i) for i in range(order + 1)]


def lanczos_q16(oversample=4, a=8):
    """Lanczos 補間核 (長さ 2·a·oversample + 1、Q16)"""
    import numpy as np
    n = np.arange(-a * oversample, a * oversample + 1) / oversample
    return [round(v * 65536) for v in np.sinc(n) * np.sinc(n / a)]


def lpf_q17(taps=511, cutoff_hz=0.98 * 32000 / 2, fs_hz=32000 * 4):
    """Kaiser(9) 窓の線形位相 LPF (Q17)。fs=32 kHz の 4 倍レート。48 kHz の 4 倍レートは cutoff が異なる"""
    from scipy.signal import firwin
    return [round(v * 131072) for v in firwin(taps, cutoff_hz, window=("kaiser", 9.0), fs=fs_hz)]


def resample_q16(up, down):
    """resample_poly の既定フィルタ (Kaiser 9、長さ 2·10·max(up, down) + 1、利得 up) (Q16)"""
    from scipy.signal import firwin
    half = 10 * max(up, down)
    return [round(v * up * 65536) for v in firwin(2 * half + 1, 1.0 / max(up, down), window=("kaiser", 9.0))]


IIR_SCALE_MAX = 5       # b0 の小数の位を増やす上限 (フィードバックの積を 48 bit に収めるため)


def iir_sos_q16(fs_hz, cutoff_hz=4000, order=4):
    """因果の Butterworth (低域通過) を 2 次の区間に分けた係数を整数にする。区間ごとの (b0_q, s, a1_q, a2_q)。
    b0 = b0_q / 2^(16+s)、a1 = a1_q / 2^16、a2 = a2_q / 2^16 (a0 = 1)。
    低域通過の区間は b1 = 2·b0、b2 = b0 が厳密に成り立つので、b1 と b2 は持たない (iir.py)。
    s は、b0 の精度を上げるための小数の位の増分 (0 から IIR_SCALE_MAX まで、b0_q が 18 bit 符号つきに収まる最大)。
    a1、a2 は Q16 のまま (|a| < 2)。どの係数も 18 bit 符号つきに収める。"""
    from scipy.signal import butter
    sos = butter(order, cutoff_hz, fs=fs_hz, output="sos")
    out = []
    for s in sos:
        assert s[1] == 2 * s[0] and s[2] == s[0] and s[3] == 1, "low-pass Butterworth biquad expected"
        shift = 0
        while shift < IIR_SCALE_MAX and abs(s[0]) * (1 << (16 + shift + 1)) < (1 << 17):
            shift += 1
        b0_q = round(float(s[0]) * (1 << (16 + shift)))
        a1_q, a2_q = round(float(s[4]) * (1 << 16)), round(float(s[5]) * (1 << 16))
        assert all(abs(v) < (1 << 17) for v in (b0_q, a1_q, a2_q)), (b0_q, a1_q, a2_q)
        out.append((b0_q, shift, a1_q, a2_q))
    return tuple(out)


def main():
    out = ['"""整数実装の定数表。tools/gen/gen_tables.py が作る (手で書き換えない)。ハードウェアでは ROM になる。"""', '']
    for name, tab, doc in (
            ("HANN128_Q15", hann128_q15(), "ハン窓 128 点 (Q15)"),
            ("LANCZOS_Q16", lanczos_q16(), "Lanczos 補間核 (4 倍、a = 8、長さ 65、Q16)"),
            ("LPF_32K_Q17", lpf_q17(), "32 kHz 系の 4 倍レートの LPF (Kaiser 9、511 タップ、通過域端 0.98 × 16 kHz、Q17)"),
            ("LPF_48K_Q17", lpf_q17(cutoff_hz=0.98 * 48000 / 2, fs_hz=48000 * 4), "48 kHz 系の 4 倍レートの LPF (同、通過域端 0.98 × 24 kHz、Q17)"),
            ("RESAMPLE_3_8_Q16", resample_q16(3, 8), "32 kHz 系の 128 kHz → 48 kHz (3/8) のフィルタ (161 タップ、Q16)"),
            ("RESAMPLE_1_4_Q16", resample_q16(1, 4), "48 kHz 系の 192 kHz → 48 kHz (1/4) のフィルタ (81 タップ、Q16)")):
        out.append(f"# {doc}")
        out.append(f"{name} = (")
        for i in range(0, len(tab), 12):
            out.append("    " + ", ".join(str(v) for v in tab[i:i + 12]) + ",")
        out.append(")")
        out.append("")
    for name, fs_hz in (("ALT_IIR_32K_Q16", 32000), ("ALT_IIR_48K_Q16", 48000)):
        out.append("# 欠落・高域欠落のブロックで出力を切り替える先の IIR (因果の Butterworth 4 次、4 kHz)。区間ごとの (b0_q, s, a1_q, a2_q)。b0 = b0_q / 2^(16+s)、a1, a2 は Q16、a0 = 1。b1 = 2·b0、b2 = b0")
        out.append(f"{name} = (")
        for sec in iir_sos_q16(fs_hz):
            out.append("    (" + ", ".join(str(v) for v in sec) + "),")
        out.append(")")
        out.append("")
    (ROOT / "gracefm" / "tables.py").write_text("\n".join(out))


if __name__ == "__main__":
    main()
