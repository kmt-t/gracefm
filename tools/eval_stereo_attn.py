#!/usr/bin/env python3
"""Compare interval attenuators on the M/S channels of the broadcast stereo profile.

The lossless source files stay in the Git-ignored eval_audio/lossless directory.
Run: .venv/bin/python tools/eval_stereo_attn.py --json docs/results/stereo_attn_eval.json
"""
import argparse
from dataclasses import replace
import json
from pathlib import Path
import sys

import numpy as np
import soundfile as sf

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from gracefm import channel, metrics, wavio  # noqa: E402
from gracefm.codec import (dequantize, haar_forward, haar_inverse,
                           quantize_attenuated)  # noqa: E402
from gracefm.framing import Layout  # noqa: E402
from gracefm.profiles import PROFILES  # noqa: E402


def profiles():
    base = replace(PROFILES["B200"], attn_group_m=None, attn_group_s=None)
    off4 = (0, 0, 0, 0, 0, 0, 4)
    off8 = (0, 0, 0, 0, 0, 0, 8)
    variants = {
        "none": base,
        "M4": replace(base, attn_group_m=off4),
        "S4": replace(base, attn_group_s=off4),
        "M4S4": replace(base, attn_group_m=off4, attn_group_s=off4),
        "M8S8": replace(base, attn_group_m=off8, attn_group_s=off8),
        "M4S8": replace(base, attn_group_m=off4, attn_group_s=off8),
        "M8S4": replace(base, attn_group_m=off8, attn_group_s=off4),
    }
    # 区間ビット12bit/フレームを、M の k=3 (4係数) と k=4 (8係数) の
    # 拡張仮数各1bit削減で相殺した同一音声レート案。
    p = variants["M8S4"]
    bits_m = list(p.bits_m)
    bits_m[3] -= 1
    bits_m[4] -= 1
    variants["M8S4-trim"] = replace(p, bits_m=tuple(bits_m),
                                    exp_offset_m=None, exp_offset_s=None)
    return variants


def source_clips(seconds):
    manifest = json.loads((ROOT / "eval_audio/lossless/manifest.json").read_text())
    n = int(seconds * 32000) // 64 * 64
    clips = {}
    for item in manifest["sources"]:
        if item["channels"] != 2:
            continue
        x, fs = sf.read(ROOT / "eval_audio" / item["file"], always_2d=True)
        x = wavio.resample(x, fs, 32000)[:n]
        if len(x) != n:
            raise ValueError(f"{item['name']}: 音声が短すぎます")
        clips[item["name"]] = x * (0.89 / np.max(np.abs(x)))
    x, fs = sf.read(ROOT / "samples/demo__32k__reference.flac", always_2d=True)
    clips["demo"] = wavio.resample(x, fs, 32000)[:n]
    return clips


