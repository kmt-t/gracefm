#!/usr/bin/env python3
"""同じ原音・C/N0 で波形SNRと ViSQOL Audio MOS-LQO を比較する。

  python tools/eval_perceptual.py --json docs/results/perceptual_eval.json
  python tools/eval_perceptual.py --materials fishin --cn0 60 --channels awgn

音楽素材は samples/*__32k__reference.flac の10秒全体（既定）。評価する通信路は
tools/eval_final.py と同じ同期済みシンボル列のモデル。ViSQOL は
32kHz の原音と受信音を共に48kHzに再標本化し、モノラルにして Audio mode で測る。
MOS-LQO は予測値であり、実際の聴取試験の MOS ではない。
"""
import argparse
import json
import os
import sys
from concurrent.futures import ProcessPoolExecutor

import numpy as np

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
sys.path.insert(0, ROOT)

from gracefm import channel, metrics, wavio  # noqa: E402
from gracefm.analog_am import AnalogAM  # noqa: E402
from gracefm.analog_fm import AnalogFM  # noqa: E402

METHODS = {
    "AM": None,
    "FM": None,
    "B200MH": dict(main="B200MH"),
    "GraceFM": dict(main="B200MH", sub="SUB50M", power_main=0.5),
    "GraceFM75": dict(main="B200MH", sub="SUB50M", power_main=0.75),
}
DEFAULT_METHODS = "AM,FM,GraceFM"


def parse_csv(text, convert=str):
    return [convert(part.strip()) for part in text.split(",") if part.strip()]


def scenarios(materials, cn0s, nonawgn_cn0s, channels, methods, seconds):
    for material in materials:
        for kind in channels:
            strengths = cn0s if kind == "awgn" else nonawgn_cn0s
            seeds = (1, 2) if kind == "rayleigh" else (1,)
            for cn0 in strengths:
                for seed in seeds:
                    for method in methods:
                        if method == "AM" and kind != "awgn":
                            continue  # AM のフェージング/選択的減衰モデルは未実装
                        yield (material, kind, cn0, seed, seconds, method)


def job(args):
    material, kind, cn0, seed, seconds, method = args
    from visqol import VisqolApi

    x, fs = wavio.read(os.path.join(ROOT, "samples", f"{material}__32k__reference.flac"))
    x = x[: int(seconds * fs)]
    if fs != 32000 or len(x) != int(seconds * fs):
        raise ValueError(f"{material}: 32kHz、{seconds:g}秒以上の原音が必要")
    if method == "AM":
        y1 = AnalogAM(x[:, 0], fs).receive(cn0, np.random.default_rng(seed))
        y = np.repeat(y1[:, None], 2, axis=1)
        plc = 0.0
    elif method == "FM":
        gains = None
        if kind != "awgn":
            gains = channel.fading_gains(int(np.ceil(len(x) / 64)), kind, np.random.default_rng(seed + 100))
        y1 = AnalogFM(x[:, 0], fs).receive(cn0, np.random.default_rng(seed), gains)
        y = np.repeat(y1[:, None], 2, axis=1)
        plc = 0.0
    else:
        cfg = METHODS[method]
        y, state, _ = channel.link(x, cfg["main"], cn0, sub=cfg.get("sub"),
                                   power_main=cfg.get("power_main", 0.5),
                                   kind_main=kind, kind_sub="awgn" if kind == "fade10" else kind,
                                   seed=seed)
        plc = 100 * state["plc_samples"] / len(x)

    # 波形SNRは元の32kHzで測る。ViSQOL Audio は48kHz・モノラルを要求する。
    snr = float(metrics.snr_db(x, y))
    ref48 = wavio.resample(x.mean(axis=1), fs, 48000)
    deg48 = wavio.resample(y.mean(axis=1), fs, 48000)
    api = VisqolApi()
    api.create(mode="audio")
    mos = float(api.measure_from_arrays(ref48, deg48, sample_rate=48000).moslqo)
    if not np.isfinite(mos):
        raise ValueError(f"{args}: ViSQOL が有限の値を返しませんでした")
    return dict(material=material, channel=kind, cn0_db_hz=cn0, seed=seed, method=method,
                snr_db=snr, visqol_moslqo=mos, plc_percent=plc)


