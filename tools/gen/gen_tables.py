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


def hann_2cos_q28(n=128):
    """ハン窓 (n 点) の漸化式 cos((k+1)θ) = 2cosθ · cos(kθ) - cos((k-1)θ) の定数 2cosθ (Q28)、θ = 2π/(n-1)"""
    return round(2 * math.cos(2 * math.pi / (n - 1)) * (1 << 28))


def lpc_bandwidth_q15(order=16):
    """0.998^i (Q15), i = 0..order"""
    return [round(32768 * 0.998 ** i) for i in range(order + 1)]


def lanczos_q16(oversample=8, a=8):
    """Lanczos 補間核 (長さ 2·a·oversample + 1、Q16)"""
    import numpy as np
    n = np.arange(-a * oversample, a * oversample + 1) / oversample
    return [int(round(v * 65536)) for v in np.sinc(n) * np.sinc(n / a)]


def lpf_q17(taps=1023, cutoff_hz=0.98 * 32000 / 2, fs_hz=32000 * 8):
    """Kaiser(9) 窓の線形位相 LPF (Q17)。fs=32 kHz の 8 倍レート。48 kHz の 8 倍レートは cutoff が異なる"""
    from scipy.signal import firwin
    return [int(round(v * 131072)) for v in firwin(taps, cutoff_hz, window=("kaiser", 9.0), fs=fs_hz)]


def resample_q16(up, down):
    """resample_poly の既定フィルタ (Kaiser 9、長さ 2·10·max(up, down) + 1、利得 up) (Q16)"""
    from scipy.signal import firwin
    half = 10 * max(up, down)
    return [int(round(v * up * 65536)) for v in firwin(2 * half + 1, 1.0 / max(up, down), window=("kaiser", 9.0))]


def main():
    out = ['"""整数実装の定数表。tools/gen/gen_tables.py が作る (手で書き換えない)。ハードウェアでは ROM になる。"""', '']
    for name, tab, doc in (
            ("LANCZOS_Q16", lanczos_q16(), "Lanczos 補間核 (8 倍、a = 8、長さ 129、Q16)"),
            ("LPF_32K_Q17", lpf_q17(), "32 kHz 系の 8 倍レートの LPF (Kaiser 9、1023 タップ、通過域端 0.98 × 16 kHz、Q17)"),
            ("LPF_48K_Q17", lpf_q17(cutoff_hz=0.98 * 48000 / 2, fs_hz=48000 * 8), "48 kHz 系の 8 倍レートの LPF (同、通過域端 0.98 × 24 kHz、Q17)"),
            ("RESAMPLE_3_16_Q16", resample_q16(3, 16), "32 kHz 系の 256 kHz → 48 kHz (3/16) のフィルタ (321 タップ、Q16)"),
            ("RESAMPLE_1_8_Q16", resample_q16(1, 8), "48 kHz 系の 384 kHz → 48 kHz (1/8) のフィルタ (161 タップ、Q16)")):
        out.append(f"# {doc}")
        out.append(f"{name} = (")
        for i in range(0, len(tab), 12):
            out.append("    " + ", ".join(str(v) for v in tab[i:i + 12]) + ",")
        out.append(")")
        out.append("")
    out.append("# ハン窓 (128 点) の漸化式の定数 2cos(2π/127) (Q28)")
    out.append(f"HANN_2COS_Q28 = {hann_2cos_q28()}")
    out.append("")
    (ROOT / "gracefm" / "tables.py").write_text("\n".join(out))


if __name__ == "__main__":
    main()
