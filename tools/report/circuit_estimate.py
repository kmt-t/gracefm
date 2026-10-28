#!/usr/bin/env python3
"""
受信側の演算量とメモリを、処理ごとに数える (docs/COMPARISON.md の回路規模の節)。

  python tools/report/circuit_estimate.py

数えるもの: 乗算 (MAC)、加減算つきの比較選択 (ACS)、除算。式は各関数にある。プロファイルのレイアウト (Layout) と
パラメータから出すので、プロファイルを変えれば数も変わる。幅は docs/FIXED.md の固定小数点 (データ 24 bit、係数 18 bit)。
DSP スライス数は、MAC/s ÷ (クロック × 稼働率) の下限で、クロックと稼働率は引数 (既定 100 MHz、100%) の仮定である。
論理 (LUT/FF) の数は、HDL を合成しないと出ないので見積もらない。

数えていないもの (設計がない): 同期 (シンボルタイミング、搬送波、AGC)、AD9363 とのインターフェースと、そのサンプルレート
(シンボルレートより高い固定のレートからのリサンプリング)、制御用 ARM のソフトウェア、暗号化 (AES-CTR)。
出力: docs/results/circuit_estimate.json
"""
import json
import math
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from gracefm import fec  # noqa: E402
from gracefm.channel import DEFAULT_SUB, symbol_rate  # noqa: E402
from gracefm.layout import Layout  # noqa: E402
from gracefm.modem import bits_per_symbol, n_symbols  # noqa: E402
from gracefm.postfilter import LANCZOS_A, LPF_TAPS, OUT_FS, OVERSAMPLE  # noqa: E402
from gracefm.profiles import PROFILES  # noqa: E402

CLOCK_HZ = 100e6
UTILIZATION = 1.0
DATA_BITS, COEF_BITS = 24, 18
EQ_TAPS = 11
LPC_ORDER, LPC_HIST = 16, 128
RESAMPLE_TAPS = 2 * 10 * 16 + 1                  # resample_poly の既定 (最大 16 で上下したとき)


def front_end(p):
    """1系統の受信 (RRC、等化、復調、ビタビ、仮数の軟判定) の1秒あたりの演算"""
    lay = Layout(p)
    fps = p.fs / p.block
    sym_rate = symbol_rate(p)
    digital = n_symbols(lay.n_tx, lay.n_strong, p.modulation)                       # デジタルシンボル数
    L = 2 if p.modulation == "qam16h" else 1
    stages = (lay.n_hdata + fec.K - 1) + ((lay.n_top + fec.K - 1) if lay.n_top else 0) \
        + ((lay.n_y + fec.K - 1) if lay.n_y else 0)
    return {
        "rrc_mac": 2 * p.pulse_span * 2 * sym_rate,                                # 2 sps、実係数 × (I, Q)
        "eq_mac": EQ_TAPS * 4 * sym_rate,                                          # 複素 FIR = 実 4 MAC
        "llr_mul": (2 * 2 * L + 2 + bits_per_symbol(p.modulation)) * digital * fps,  # 距離の二乗 + 分散 + LLR の尺度
        "viterbi_acs": fec.NSTATE * stages * fps,
        "soft_mantissa_mul": 4 * lay.n_coef_bits * fps,                            # 期待値 1 + 分散 2 + 係数の尺度 1
    }, lay


