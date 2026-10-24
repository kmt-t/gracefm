#!/usr/bin/env python3
"""Compare stereo B200H with FFmpeg aptX and aptX HD on untracked lossless WAVs.

The common-band view uses the same 32 kHz input for GraceFM and aptX (the
latter is upsampled to its 48 kHz operating rate). The full-band view uses
the original 48 kHz signal as reference, exposing GraceFM's 16 kHz limit.
Only numeric results and source metadata are saved in docs/results/.
"""
import argparse
from concurrent.futures import ProcessPoolExecutor
import json
from pathlib import Path
import subprocess
import sys
import tempfile

import numpy as np
from scipy.signal import correlate

ROOT = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(ROOT), str(ROOT / "tools")]

from gracefm import metrics, wavio  # noqa: E402
from gracefm.profiles import PROFILES  # noqa: E402
from make_samples import codec  # noqa: E402


def source(entry, seconds):
    x, fs = wavio.read(ROOT / "eval_audio" / entry["file"])
    if len(x) < round((seconds + 1) * fs):
        raise ValueError(f"{entry['name']}: at least {seconds + 1:g}s required")
    x = x[fs:fs + round(seconds * fs)]
    x = wavio.resample(x, fs, 48000)
    x *= 0.89 / np.max(np.abs(x))
    n32 = int(seconds * 32000) // 64 * 64
    if n32 < 64:
        raise ValueError("evaluation interval is too short")
    x48 = x[:n32 * 3 // 2]
    x32 = wavio.resample(x48, 48000, 32000)[:n32]
    common48 = wavio.resample(x32, 32000, 48000)
    return x48, x32, common48


def aptx_roundtrip(x, variant, ffmpeg):
    """Encode/decode 48 kHz stereo and compensate the measured codec delay."""
    if variant not in ("aptx", "aptx_hd") or x.ndim != 2 or x.shape[1] != 2:
        raise ValueError("aptX requires stereo audio and a supported variant")
    pad = 512
    with tempfile.TemporaryDirectory() as directory:
        source_path = Path(directory) / "source.wav"
        encoded = Path(directory) / f"audio.{variant}"
        decoded = Path(directory) / "decoded.wav"
        input_audio = np.pad(x, ((0, pad), (0, 0)))
        if variant == "aptx":
            from scipy.io import wavfile
            pcm16 = np.clip(np.rint(input_audio * 32767), -32768, 32767).astype(np.int16)
            wavfile.write(source_path, 48000, pcm16)
        else:
            wavio.write_pcm24(source_path, input_audio, 48000)
        subprocess.run([ffmpeg, "-y", "-hide_banner", "-loglevel", "error", "-i", str(source_path),
                        "-c:a", variant, "-f", variant, str(encoded)], check=True)
        subprocess.run([ffmpeg, "-y", "-hide_banner", "-loglevel", "error", "-f", variant,
                        "-i", str(encoded), "-c:a", "pcm_f32le", str(decoded)], check=True)
        y, fs = wavio.read(decoded)
        size = encoded.stat().st_size
    if fs != 48000 or len(y) < len(x) + 256:
        raise ValueError(f"{variant}: unexpected decoder length or sample rate")
    n = min(48000, len(x))
    delay = int(np.argmax(correlate(y[:n + 256, 0], x[:n, 0], mode="valid", method="fft")))
    y = y[delay:delay + len(x)]
    if len(y) != len(x):
        raise ValueError(f"{variant}: delay compensation failed")
    kbps = size * 8 * 48000 / (len(x) + pad) / 1000
    return y, round(kbps, 3), delay


def evaluate(task):
    from imageio_ffmpeg import get_ffmpeg_exe
    from visqol import VisqolApi

    entry, seconds = task
    original48, x32, common48 = source(entry, seconds)
    grace48 = wavio.resample(codec(x32, PROFILES["B200H"]), 32000, 48000)
    api = VisqolApi()
    api.create(mode="audio")
    rows = []
    for view, reference in (("common_16khz", common48), ("full_48khz", original48)):
        for method in ("B200H", "aptX", "aptX_HD"):
            if method == "B200H":
                y, bitrate, delay = grace48, PROFILES["B200H"].audio_kbps(), 0
            else:
                variant = "aptx" if method == "aptX" else "aptx_hd"
                y, bitrate, delay = aptx_roundtrip(reference, variant, get_ffmpeg_exe())
            snr = float(metrics.snr_db(reference, y))
            mos = [float(api.measure_from_arrays(reference[:, ch], y[:, ch], sample_rate=48000).moslqo)
                   for ch in (0, 1)]
            if not np.isfinite(snr) or not all(np.isfinite(m) for m in mos):
                raise ValueError(f"nonfinite result: {entry['name']} {view} {method}")
            rows.append(dict(material=entry["name"], view=view, method=method,
                             audio_kbps=round(bitrate, 3), decoder_delay_samples_48khz=delay,
                             snr_db=round(snr, 2), visqol_left=round(mos[0], 3),
                             visqol_right=round(mos[1], 3), visqol_mean=round(float(np.mean(mos)), 3)))
    return rows


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seconds", type=float, default=5.0)
    parser.add_argument("--workers", type=int, default=3)
    parser.add_argument("--json", type=Path, default=ROOT / "docs/results/aptx_benchmark.json")
    args = parser.parse_args()
    if args.seconds < 3 or args.workers < 1:
        parser.error("seconds must be >= 3 and workers >= 1")
    from imageio_ffmpeg import get_ffmpeg_exe
    ffmpeg = get_ffmpeg_exe()
    encoders = subprocess.run([ffmpeg, "-hide_banner", "-encoders"], check=True,
                              capture_output=True, text=True).stdout
    available = {line.split()[1] for line in encoders.splitlines()
                 if line.lstrip().startswith("A") and len(line.split()) > 1}
    if not {"aptx", "aptx_hd"} <= available:
        parser.error("FFmpeg build does not contain aptx and aptx_hd encoders")
    manifest = json.loads((ROOT / "eval_audio/lossless/manifest.json").read_text())
    entries = manifest["sources"]
    with ProcessPoolExecutor(max_workers=args.workers) as executor:
        rows = []
        for result in executor.map(evaluate, ((entry, args.seconds) for entry in entries)):
            rows.extend(result)
            for row in result:
                print(f"{row['material']:10s} {row['view']:13s} {row['method']:7s} "
                      f"{row['audio_kbps']:6.1f} kbps SNR {row['snr_db']:6.2f} dB "
                      f"ViSQOL {row['visqol_mean']:.3f}", flush=True)
    version = subprocess.run([ffmpeg, "-version"], check=True, capture_output=True,
                             text=True).stdout.splitlines()[0]
    result = dict(method="Codec-only stereo comparison; no Bluetooth transport or radio channel",
                  ffmpeg_version=version, gracefm_profile="B200H",
                  gracefm_profile_signature=repr(PROFILES["B200H"]), source_seconds=args.seconds,
                  source_offset_seconds=1, source_peak=0.89, aptx_sample_rate_hz=48000,
                  gracefm_sample_rate_hz=32000, metric_sample_rate_hz=48000,
                  common_view="All codecs receive the same 16 kHz-limited input; aptX input is upsampled from 32 to 48 kHz.",
                  full_view="All codecs are compared against the original 48 kHz audio; GraceFM is downsampled to 32 kHz.",
                  alignment="FFmpeg aptX decoder delay is measured by cross-correlation over 0..256 samples and removed.",
                  sources=entries, rows=rows)
    args.json.parent.mkdir(parents=True, exist_ok=True)
    args.json.write_text(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False) + "\n")


if __name__ == "__main__":
    main()
