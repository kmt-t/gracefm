#!/usr/bin/env python3
"""Compare Haar and LeGall 5/3 (-L) profiles through the full receive path, on the repository's reference samples.

  python tools/eval/eval_legall.py --workers 6 --json docs/results/legall_link.json

Two conditions, with ideal synchronization:
  cn0:  main + default sub stream, AWGN at the given C/N0 on each.
  loss: main stream only at 80 dB-Hz, with independent random frame loss. Stresses the concealment.
"""
import argparse
import json
import os
import sys
from concurrent.futures import ProcessPoolExecutor, as_completed

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)

from gracefm import channel
from gracefm.encoder import Encoder
from gracefm.iir import ALT_DELAY
from gracefm.profiles import PROFILES
from gracefm.receiver import receive
from tools.common import metrics, wavio

MATERIALS = ("demo", "percussion", "piano")
BASES = ("B200M", "B200MY", "M700Y")
CN0 = (54, 57, 60, 66)
LOSS = (0.01, 0.05)
LOSS_CN0 = 80
LOSS_SEED = 5


def load(material, p):
    stereo = any(p.bits_s)
    form = "stereo" if stereo else "mono"
    x, fs = wavio.read(os.path.join(ROOT, "samples", f"{material}-{form}__{p.fs // 1000}k__reference.flac"))
    assert fs == p.fs
    return (x if stereo else np.repeat(x[:, :1], 2, axis=1)), stereo


def lossy(frames, loss, p, rng):
    esn0 = LOSS_CN0 - 10 * np.log10(channel.symbol_rate(p))
    return [None if rng.random() < loss else channel.adc(channel.awgn(f / float(1 << 22), esn0, rng)) for f in frames]


def score(x, y, p, stereo):
    """Returns (SNR dB, mean ViSQOL) against the reference, scored at 48 kHz like the other evaluations."""
    from visqol import VisqolApi

    api = VisqolApi()
    api.create(mode="audio")
    delay = ALT_DELAY[p.fs]
    n = len(y) - delay
    channels = 2 if stereo else 1
    ref, out = x[:n, :channels], wavio.from_pcm24(y)[delay:, :channels]
    ref48 = wavio.resample(ref, p.fs, 48000) if p.fs != 48000 else ref
    out48 = wavio.resample(out, p.fs, 48000) if p.fs != 48000 else out
    mos = [float(api.measure_from_arrays(ref48[:, c], out48[:, c], sample_rate=48000).moslqo) for c in range(channels)]
    return float(metrics.snr_db(ref, out)), float(np.mean(mos))


def run(task):
    material, base, suffix, mode, value = task
    p = PROFILES[base + suffix]
    x, stereo = load(material, p)
    xi = wavio.to_pcm24(x)
    if mode == "cn0":
        y, st, _ = channel.link(xi, p.name, value, seed=1)
    else:
        rng = np.random.default_rng(LOSS_SEED)
        y, st = receive(p, lossy(Encoder(p, 0, 0).run(xi), value, p, rng), None, len(xi), 0)
    snr, mos = score(x, y, p, stereo)
    return {"material": material, "base": base, "transform": p.transform, "mode": mode, "value": value,
            "snr_db": round(snr, 2), "visqol": round(mos, 3),
            "main_frames_lost": int(st["A"]["lost"] + st["A"]["crc_fail"]), "plc_samples": int(st["plc_samples"])}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--json", help="output path")
    ap.add_argument("--materials", default=",".join(MATERIALS))
    ap.add_argument("--bases", default=",".join(BASES))
    args = ap.parse_args()
    tasks = []
    for material in args.materials.split(","):
        for base in args.bases.split(","):
            for suffix in ("", "-L"):
                tasks += [(material, base, suffix, "cn0", c) for c in CN0]
                tasks += [(material, base, suffix, "loss", v) for v in LOSS]
    rows = []
    with ProcessPoolExecutor(args.workers) as pool:
        for future in as_completed([pool.submit(run, t) for t in tasks]):
            rows.append(future.result())
            print(f"{len(rows)}/{len(tasks)}", rows[-1], flush=True)
    rows.sort(key=lambda r: (r["material"], r["base"], r["mode"], r["value"], r["transform"]))
    if args.json:
        with open(args.json, "w") as f:
            json.dump({"condition": "ideal sync, AWGN; see tools/eval/eval_legall.py", "rows": rows}, f, ensure_ascii=False, indent=1)
            f.write("\n")


if __name__ == "__main__":
    main()