def back_end(p, two_streams):
    """合成以降 (Haar 合成、融合、補間、ポストフィルタ) の1秒あたりの演算。主系のブロック格子で数える"""
    fps = p.fs / p.block
    outs = sum(2 * p.ncoef(k) for k in range(1, p.nbands))                         # Haar 合成の出力数 (1成分)
    haar = 2 * outs                                                                # 積 p·C と q·C を共有して 1 組 2 乗算 ≒ 出力数
    haar_per_block = 2 * haar                                                      # M と S
    fuse_per_block = (4 + 2) * haar + 2 * sum(p.ncoef(k) for k in range(p.nbands)) * 2 if two_streams else 0
    lpc_block = 2 * (LPC_HIST + LPC_HIST * (LPC_ORDER + 1) // 2 + LPC_ORDER * LPC_ORDER
                     + LPC_ORDER * (p.block + 16))                                 # 窓 + 自己相関 + Levinson + 外挿 (成分ごと)
    lanczos = 2 * p.fs * (2 * LANCZOS_A * OVERSAMPLE // OVERSAMPLE) * OVERSAMPLE   # 8倍の各点が 2a 入力の和
    lpf_sequential = 2 * p.fs * OVERSAMPLE * LPF_TAPS                              # 定義どおり: 8倍レートの全点
    resample = 2 * OUT_FS * math.ceil(RESAMPLE_TAPS / 3)
    lpf_at_output = 2 * OUT_FS * LPF_TAPS // 2                                     # 出力点だけ、対称な係数の半分
    return {
        "haar_synthesis_mac": haar_per_block // 2 * fps,
        "fusion_mac": fuse_per_block * fps,
        "plc_worst_case_mac": lpc_block * fps,
        "postfilter_lanczos_mac": lanczos,
        "postfilter_lpf_sequential_mac": lpf_sequential,
        "postfilter_resample_mac": resample,
        "postfilter_lpf_at_output_points_mac": lpf_at_output,
    }


def memory_bits(p, lay, two_streams):
    nsym = n_symbols(lay.n_tx, lay.n_strong, p.modulation) + 16
    return {
        "symbol_buffer": nsym * 2 * DATA_BITS,
        "llr_buffer": lay.n_tx * 6,
        "viterbi_traceback": fec.NSTATE * max(lay.n_hdata, lay.n_top, lay.n_y) + 0,
        "coefficients": 2 * p.block * DATA_BITS,
        "output_double_buffer": 2 * p.block * 2 * DATA_BITS * (2 if two_streams else 1),
        "plc_history": LPC_HIST * 2 * DATA_BITS,
        "postfilter_delay_line": (LPF_TAPS // 2 + LANCZOS_A * 2) * 2 * DATA_BITS,
        "rom_coefficients": (LPF_TAPS // 2 + 1 + 129 + RESAMPLE_TAPS) * COEF_BITS + p.pulse_span * 2 * COEF_BITS,
    }


def estimate(name):
    p = PROFILES[name]
    sub = DEFAULT_SUB.get(name)
    fe, lay = front_end(p)
    systems = [fe] + ([front_end(PROFILES[sub])[0]] if sub else [])
    totals = {}
    for s in systems:
        for k, v in s.items():
            totals[k] = totals.get(k, 0) + v
    be = back_end(p, bool(sub))
    mac = sum(v for k, v in {**totals, **be}.items() if k.endswith("_mac") or k.endswith("_mul")) \
        - be["postfilter_lpf_sequential_mac"] - be["plc_worst_case_mac"]
    macs_min = mac                                                                 # 出力点だけで LPF を評価、補間なし
    mem = memory_bits(p, lay, bool(sub))
    return dict(name=name, sub=sub, front_end_per_s=totals, back_end_per_s=be, mac_per_s_restructured=macs_min,
                mac_per_s_sequential=macs_min - be["postfilter_lpf_at_output_points_mac"] + be["postfilter_lpf_sequential_mac"],
                plc_worst_case_mac_per_s=be["plc_worst_case_mac"],
                dsp_slices_min_restructured=math.ceil(macs_min / (CLOCK_HZ * UTILIZATION)),
                dsp_slices_min_restructured_with_plc=math.ceil((macs_min + be["plc_worst_case_mac"]) / (CLOCK_HZ * UTILIZATION)),
                memory_bits=mem, memory_total_bits=sum(mem.values()))


def main():
    rows = [estimate(n) for n in ("B200M", "B200", "M700M", "M700")]
    (ROOT / "docs/results/circuit_estimate.json").write_text(json.dumps(rows, ensure_ascii=False, indent=2) + "\n")
    for r in rows:
        print(r["name"], r["sub"], "MMAC/s restructured %.1f sequential %.1f plc %.1f" % (
            r["mac_per_s_restructured"] / 1e6, r["mac_per_s_sequential"] / 1e6, r["plc_worst_case_mac_per_s"] / 1e6),
            "ACS/s %.1fM" % (r["front_end_per_s"]["viterbi_acs"] / 1e6), "DSP>=", r["dsp_slices_min_restructured"],
            "mem %.0f kbit" % (r["memory_total_bits"] / 1e3))


if __name__ == "__main__":
    main()
