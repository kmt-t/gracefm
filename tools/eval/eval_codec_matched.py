#!/usr/bin/env python3
"""Measure mono and stereo codecs separately at matched analysis bandwidth."""
import argparse
from concurrent.futures import ProcessPoolExecutor
import json
from pathlib import Path
import subprocess
import sys

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from tools.eval.codec_benchmark_io import aptx_roundtrip, heaac_roundtrip, source  # noqa: E402
from tools.common import metrics, wavio  # noqa: E402
from gracefm.profiles import PROFILES  # noqa: E402
from gracefm.codec import roundtrip as codec  # noqa: E402


def bandlimit(x):
    return wavio.resample(wavio.resample(x, 48000, 32000), 32000, 48000)


def evaluate(task):
    from visqol import VisqolApi

    entry, seconds, channels, bandwidth, fdkaac, gracefm_only = task
    x48, _, _ = source(entry, seconds)
    if channels == 1:
        x48 = x48.mean(axis=1, keepdims=True)
    elif entry["channels"] != 2:
        raise ValueError("Stereo view requires stereo source")
    reference = bandlimit(x48) if bandwidth == 16 else x48
    x32 = wavio.resample(reference, 48000, 32000)
    methods = (("B200M", "B200MY") if channels == 1 else ("B200", "B200Y")) if bandwidth == 16 else ()
    methods += ("M700M", "M700MY") if channels == 1 else ("M700", "M700Y")
    if not gracefm_only:
        if channels == 2:
            methods += ("aptX", "aptX HD")
        methods += ("HE-AAC v1 32k", "HE-AAC v1 48k") if channels == 1 else ("HE-AAC v2 32k", "HE-AAC v2 48k")
    api = VisqolApi()
    api.create(mode="audio")
    ffmpeg = None
    if not gracefm_only:
        from imageio_ffmpeg import get_ffmpeg_exe
        ffmpeg = get_ffmpeg_exe()
    rows = []
    for method in methods:
        if method in PROFILES:
            p = PROFILES[method]
            encoded_input = x32 if p.fs == 32000 else reference
            if channels == 1:
                encoded_input = np.repeat(encoded_input, 2, axis=1)
            decoded = codec(encoded_input, p)
            if channels == 1:
                decoded = decoded[:, :1]
            if p.fs == 32000:
                decoded = wavio.resample(decoded, 32000, 48000)
            bitrate, delay = p.audio_kbps(), 0
        elif method in ("aptX", "aptX HD"):
            decoded, bitrate, delay = aptx_roundtrip(reference, "aptx" if method == "aptX" else "aptx_hd", ffmpeg)
        else:
            bitrate = 32000 if method.endswith("32k") else 48000
            decoded, _, delay = heaac_roundtrip(reference, 5 if channels == 1 else 29, bitrate, fdkaac, ffmpeg)
            bitrate /= 1000
        scored = bandlimit(decoded) if bandwidth == 16 else decoded
        if scored.shape != reference.shape:
            raise ValueError(f"Shape mismatch: {entry['name']} {channels} {bandwidth} {method}")
        mos = [float(api.measure_from_arrays(reference[:, ch], scored[:, ch], sample_rate=48000).moslqo)
               for ch in range(channels)]
        snr = float(metrics.snr_db(reference, scored))
        if not np.isfinite(snr) or not all(np.isfinite(m) for m in mos):
            raise ValueError(f"Nonfinite score: {entry['name']} {method}")
        row = dict(material=entry["name"], source_channels=entry["channels"],
                   evaluated_channels=channels, bandwidth_khz=bandwidth, method=method,
                   audio_kbps=round(bitrate, 3), decoder_delay_samples_48khz=delay,
                   snr_db=round(snr, 2), visqol_mean=round(float(np.mean(mos)), 3))
        rows.append(row)
        print(entry["name"], channels, bandwidth, method, row["visqol_mean"], flush=True)
    return rows


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fdkaac", default="fdkaac")
    parser.add_argument("--fdk-source-revision", default="unknown")
    parser.add_argument("--seconds", type=float, default=5.0)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--json", type=Path, default=ROOT / "docs/results/codec_matched.json")
    parser.add_argument("--gracefm-only", action="store_true",
                        help="GraceFMの行だけ測り直し、既存JSONのaptX・HE-AACの行と測定条件はそのまま残す")
    args = parser.parse_args()
    if args.seconds < 3 or args.workers < 1:
        parser.error("seconds must be >= 3 and workers >= 1")
    manifest = json.loads((ROOT / "eval_audio/lossless/manifest.json").read_text())
    entries = manifest["sources"]
    tasks = [(entry, args.seconds, channels, bandwidth, args.fdkaac, args.gracefm_only)
             for entry in entries for channels in (1, 2) if channels == 1 or entry["channels"] == 2
             for bandwidth in (16, 24)]
    with ProcessPoolExecutor(max_workers=args.workers) as executor:
        rows = [row for result in executor.map(evaluate, tasks) for row in result]
    if args.gracefm_only:
        result = json.loads(args.json.read_text())
        result["rows"] = [r for r in result["rows"] if r["method"] not in PROFILES] + rows
        result["profile_signatures"] = {name: repr(p) for name, p in PROFILES.items() if name.startswith(("B200", "M700"))}
        args.json.write_text(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False) + "\n")
        return
    from imageio_ffmpeg import get_ffmpeg_exe
    result = dict(method="Codec-only channel-count and bandwidth matched comparison",
                  source_seconds=args.seconds, source_offset_seconds=1, source_peak=0.89,
                  mono_source_policy="Original mono retained; stereo sources downmixed to (L+R)/2",
                  stereo_source_policy="Original stereo sources only",
                  matched_bandwidth="16 kHz view: common 48->32->48 kHz analysis filter on input, reference and every decoded output",
                  full_bandwidth="24 kHz view: original 48 kHz input; 32 kHz GraceFM excluded",
                  metric="ViSQOL Audio MOS-LQO per channel then mean; waveform SNR per source",
                  aptx_encoder="FFmpeg aptX/aptX HD, stereo only",
                  heaac_encoder="fdkaac AOT 5 mono, AOT 29 stereo; FFmpeg decoded output is forced to the evaluated channel count; ordinary framing, not DAB+ 960-sample framing",
                  fdk_source_revision=args.fdk_source_revision,
                  fdkaac_version=subprocess.run([args.fdkaac, "--help"], capture_output=True, text=True).stdout.splitlines()[0],
                  ffmpeg_version=subprocess.run([get_ffmpeg_exe(), "-version"], capture_output=True, text=True).stdout.splitlines()[0],
                  profile_signatures={name: repr(p) for name, p in PROFILES.items() if name.startswith(("B200", "M700"))},
                  sources=entries, rows=rows)
    args.json.parent.mkdir(parents=True, exist_ok=True)
    args.json.write_text(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False) + "\n")


if __name__ == "__main__":
    main()