def summarize(rows):
    grouped = {}
    for row in rows:
        key = (row["material"], row["channel"], row["cn0_db_hz"], row["method"])
        grouped.setdefault(key, []).append(row)
    return [dict(material=key[0], channel=key[1], cn0_db_hz=key[2], method=key[3], seeds=len(group),
                 snr_db=round(float(np.mean([r["snr_db"] for r in group])), 2),
                 visqol_moslqo=round(float(np.mean([r["visqol_moslqo"] for r in group])), 3),
                 plc_percent=round(float(np.mean([r["plc_percent"] for r in group])), 2))
            for key, group in grouped.items()]


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--materials", default="fishin,vibeace", help="32kHz モノラル音楽素材")
    ap.add_argument("--cn0", default="54,57,60,63,66,70,75,80", help="AWGN の C/N0 [dB-Hz]")
    ap.add_argument("--nonawgn-cn0", default="60,66", help="フェージングと主系 -10dB の C/N0 [dB-Hz]")
    ap.add_argument("--channels", default="awgn,rayleigh,fade10")
    ap.add_argument("--methods", default=DEFAULT_METHODS, help="選択肢: " + ",".join(METHODS))
    ap.add_argument("--seconds", type=float, default=10.0)
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--json", help="生データと平均を保存する JSON ファイル")
    args = ap.parse_args()
    materials = parse_csv(args.materials)
    cn0s = parse_csv(args.cn0, float)
    nonawgn_cn0s = parse_csv(args.nonawgn_cn0, float)
    channels = parse_csv(args.channels)
    methods = parse_csv(args.methods)
    if not materials or not cn0s or not methods or not channels:
        ap.error("materials、cn0、channels、methods は空にできません")
    if any(m not in ("fishin", "vibeace") for m in materials):
        ap.error("materials は fishin,vibeace から選んでください（FM/AM はモノラルのみ）")
    if any(c not in ("awgn", "rayleigh", "fade10") for c in channels):
        ap.error("channels は awgn,rayleigh,fade10 から選んでください")
    if any(m not in METHODS for m in methods):
        ap.error("methods に未定義の方式があります: " + ",".join(METHODS))
    if args.seconds < 3 or args.seconds > 10 or args.workers < 1:
        ap.error("seconds は 3〜10、workers は 1 以上にしてください")
    jobs = list(scenarios(materials, cn0s, nonawgn_cn0s, channels, methods, args.seconds))
    if not jobs:
        ap.error("評価する組み合わせがありません")
    rows = []
    with ProcessPoolExecutor(max_workers=args.workers) as executor:
        for row in executor.map(job, jobs):
            rows.append(row)
            print(f"{row['material']:8s} {row['channel']:8s} C/N0 {row['cn0_db_hz']:g} "
                  f"seed {row['seed']} {row['method']:9s} SNR {row['snr_db']:6.2f}dB "
                  f"ViSQOL {row['visqol_moslqo']:.3f} PLC {row['plc_percent']:.1f}%", flush=True)
    summary = summarize(rows)
    if args.json:
        result = dict(metric="ViSQOL Audio MOS-LQO", metric_implementation="visqol-python 3.8.0",
                      gracefm_main_profile="B200MH", gracefm_sub_profile="SUB50M",
                      reference="samples/{material}__32k__reference.flac", source_sample_rate_hz=32000,
                      visqol_sample_rate_hz=48000, seconds=args.seconds,
                      cn0_noise_bandwidth_hz=180000,
                      notes="FM/AM はモノラル。fade10 は GraceFM の主系と FM の搬送波のみ -10dB。"
                            "rayleigh は主系・副系で独立。AM は AWGN のみ。MOS-LQO は主観 MOS ではない。",
                      summary=summary, runs=rows)
        with open(args.json, "w") as f:
            json.dump(result, f, ensure_ascii=False, indent=2, allow_nan=False)
            f.write("\n")


if __name__ == "__main__":
    main()
