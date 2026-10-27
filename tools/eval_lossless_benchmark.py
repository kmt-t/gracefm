#!/usr/bin/env python3
"""Benchmark A4, MP3 and the radio link on local, untracked licensed WAV sources.

Run fetch_lossless_benchmark_audio.py first. All sources remain in eval_audio/;
only numeric results and source metadata are written to docs/results/.
"""
import argparse
import json
import os
import subprocess
import sys
from concurrent.futures import ProcessPoolExecutor

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "tools"))

from gracefm import channel, metrics, wavio  # noqa: E402
from gracefm.analog_fm import AnalogFM  # noqa: E402
from gracefm.profiles import PROFILES  # noqa: E402
from eval_codec_perceptual import mp3_roundtrip  # noqa: E402
from make_samples import codec  # noqa: E402


def prepare(entry, seconds):
    path = os.path.join(ROOT, "eval_audio", entry["file"])
    x, fs = wavio.read(path)
    # A one-second lead-in avoids a possibly silent file opening.
    first = fs
    if len(x) < first + round(seconds * fs):
        raise ValueError(f"{path}: at least {seconds + 1:g}s required")
    x = x[first:first + round(seconds * fs)].mean(axis=1)
    x = wavio.resample(x[:, None], fs, 32000)[:, 0] if fs != 32000 else x
    x = x[:round(seconds * 32000)]
    peak = float(np.max(np.abs(x)))
    if peak < 1e-4:
        raise ValueError(f"{path}: almost silent evaluation interval")
    x = x * (0.89 / peak)
    return np.repeat(x[:, None], 2, axis=1)


def job(task):
    entry, seconds, method, cn0, kind = task
    from visqol import VisqolApi

    x = prepare(entry, seconds)
    plc = 0.0
    encoded_bytes = None
    if method == "B200M":
        y = codec(x, PROFILES[method])
        audio_kbps = round(PROFILES[method].audio_kbps(), 1)
    elif method.startswith("MP3-"):
        audio_kbps = int(method.split("-", 1)[1])
        y, encoded_bytes = mp3_roundtrip(x, 32000, audio_kbps)
    elif method == "GraceFM":
        y, state, _ = channel.link(x, "B200M", cn0, sub="SUB50M",
                                   kind_main=kind, kind_sub="awgn" if kind == "fade10" else kind, seed=1)
        plc = 100 * state["plc_samples"] / len(x)
        audio_kbps = 474.0
    elif method == "FM":
        fm = AnalogFM(x[:, 0], 32000)
        gains = None if kind == "awgn" else channel.fading_gains(
            int(np.ceil(len(x) / 64)), kind, np.random.default_rng(101))
        mono = fm.receive(cn0, np.random.default_rng(1), gains)
        y = np.repeat(mono[:, None], 2, axis=1)
        audio_kbps = None
    else:
        raise ValueError(method)
    snr = float(metrics.snr_db(x, y))
    reference = wavio.resample(x.mean(axis=1), 32000, 48000)
    degraded = wavio.resample(y.mean(axis=1), 32000, 48000)
    api = VisqolApi()
    api.create(mode="audio")
    mos = float(api.measure_from_arrays(reference, degraded, sample_rate=48000).moslqo)
    if not np.isfinite(snr) or not np.isfinite(mos):
        raise ValueError(f"nonfinite result: {entry['name']}, {method}, {cn0}")
    return dict(material=entry["name"], method=method, channel=kind or "codec", cn0_db_hz=cn0,
                nominal_audio_kbps=audio_kbps, mp3_encoded_bytes=encoded_bytes,
                snr_db=round(snr, 2), visqol_moslqo=round(mos, 3),
                plc_percent=round(plc, 2))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seconds", type=float, default=5.0)
    parser.add_argument("--cn0", default="54,60,66,80")
    parser.add_argument("--channels", default="awgn", help="awgn,rayleigh,fade10")
    parser.add_argument("--skip-codec", action="store_true", help="measure link conditions only")
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--json", default=os.path.join(ROOT, "docs/results/lossless_benchmark.json"))
    args = parser.parse_args()
    if args.seconds < 3 or args.workers < 1:
        parser.error("seconds must be >= 3; workers must be >= 1")
    strengths = [int(c.strip()) for c in args.cn0.split(",")]
    kinds = [c.strip() for c in args.channels.split(",") if c.strip()]
    if not kinds or any(kind not in ("awgn", "rayleigh", "fade10") for kind in kinds):
        parser.error("channels must be awgn, rayleigh or fade10")
    with open(os.path.join(ROOT, "eval_audio/lossless/manifest.json"), encoding="utf-8") as source:
        entries = json.load(source)["sources"]
    tasks = []
    for entry in entries:
        if not args.skip_codec:
            tasks.extend((entry, args.seconds, method, None, None)
                         for method in ("B200M", "MP3-128", "MP3-192", "MP3-320"))
        tasks.extend((entry, args.seconds, method, cn0, kind)
                     for kind in kinds for cn0 in strengths for method in ("FM", "GraceFM"))
    rows = []
    with ProcessPoolExecutor(max_workers=args.workers) as executor:
        for row in executor.map(job, tasks):
            rows.append(row)
            print(f"{row['material']:10s} {row['channel']:8s} {row['method']:10s} C/N0 {str(row['cn0_db_hz']):>4s} "
                  f"SNR {row['snr_db']:6.2f} dB ViSQOL {row['visqol_moslqo']:.3f}", flush=True)
    from imageio_ffmpeg import get_ffmpeg_exe
    ffmpeg_version = subprocess.run([get_ffmpeg_exe(), "-version"], check=True,
                                    capture_output=True, text=True).stdout.splitlines()[0]
    result = dict(metric="ViSQOL Audio MOS-LQO", metric_implementation="visqol-python 3.8.0",
                  mp3_encoder=f"{ffmpeg_version} / libmp3lame CBR",
                  gracefm_main_profile="B200M", gracefm_sub_profile="SUB50M",
                  seconds=args.seconds, evaluation_sample_rate_hz=32000,
                  visqol_sample_rate_hz=48000, cn0_noise_bandwidth_hz=180000,
                  channels=kinds,
                  source_processing="Read original WAV, take seconds 1..1+duration, downmix to mono, "
                                    "resample to 32 kHz and normalize peak to 0.89; duplicate to L/R codec input.",
                  comparison="Codec-only A4 vs MP3 CBR; separate link comparison A4+SUB50M vs analog mono FM.",
                  sources=entries, rows=rows)
    with open(args.json, "w", encoding="utf-8") as output:
        json.dump(result, output, ensure_ascii=False, indent=2, allow_nan=False)
        output.write("\n")


if __name__ == "__main__":
    main()
