#!/usr/bin/env python3
"""Reproducible static multipath benchmark on local, untracked lossless WAVs.

Example:
  python tools/eval_ghost.py --seconds 5 --cn0 66,80 --workers 3 \
      --json docs/results/ghost_eval.json

The first 100 frames (0.2 s) calibrate the causal static-channel equalizer.
Only later samples are scored. Symbol timing and carrier recovery remain ideal.
"""
import argparse
import json
import os
import sys
from concurrent.futures import ProcessPoolExecutor, as_completed

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "tools"))

from gracefm import channel, metrics, wavio  # noqa: E402
from gracefm.analog_fm import AnalogFM  # noqa: E402
from gracefm.equalizer import equalize_static, through_matched_channel  # noqa: E402
from gracefm.profiles import PROFILES  # noqa: E402
from gracefm.txrx import Transmitter, receive  # noqa: E402
from eval_lossless_benchmark import prepare  # noqa: E402

MAIN, SUB = "B200M", "SUB50M"
SCENARIOS = (
    ("none", None),
    ("echo_1us_m10", (1e-6, -10.0, np.pi / 3)),
    ("echo_2us_m10", (2e-6, -10.0, np.pi / 3)),
    ("echo_5us_m10", (5e-6, -10.0, np.pi / 3)),
    ("echo_5us_m20", (5e-6, -20.0, np.pi / 3)),
    ("echo_10us_m10", (10e-6, -10.0, np.pi / 3)),
    ("echo_5us_m3_pi", (5e-6, -3.0, np.pi)),
    ("echo_1us_m3_pi", (1e-6, -3.0, np.pi)),
)


def score(api, x, y, stats, start, end):
    ref, deg = x[start:end, 0], y[start:end].mean(axis=1)
    snr = float(metrics.snr_db(ref, deg))
    vr = wavio.resample(ref, 32000, 48000)
    vd = wavio.resample(deg, 32000, 48000)
    mos = float(api.measure_from_arrays(vr, vd, sample_rate=48000).moslqo)
    if "vA" in stats:
        plc = 100 * float(np.mean(~(stats["vA"][start:end] | stats["vB"][start:end])))
    else:
        plc = None
    return dict(snr_db=round(snr, 2), visqol_moslqo=round(mos, 3),
                plc_percent=None if plc is None else round(plc, 3))


