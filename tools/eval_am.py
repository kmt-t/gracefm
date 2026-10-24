#!/usr/bin/env python3
"""
アナログAM (中波) との比較: 同じ受信電力 (C/N0) での波形SNR [dB] / BandMetric。

  python tools/eval_am.py --json docs/results/am_eval.json

素材は samples/fishin__32k__reference.flac・vibeace__32k__reference.flac の先頭5秒 (tools/eval_final.py と同じ)。
FM と放送構成の値は docs/results/final_eval.json を参照 (SPEC 5.2節)。
"""
import argparse
import json
import os
import sys

import numpy as np

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
sys.path.insert(0, ROOT)

from gracefm import metrics, wavio  # noqa: E402
from gracefm.analog_am import AnalogAM  # noqa: E402


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--seconds", type=float, default=5.0)
    ap.add_argument("--cn0", default="54,57,60,63,66,70,75,80")
    ap.add_argument("--json")
    args = ap.parse_args()
    out = {}
    for mat in ("fishin", "vibeace"):
        x, fs = wavio.read(os.path.join(ROOT, "samples", f"{mat}__32k__reference.flac"))
        x = x[: int(args.seconds * fs)]
        bm = metrics.BandMetric(x, fs)
        am = AnalogAM(x[:, 0], fs)
        res = {}
        for c in map(float, args.cn0.split(",")):
            y = am.receive(c, np.random.default_rng(1))
            Y = np.stack([y, y], axis=1)
            res[f"{c:g}"] = (round(metrics.snr_db(x, Y), 2), round(bm(Y - x), 2))
        y = am.gain * am._rx(am.tx.astype(complex))
        Y = np.stack([y, y], axis=1)
        res["雑音なし"] = (round(metrics.snr_db(x, Y), 2), round(bm(Y - x), 2))
        out[mat] = res
        print(mat, " | ".join(f"C/N0 {k}: {v[0]:.1f}dB / {v[1]:.1f}" for k, v in res.items()))
    if args.json:
        with open(args.json, "w") as f:
            json.dump(out, f, ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
