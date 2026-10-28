#!/usr/bin/env python3
"""
受信側の演算量とメモリを、処理ごとに数える (docs/COMPARISON.md の回路規模の節)。

  python tools/report/circuit_estimate.py

数えるもの: 乗算 (MAC)、加減算つきの比較選択 (ACS)、除算。式は各関数にある。プロファイルのレイアウト (Layout) と
パラメータから出すので、プロファイルを変えれば数も変わる。幅は docs/FIXED.md の固定小数点 (データ 24 bit、係数 18 bit)。
DSP スライス数は、MAC/s ÷ (クロック × 稼働率) の下限で、クロックと稼働率は引数 (既定 100 MHz、100%) の仮定である。
論理 (LUT/FF)・DSP・ブロック RAM は、HDL がないので、主な部品を RTL の構造として書き下したときの演算器とレジスタの幅から
積み上げた見積もりである (合成していない。制御の一部は仮定で、誤差は 0.5〜2 倍を見込む)。規則: N bit の加減算・比較・2:1 選択は N LUT、レジスタは N FF、小さな記憶 (1 kbit 以下) は 64 bit/LUT の
分散 RAM、それより大きい記憶は 18 kbit のブロック RAM 単位、25×18 以下の積和は DSP48E1 1個。

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
from gracefm.tables import LANCZOS_Q16, RESAMPLE_1_4_Q16, RESAMPLE_3_8_Q16  # noqa: E402
from gracefm.profiles import PROFILES  # noqa: E402

CLOCK_HZ = 100e6
UTILIZATION = 1.0
DATA_BITS, COEF_BITS = 24, 18
EQ_TAPS = 11
LPC_ORDER, LPC_HIST = 16, 128


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
    lanczos = 2 * p.fs * (2 * LANCZOS_A * OVERSAMPLE // OVERSAMPLE) * OVERSAMPLE   # オーバーサンプルの各点が 2a 入力の和
    lpf_sequential = 2 * p.fs * OVERSAMPLE * LPF_TAPS                              # 定義どおり: オーバーサンプル後のレートの全点
    up_f, kernel = (3, RESAMPLE_3_8_Q16) if p.fs == 32000 else (1, RESAMPLE_1_4_Q16)
    resample = 2 * OUT_FS * math.ceil(len(kernel) / up_f)
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
        "rom_coefficients": (LPF_TAPS // 2 + 1 + len(LANCZOS_Q16) + len(RESAMPLE_3_8_Q16 if p.fs == 32000 else RESAMPLE_1_4_Q16)) * COEF_BITS + p.pulse_span * 2 * COEF_BITS,
    }


# --- 論理の積み上げ (規則は冒頭) ---
# 各部品を、RTL に書いたときの演算器とレジスタの幅から数える。加減算・比較・選択は N bit で N LUT、
# 大きさの比較は N LUT、カウンタは N LUT + N FF。DSP48E1 の内側のレジスタ (入力、積、累積) は FF に数えない。
PRACTICAL_UTILIZATION = 0.5                      # DSP の稼働率の仮定 (パイプライン、メモリ帯域、同期の余裕)
SEQUENCER_LUT = SEQUENCER_FF = 60                # 機能ごとのループ (サンプル、ブロック、バッファの面) を回す制御の仮定。10 bit のカウンタ 3つ + 少しの状態
TOP_CONTROL_LUT = TOP_CONTROL_FF = 300           # 全体の状態機械 (フレームの取得、復号の順序、系統の切り替え) の仮定
BRAM18_BITS = 18 * 1024
LUTRAM_MAX_BITS = 1024
# Zynq-7010 (docs/SPEC.md 7.1)
ZYNQ_LUT, ZYNQ_FF, ZYNQ_DSP, ZYNQ_BRAM18 = 17600, 35200, 80, 120


def part(adders=(), compares=(), muxes=(), counters=(), regs=(), extra_lut=0, dsp=0, lutram_lut=0):
    """部品表: 幅のリストから LUT/FF を出す。adders = 加減算、compares = 比較、muxes = 2:1 選択、counters = カウンタ、regs = レジスタ"""
    lut = sum(adders) + sum(compares) + sum(muxes) + sum(counters) + extra_lut + lutram_lut
    ff = sum(counters) + sum(regs)
    return {"lut": lut, "ff": ff, "dsp": dsp}


def mac_engine():
    """1個の DSP48E1 を時分割する積和機 (24 bit データ × 18 bit 係数、48 bit 累積)。
    アドレスのカウンタ 10 bit、終了の比較 10 bit (2 つの 10 bit 値の一致 ≒ 4 LUT)、
    24 bit への飽和 (上位 25 bit が一致するかの検出 8 LUT + 24 bit の選択)、出力レジスタ 24 bit、状態 4 bit"""
    return part(counters=[10], compares=[4], extra_lut=8 + 3, muxes=[24], regs=[24, 4], dsp=1)


def viterbi_unit():
    """K=7 (133, 171)、軟判定の ACS を 1個、1サイクルに 1状態。経路メトリック 14 bit。
    期待符号の偶奇 4 LUT、枝メトリック 2つ (10 bit の加減算 2回ずつ)、候補の和 2つ (15 bit)、比較 15、選択 15、
    正規化の減算 14、最小値の比較と更新 14 + 14、読み出しのバンク選択 14 × 2、状態カウンタ 6、制御 10。
    経路メトリックの記憶は 64 × 14 bit を 2面 (ping-pong)、読み出し口が 2つなので 14 × 2面 × 2口 × 2 LUT (RAM64X1D)"""
    pm = 14
    lutram = pm * 2 * 2 * 2
    return part(adders=[10, 10, 10, 10, 15, 15, pm], compares=[15, pm], muxes=[15, pm, 2 * pm],
                counters=[6], regs=[pm, pm, pm, pm, 4], extra_lut=4 + 10, lutram_lut=lutram)


def traceback_unit():
    """判定ビットを 6 bit のポインタにシフトして状態を辿る (判定ビットの記憶は別にブロック RAM)"""
    return part(regs=[6 + 1])


def frame_control():
    """CRC12 (0x80F の1が5つ) と CRC10 (0x233 の1が5つ) の LFSR、PRBS の LFSR (排他的論理和 1 LUT)、
    索引のカウンタ 11 bit と末尾の比較 4 LUT"""
    return part(counters=[11], compares=[4], extra_lut=5 + 5 + 1, regs=[12, 10, 16])


def llr_unit():
    """軸ごとの max-log LLR: 距離 16 bit どうしの小さいほうを 2組 (比較 16 + 選択 16 を 2回)、差 17 bit、
    1/(2σ²) との乗算 (DSP 1個)、8 bit への飽和 10 LUT。レジスタは差の 17 bit と出力の 8 bit"""
    return part(compares=[16, 16], muxes=[16, 16], adders=[17], extra_lut=10, regs=[17, 8], dsp=1)


def divider_unit():
    """48 bit ÷ 24 bit の、1 bit/サイクルの除算: 被除数 48、剰余 25、商 48、段数カウンタ 6、状態 2。
    25 bit の比較・減算・剰余の選択"""
    return part(compares=[25], adders=[25], muxes=[25], counters=[6], regs=[48, 25, 48, 2])


def isqrt_unit():
    """48 bit の、1 bit/サイクルの平方根 (乗算なし): 被開平数・結果・ビット位置が各 48 bit。
    結果 + ビット位置の加算、比較、被開平数の減算、結果の選択"""
    return part(adders=[48, 48], compares=[48], muxes=[48], regs=[48, 48, 48, 2])


def solver_unit():
    """通信路推定と MMSE の重み (整数コレスキー): 積和機 + 除算器 + 平方根 + 逐次の制御"""
    parts = [mac_engine(), divider_unit(), isqrt_unit(), part(extra_lut=SEQUENCER_LUT, regs=[SEQUENCER_FF])]
    return {m: sum(x[m] for x in parts) for m in ("lut", "ff", "dsp")}


def index_rom_bits(lay):
    """配置の索引を全部 ROM に持つ場合の上限 (実際は規則的なので、カウンタで作る分だけ減る)"""
    entries = sum(v.size for k, v in vars(lay).items() if hasattr(v, "size") and not k.startswith("_seg") and v.size > 20)
    return entries * max(1, (lay.n_tx - 1).bit_length())


def place(bits):
    """記憶 bit 数 → (分散 RAM の LUT 数, ブロック RAM 18k の個数)"""
    if bits <= LUTRAM_MAX_BITS:
        return math.ceil(bits / 64), 0
    return 0, math.ceil(bits / BRAM18_BITS)


def logic_estimate(name):
    p = PROFILES[name]
    sub = DEFAULT_SUB.get(name)
    fe, lay = front_end(p)
    systems = [fe] + ([front_end(PROFILES[sub])[0]] if sub else [])
    be = back_end(p, bool(sub))
    rate = lambda *keys: sum(s[k] for s in systems for k in keys if k in s) + sum(be[k] for k in keys if k in be)
    cap = CLOCK_HZ * PRACTICAL_UTILIZATION
    mac_engines = {                                                                # 機能 → 必要な積和機の数
        "rrc": math.ceil(rate("rrc_mac") / cap),
        "equalizer": math.ceil(rate("eq_mac") / cap),
        "demod_soft": math.ceil(rate("llr_mul", "soft_mantissa_mul") / cap),
        "haar_fusion": math.ceil(rate("haar_synthesis_mac", "fusion_mac") / cap),
        "postfilter": math.ceil(rate("postfilter_lanczos_mac", "postfilter_lpf_at_output_points_mac", "postfilter_resample_mac") / cap),
        "plc": math.ceil(rate("plc_worst_case_mac") / cap),
    }
    unit = {m: v + (SEQUENCER_LUT if m == "lut" else SEQUENCER_FF if m == "ff" else 0) for m, v in mac_engine().items()}
    parts = {f"mac:{k}": {m: v * n for m, v in unit.items()} for k, n in mac_engines.items()}
    parts["viterbi"] = {m: v + t for m, v, t in ((m, viterbi_unit()[m], traceback_unit()[m]) for m in ("lut", "ff", "dsp"))}
    parts["frame_control"] = frame_control()
    parts["llr"] = llr_unit()
    parts["channel_solver"] = solver_unit()
    parts["top_control"] = part(extra_lut=TOP_CONTROL_LUT, regs=[TOP_CONTROL_FF])
    mem = memory_bits(p, lay, bool(sub))
    mem["index_rom_upper_bound"] = index_rom_bits(lay) + (index_rom_bits(Layout(PROFILES[sub])) if sub else 0)
    mem["solver_matrix"] = (2 * 11) ** 2 * 32                                      # 2n × 2n (n = 11)、32 bit
    lutram_lut = bram18 = 0
    for bits in mem.values():
        a, b = place(bits)
        lutram_lut += a
        bram18 += b
    parts["lutram"] = {"lut": lutram_lut, "ff": 0, "dsp": 0}                       # 1 kbit 以下の小さな記憶
    total = {m: sum(v[m] for v in parts.values()) for m in ("lut", "ff", "dsp")}
    total["bram18"] = bram18
    return dict(name=name, sub=sub, utilization=PRACTICAL_UTILIZATION, mac_engines=mac_engines, parts=parts,
                memory_bits=mem, total=total,
                fraction_of_zynq_7010=dict(lut=total["lut"] / ZYNQ_LUT, ff=total["ff"] / ZYNQ_FF,
                                           dsp=total["dsp"] / ZYNQ_DSP, bram18=total["bram18"] / ZYNQ_BRAM18))


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
    logic = [logic_estimate(n) for n in ("B200M", "B200", "M700M", "M700")]
    (ROOT / "docs/results/circuit_estimate.json").write_text(json.dumps(
        {"operations": rows, "logic": logic}, ensure_ascii=False, indent=2) + "\n")
    for r in logic:
        t = r["total"]
        print(r["name"], r["sub"], "LUT %d (%.0f%%) FF %d (%.0f%%) DSP %d BRAM18 %d (%.0f%%)" % (
            t["lut"], 100 * r["fraction_of_zynq_7010"]["lut"], t["ff"], 100 * r["fraction_of_zynq_7010"]["ff"],
            t["dsp"], t["bram18"], 100 * r["fraction_of_zynq_7010"]["bram18"]))
    for r in rows:
        print(r["name"], r["sub"], "MMAC/s restructured %.1f sequential %.1f plc %.1f" % (
            r["mac_per_s_restructured"] / 1e6, r["mac_per_s_sequential"] / 1e6, r["plc_worst_case_mac_per_s"] / 1e6),
            "ACS/s %.1fM" % (r["front_end_per_s"]["viterbi_acs"] / 1e6), "DSP>=", r["dsp_slices_min_restructured"],
            "mem %.0f kbit" % (r["memory_total_bits"] / 1e3))


if __name__ == "__main__":
    main()
