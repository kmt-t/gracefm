#!/usr/bin/env python3
"""Codec-only stereo comparison of B200H and MPEG HE-AAC v2.

Use a working fdkaac build with HE-AAC v2 (AOT 29) support. The Ubuntu
libfdk-aac2 build may omit SBR/PS encoding. This is MPEG HE-AAC v2 with
ordinary AAC framing, not the 960-sample AAC configuration used by DAB+.

Example:
  python tools/eval_heaacv2_benchmark.py --fdkaac /path/to/fdkaac \
      --fdk-source-revision <fdk-aac-commit>
"""
import argparse
import json
from pathlib import Path
import subprocess
import sys
import tempfile

import numpy as np
from scipy.signal import correlate

ROOT = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(ROOT), str(ROOT / "tools")]

from eval_aptx_benchmark import source  # noqa: E402
from gracefm import metrics, wavio  # noqa: E402
from gracefm.profiles import PROFILES  # noqa: E402
from make_samples import codec  # noqa: E402


def heaacv2_roundtrip(x, bitrate, fdkaac, ffmpeg):
    """Encode AOT 29, decode, and remove the measured codec delay."""
    with tempfile.TemporaryDirectory() as directory:
        directory = Path(directory)
        original = directory / "input.wav"
        encoded = directory / "audio.m4a"
        decoded = directory / "decoded.wav"
        wavio.write_pcm24(original, x, 48000)
        subprocess.run([fdkaac, "-S", "-p", "29", "-b", str(bitrate),
                        "-o", str(encoded), str(original)], check=True)
        subprocess.run([ffmpeg, "-y", "-hide_banner", "-loglevel", "error",
                        "-i", str(encoded), "-c:a", "pcm_f32le", str(decoded)],
                       check=True)
        y, fs = wavio.read(decoded)
        size = encoded.stat().st_size
    if fs != 48000 or y.ndim != 2 or y.shape[1] != 2 or len(y) < len(x):
        raise ValueError("Unexpected HE-AAC v2 decoder output")
    # FDK's MP4 gapless signaling is not consistently honored by FFmpeg.
    # Estimate only a constant offset, using both channels over the first second.
    search = min(8192, len(y) - len(x))
    n = min(48000, len(x))
    if search <= 0:
        raise ValueError("Insufficient decoder padding for alignment")
    correlation = sum(correlate(y[:n + search, ch], x[:n, ch],
                                mode="valid", method="fft")
                      for ch in range(2))
    delay = int(np.argmax(correlation))
    y = y[delay:delay + len(x)]
    if len(y) != len(x):
        raise ValueError("HE-AAC v2 delay compensation failed")
    return y, size, delay


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fdkaac", default="fdkaac")
    parser.add_argument("--fdk-source-revision", default="unknown",
                        help="Revision of the libfdk-aac build used by fdkaac")
    parser.add_argument("--seconds", type=float, default=5.0)
    parser.add_argument("--bitrates", default="32000,48000")
    parser.add_argument("--json", type=Path,
                        default=ROOT / "docs/results/heaacv2_benchmark.json")
    args = parser.parse_args()
    if args.seconds < 3:
        parser.error("seconds must be >= 3")
    bitrates = [int(s) for s in args.bitrates.split(",")]
    if any(rate <= 0 for rate in bitrates):
        parser.error("bitrates must be positive")

    from imageio_ffmpeg import get_ffmpeg_exe
    from visqol import VisqolApi

    ffmpeg = get_ffmpeg_exe()
    manifest = json.loads((ROOT / "eval_audio/lossless/manifest.json").read_text())
    api = VisqolApi()
    api.create(mode="audio")
    rows = []
    for entry in manifest["sources"]:
        original48, x32, common48 = source(entry, args.seconds)
        grace48 = wavio.resample(codec(x32, PROFILES["B200H"]), 32000, 48000)
        for view, reference in (("common_16khz", common48),
                                ("full_48khz", original48)):
            for method in ("B200H",) + tuple(f"HE-AACv2-{rate // 1000}k"
                                             for rate in bitrates):
                if method == "B200H":
                    y, size, delay = grace48, None, 0
                    bitrate = PROFILES["B200H"].audio_kbps()
                else:
                    rate = int(method.split("-")[-1][:-1]) * 1000
                    y, size, delay = heaacv2_roundtrip(reference, rate,
                                                       args.fdkaac, ffmpeg)
                    bitrate = rate / 1000
                snr = float(metrics.snr_db(reference, y))
                mos = [float(api.measure_from_arrays(reference[:, ch], y[:, ch],
                                                     sample_rate=48000).moslqo)
                       for ch in range(2)]
                if not np.isfinite(snr) or not all(np.isfinite(m) for m in mos):
                    raise ValueError(f"Nonfinite score: {entry['name']} {view} {method}")
                row = dict(material=entry["name"], view=view, method=method,
                           target_audio_kbps=bitrate, m4a_bytes=size,
                           decoder_delay_samples_48khz=delay,
                           snr_db=round(snr, 2),
                           visqol_left=round(mos[0], 3),
                           visqol_right=round(mos[1], 3),
                           visqol_mean=round(float(np.mean(mos)), 3))
                rows.append(row)
                print(f"{row['material']:10s} {view:13s} {method:13s} "
                      f"SNR {snr:6.2f} dB ViSQOL {row['visqol_mean']:.3f}",
                      flush=True)

    result = dict(method="Codec-only stereo comparison; no DAB+ superframe or radio channel",
                  source_seconds=args.seconds, source_offset_seconds=1,
                  source_peak=0.89, gracefm_profile="B200H",
                  gracefm_profile_signature=repr(PROFILES["B200H"]),
                  heaacv2_profile="MPEG-4 AOT 29 (AAC-LC + SBR + PS)",
                  heaacv2_encoder="fdkaac / Fraunhofer FDK AAC, CBR, 24-bit PCM input",
                  fdkaac_version=subprocess.run([args.fdkaac, "--help"],
                                                capture_output=True, text=True).stdout.splitlines()[0],
                  fdk_source_revision=args.fdk_source_revision,
                  heaacv2_transport="M4A; container bytes reported but excluded from target bitrate",
                  dabplus_caveat="Ordinary AAC frames, not DAB+ 960-sample framing",
                  ffmpeg_version=subprocess.run([ffmpeg, "-version"], check=True,
                                                capture_output=True, text=True).stdout.splitlines()[0],
                  alignment="Constant codec delay measured by stereo cross-correlation; no time stretching",
                  common_view="All codecs receive the same 16 kHz-limited input at their operating rate",
                  full_view="All codecs scored against original 48 kHz source; GraceFM input is 32 kHz",
                  sources=manifest["sources"], rows=rows)
    args.json.parent.mkdir(parents=True, exist_ok=True)
    args.json.write_text(json.dumps(result, ensure_ascii=False, indent=2,
                                    allow_nan=False) + "\n")


if __name__ == "__main__":
    main()