def roundtrip(x, p):
    """Vectorized codec roundtrip."""
    ms = {"M": ((x[:, 0] + x[:, 1]) / 2).reshape(-1, p.block),
          "S": ((x[:, 0] - x[:, 1]) / 2).reshape(-1, p.block)}
    decoded = {}
    highband = {}
    for ch, bits in (("M", p.bits_m), ("S", p.bits_s)):
        bands = haar_forward(ms[ch], p.levels)
        rec = []
        for k, (c, b) in enumerate(zip(bands, bits)):
            m, e, a = quantize_attenuated(c, k, b, p, ch=ch)
            rec.append(dequantize(m, e, k, b, p, ch, a))
        decoded[ch] = haar_inverse(rec).reshape(-1)
        highband[ch] = metrics.snr_db(bands[-1], rec[-1])
    M, S = decoded["M"], decoded["S"]
    y = np.stack([M + S, M - S], axis=1)
    return y, highband


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--seconds", type=float, default=5.0)
    ap.add_argument("--perceptual-seconds", type=float, default=0.0,
                    help="L/R ViSQOL と波形SNRを別途測る秒数")
    ap.add_argument("--rf-seconds", type=float, default=0.0,
                    help="RRC パルス成形後の 99%% 占有帯域を測る秒数")
    ap.add_argument("--json", type=Path)
    args = ap.parse_args()
    if args.seconds <= 0 or args.perceptual_seconds < 0 or args.rf_seconds < 0:
        ap.error("評価時間は正の値、追加評価の時間は0以上にしてください")
    if max(args.perceptual_seconds, args.rf_seconds) > args.seconds:
        ap.error("追加評価の時間は --seconds 以下にしてください")
    variants = profiles()
    clips = source_clips(args.seconds)
    rows = []
    for name, x in clips.items():
        for level_db in (0, -20, -40):
            ref = x * 10 ** (level_db / 20)
            mr = (ref[:, 0] + ref[:, 1]) / 2
            sr = (ref[:, 0] - ref[:, 1]) / 2
            for label, p in variants.items():
                y, high = roundtrip(ref, p)
                my = (y[:, 0] + y[:, 1]) / 2
                sy = (y[:, 0] - y[:, 1]) / 2
                lay = Layout(p)
                row = dict(material=name, level_db=level_db, layout=label,
                           lr_snr_db=round(float(metrics.snr_db(ref, y)), 3),
                           mid_snr_db=round(float(metrics.snr_db(mr, my)), 3),
                           side_snr_db=round(float(metrics.snr_db(sr, sy)), 3),
                           high_m_snr_db=round(float(high["M"]), 3),
                           high_s_snr_db=round(float(high["S"]), 3),
                           protected_bits=lay.n_prot_crc,
                           audio_kbps=p.audio_kbps(),
                           symbol_rate_ksym=channel.symbol_rate(p) / 1000,
                           radio_gross_kbps=channel.symbol_rate(p) * 4 / 1000)
                rows.append(row)
                print(f"{name:10s} {level_db:3d}dB {label:3s} "
                      f"LR {row['lr_snr_db']:6.2f} M {row['mid_snr_db']:6.2f} "
                      f"S {row['side_snr_db']:6.2f} "
                      f"high M/S {row['high_m_snr_db']:6.2f}/{row['high_s_snr_db']:6.2f}", flush=True)
    perceptual = []
    if args.perceptual_seconds:
        from make_samples import codec
        from visqol import VisqolApi
        api = VisqolApi()
        api.create(mode="audio")
        n = int(args.perceptual_seconds * 32000) // 64 * 64
        for name, xx in clips.items():
            x = xx[:n]
            for label in ("none", "M8S4"):
                y = codec(x, variants[label])
                mos = []
                for ch in (0, 1):
                    ref = wavio.resample(x[:, ch], 32000, 48000)
                    deg = wavio.resample(y[:, ch], 32000, 48000)
                    mos.append(round(float(api.measure_from_arrays(ref, deg, sample_rate=48000).moslqo), 3))
                row = dict(material=name, layout=label, lr_snr_db=round(float(metrics.snr_db(x, y)), 3),
                           side_snr_db=round(float(metrics.snr_db((x[:, 0] - x[:, 1]) / 2,
                                                                        (y[:, 0] - y[:, 1]) / 2)), 3),
                           visqol_left=mos[0], visqol_right=mos[1])
                perceptual.append(row)
                print("perceptual", row, flush=True)
    rf = []
    if args.rf_seconds:
        from scipy.signal import welch
        from gracefm.pulse import shape
        from gracefm.txrx import Transmitter
        n = int(args.rf_seconds * 32000) // 64 * 64
        for name, xx in clips.items():
            for label in ("none", "M8S8", "M8S4", "M8S4-trim", "M4S8", "M4S4"):
                p = variants[label]
                rs = channel.symbol_rate(p)
                syms = np.concatenate(Transmitter(p).run(xx[:n]))
                wave = shape(syms, beta=p.pulse_beta, span=p.pulse_span, sps=8)
                f, power = welch(wave, fs=8 * rs, nperseg=8192,
                                 return_onesided=False, scaling="density")
                order = np.argsort(f)
                f, power = f[order], power[order]
                cumulative = np.cumsum(power)
                cumulative /= cumulative[-1]
                bw = f[np.searchsorted(cumulative, 0.995)] - f[np.searchsorted(cumulative, 0.005)]
                above = f[power >= power.max() * 1e-3]
                bw30 = (above.max() - above.min()) / 1000
                outside = float(power[np.abs(f) > 100000].sum() / power.sum() * 100)
                row = dict(material=name, layout=label, rrc_beta=p.pulse_beta,
                           rrc_span_symbols=p.pulse_span,
                           occupied_99_khz=round(float(bw / 1000), 3),
                           minus30db_khz=round(float(bw30), 3),
                           outside_200khz_percent=round(outside, 6))
                rf.append(row)
                print("rf", row, flush=True)
    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(json.dumps(dict(seconds=args.seconds, sample_rate_hz=32000,
                                             rows=rows,
                                             perceptual_seconds=args.perceptual_seconds,
                                             perceptual=perceptual,
                                             rf_seconds=args.rf_seconds, rf=rf), indent=2) + "\n")


if __name__ == "__main__":
    main()
