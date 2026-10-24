#!/usr/bin/env python3
"""
歪み率の比較: 正弦波を通して THD と THD+N を測る (アナログFM、コーデックだけ、最終構成の送受信)。

  python tools/eval_distortion.py --json docs/results/distortion.json

正弦波は −6dBFS (振幅 0.5)、100Hz・1kHz・5kHz、各 1.2秒 (前後 0.1秒は除く)。32kHz。
THD  = 高調波 (15kHz まで) の電力の平方根 / 基本波の振幅 [%]
THD+N = 20Hz〜15kHz の基本波以外の全電力の平方根 / 基本波の振幅 [%] (雑音も含む)
FM はモノラル、偏移 ±75kHz (正弦波のピークで 100% 変調)。ゴーストは反射波 1本 (遅れ、強さ、位相 60°)。
この方式の通信路は白色雑音のみ。室内5mでは反射の遅れがシンボル長より十分短い。
放送距離のゴーストは等化が前提だが、等化が未実装のため測っていない（制約は SPEC 6節）。
"""
import argparse
import json
import os
import sys

import numpy as np

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from gracefm import channel, metrics  # noqa: E402
from gracefm.analog_fm import AnalogFM  # noqa: E402
from gracefm.profiles import PROFILES  # noqa: E402
from make_samples import codec  # noqa: E402

FS = 32000


def tone(f0, amp=0.5, dur=1.2):
    t = np.arange(int(dur * FS)) / FS
    s = amp * np.sin(2 * np.pi * f0 * t)
    return np.stack([s, s], axis=1)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--json")
    args = ap.parse_args()
    out = {}
    for f0 in (100.0, 1000.0, 5000.0):
        x = tone(f0)
        rows = {}
        fm = AnalogFM(x[:, 0], FS)
        for cn0 in (80, 66):
            rows[f"FM C/N0 {cn0}dB-Hz"] = fm.receive(cn0, np.random.default_rng(1))
        for dly, rel in ((5e-6, -10), (10e-6, -10), (10e-6, -6), (20e-6, -6)):
            rows[f"FM C/N0 80dB-Hz ゴースト {dly * 1e6:.0f}µs {rel}dB"] = fm.receive(
                80, np.random.default_rng(1), ghost=[(dly, rel, np.pi / 3)])
        for name in ("B200M", "B200MH"):
            rows[f"{name} コーデックだけ"] = codec(x, PROFILES[name])[:, 0]
        for cn0 in (80, 66, 60):
            y, st, es = channel.link(x, "B200MH", cn0, sub="S50M", power_main=0.5, seed=1)
            rows[f"放送 B200MH+S50M C/N0 {cn0}dB-Hz"] = y[:, 0]
        res = {}
        for k, y in rows.items():
            t, tn = metrics.thd(y, FS, f0)
            res[k] = (round(t, 4), round(tn, 4))
            print(f"{f0:6.0f}Hz  {k:42s} THD {t:8.4f}% ({20 * np.log10(t / 100):6.1f}dB)   "
                  f"THD+N {tn:8.4f}% ({20 * np.log10(tn / 100):6.1f}dB)", flush=True)
        out[f"{f0:.0f}Hz"] = res
    if args.json:
        with open(args.json, "w") as f:
            json.dump(out, f, ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
