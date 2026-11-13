#!/usr/bin/env python3
"""
整数実装の定数表 (gracefm/tables.py) を作る。設計時に一度だけ実行する道具で、浮動小数点を使う。
出力された表は整数で、ハードウェアでは ROM になる。

  python tools/gen/gen_tables.py
"""
import argparse
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def hann128_q15():
    """np.hanning(128) (Q15)"""
    n = 128
    return [round(32768 * 0.5 * (1 - math.cos(2 * math.pi * i / (n - 1)))) for i in range(n)]


def resample_3_2_q16(taps=95, beta=7.0):
    """32 kHz → 48 kHz (3/2) の FIR。96 kHz で動く線形位相、カットオフ 16 kHz、Kaiser 窓、利得 3 (Q16)"""
    from scipy.signal import firwin
    return [round(v * 3 * 65536) for v in firwin(taps, 16000, window=("kaiser", beta), fs=96000, scale=False)]


def iir_sos_q16(fs_hz, cutoff_hz=4000, order=4):
    """因果の Butterworth (低域通過) を 2 次の区間に分けた係数を Q16 の整数にする。区間ごとの (b0_q, a1_q, a2_q)。
    b0 = b0_q / 2^16、a1 = a1_q / 2^16、a2 = a2_q / 2^16 (a0 = 1)。どの係数も符号つき 18 bit (|c| < 2^17) に収まる。
    低域通過の区間は b1 = 2·b0、b2 = b0 が厳密に成り立つので、b1 と b2 は持たない (iir.py)。"""
    from scipy.signal import butter
    sos = butter(order, cutoff_hz, fs=fs_hz, output="sos")
    out = []
    for s in sos:
        assert s[1] == 2 * s[0] and s[2] == s[0] and s[3] == 1, "low-pass Butterworth biquad expected"
        q = tuple(round(float(c) * (1 << 16)) for c in (s[0], s[4], s[5]))
        assert all(abs(v) < (1 << 17) for v in q), q
        out.append(q)
    return tuple(out)


def main():
    out = ['"""整数実装の定数表。tools/gen/gen_tables.py が作る (手で書き換えない)。ハードウェアでは ROM になる。"""', '']
    for name, tab, doc in (
            ("HANN128_Q15", hann128_q15(), "ハン窓 128 点 (Q15)"),
            ("RESAMPLE_3_2_Q16", resample_3_2_q16(), "32 kHz 系の 96 kHz → 48 kHz のフィルタ (3 倍のゼロ挿入のあと。95 タップ、Kaiser 7、カットオフ 16 kHz、Q16)")):
        out.append(f"# {doc}")
        out.append(f"{name} = (")
        for i in range(0, len(tab), 12):
            out.append("    " + ", ".join(str(v) for v in tab[i:i + 12]) + ",")
        out.append(")")
        out.append("")
    for name, fs_hz in (("ALT_IIR_32K_Q16", 32000), ("ALT_IIR_48K_Q16", 48000)):
        out.append("# 欠落・高域欠落のブロックで出力を切り替える先の IIR (因果の Butterworth 4 次、4 kHz)。区間ごとの (b0, a1, a2)、Q16 (符号つき 18 bit)、a0 = 1。b1 = 2·b0、b2 = b0")
        out.append(f"{name} = (")
        for sec in iir_sos_q16(fs_hz):
            out.append("    (" + ", ".join(str(v) for v in sec) + "),")
        out.append(")")
        out.append("")
    (ROOT / "gracefm" / "tables.py").write_text("\n".join(out))


if __name__ == "__main__":
    argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter).parse_args()
    main()