def material_job(entry, seconds, strengths, scenarios, spacing_hz, training_frames,
                 taps, lookahead, decision_passes):
    from visqol import VisqolApi

    pm, ps = PROFILES[MAIN], PROFILES[SUB]
    warmup_seconds = training_frames * pm.block / pm.fs
    x = prepare(entry, seconds + warmup_seconds)
    start = training_frames * pm.block
    end = start + round(seconds * pm.fs)
    off = pm.block // 2
    fm = AnalogFM(x[:, 0], pm.fs)
    frames_main = Transmitter(pm, 0, 0).run(x)
    frames_sub = Transmitter(ps, 1, off).run(x)
    api = VisqolApi()
    api.create(mode="audio")
    out = []
    for cn0 in strengths:
        esm = cn0 + 10 * np.log10(0.5) - 10 * np.log10(channel.symbol_rate(pm))
        ess = cn0 + 10 * np.log10(0.5) - 10 * np.log10(channel.symbol_rate(ps))
        for scenario, path in scenarios:
            paths = () if path is None else (path,)
            ra, _ = through_matched_channel(frames_main, pm, esm, paths, seed=1)
            rb, _ = through_matched_channel(frames_sub, ps, ess, paths, spacing_hz, seed=2)
            eq_a, diag_a = equalize_static(ra, pm, 0, training_frames, taps, lookahead, decision_passes)
            eq_b, diag_b = equalize_static(rb, ps, 1, training_frames, taps, lookahead, decision_passes)
            for method, a, b in (("GraceFM unequalized", ra, rb), ("GraceFM equalized", eq_a, eq_b)):
                y, st = receive(pm, list(a), list(b), len(x), off, profile_b=ps, return_streams=True)
                row = dict(material=entry["name"], cn0_db_hz=cn0, scenario=scenario, method=method,
                           **score(api, x, y, st, start, end))
                if method == "GraceFM equalized":
                    row["main_lookahead_symbols"] = diag_a["lookahead_symbols"]
                    row["sub_lookahead_symbols"] = diag_b["lookahead_symbols"]
                    row["main_residual_power"] = round(diag_a["residual_power"], 7)
                    row["sub_residual_power"] = round(diag_b["residual_power"], 7)
                out.append(row)
            ghost = None if path is None else [path]
            mono = fm.receive(cn0, np.random.default_rng(1), ghost=ghost)
            yfm = np.repeat(mono[:, None], 2, axis=1)
            out.append(dict(material=entry["name"], cn0_db_hz=cn0, scenario=scenario, method="FM",
                            **score(api, x, yfm, {}, start, end)))
            print(f"{entry['name']} {cn0} {scenario}: "
                  f"FM {out[-1]['snr_db']:.1f}, no-EQ {out[-3]['snr_db']:.1f}, "
                  f"EQ {out[-2]['snr_db']:.1f} dB", flush=True)
    return out


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seconds", type=float, default=5.0)
    parser.add_argument("--cn0", default="66,80")
    parser.add_argument("--scenarios", default="all", help="comma-separated names or all")
    parser.add_argument("--frequency-spacing-hz", type=float, default=2.1e6)
    parser.add_argument("--training-frames", type=int, default=100)
    parser.add_argument("--equalizer-taps", type=int, default=11)
    parser.add_argument("--lookahead", type=int, default=4)
    parser.add_argument("--decision-passes", type=int, default=2)
    parser.add_argument("--workers", type=int, default=3)
    parser.add_argument("--json", default=os.path.join(ROOT, "docs/results/ghost_eval.json"))
    args = parser.parse_args()
    if args.seconds < 1 or args.workers < 1 or args.training_frames < 1:
        parser.error("seconds, workers, training-frames must be positive")
    strengths = [float(x) for x in args.cn0.split(",")]
    allowed = {name: path for name, path in SCENARIOS}
    names = list(allowed) if args.scenarios == "all" else args.scenarios.split(",")
    if any(name not in allowed for name in names):
        parser.error("unknown scenario")
    scenarios = [(name, allowed[name]) for name in names]
    with open(os.path.join(ROOT, "eval_audio/lossless/manifest.json"), encoding="utf-8") as source:
        entries = json.load(source)["sources"]
    rows = []
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        futures = [pool.submit(material_job, entry, args.seconds, strengths, scenarios,
                               args.frequency_spacing_hz, args.training_frames,
                               args.equalizer_taps, args.lookahead, args.decision_passes) for entry in entries]
        for future in as_completed(futures):
            rows.extend(future.result())
    rows.sort(key=lambda r: (r["material"], r["cn0_db_hz"], r["scenario"], r["method"]))
    result = dict(main_profile=MAIN, sub_profile=SUB, source_type="local untracked lossless PCM WAV",
                  sources=entries, sample_rate_hz=32000, seconds_scored=args.seconds,
                  training_frames=args.training_frames,
                  calibration_seconds=args.training_frames * PROFILES[MAIN].block / PROFILES[MAIN].fs,
                  frequency_spacing_hz=args.frequency_spacing_hz,
                  equalizer_taps=args.equalizer_taps, max_lookahead=args.lookahead,
                  decision_passes=args.decision_passes,
                  cn0_db_hz=strengths,
                  scenarios=[dict(name=name, path=None if path is None else
                                  dict(delay_us=path[0] * 1e6, relative_db=path[1], phase_rad=path[2]))
                             for name, path in scenarios],
                  assumptions="Ideal symbol timing/carrier recovery; static one-echo channel; "
                              "calibration from preceding frames; same direct-path C/N0 and total RF power; "
                              "secondary phase = main phase - 2*pi*frequency_spacing*delay.",
                  rows=rows)
    with open(args.json, "w", encoding="utf-8") as dest:
        json.dump(result, dest, ensure_ascii=False, indent=2, allow_nan=False)
        dest.write("\n")


if __name__ == "__main__":
    main()
