#!/usr/bin/env python3
"""Check exponent width, fixed offset and A4 attenuation on licensed PCM WAV clips.

This is a codec-only robustness check. It reuses the exact local sources and
preprocessing of eval_lossless_benchmark.py, and never writes source audio.
"""
import json
import os
import sys
from dataclasses import replace

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "tools"))

from gracefm import channel, metrics  # noqa: E402
from gracefm.codec import dequantize, exp_range, haar_forward, haar_inverse, quantize_attenuated  # noqa: E402
from gracefm.framing import Layout  # noqa: E402
from gracefm.profiles import PROFILES  # noqa: E402
from eval_lossless_benchmark import prepare  # noqa: E402

BASE = PROFILES["B200MH"]
FOUR = (4,) * BASE.nbands
GROUP4 = (0,) * (BASE.nbands - 1) + (4,)
LAYOUTS = {
    "baseline": BASE,
    "offset_only": replace(BASE, exp_bits_m=FOUR,
                           exp_offset_m=(-26, -26, -27, -28, -29, -28, -26)),
    "A4_adopted": PROFILES["B200MH-A4"],
    "A4_tuned_offset": replace(BASE, exp_bits_m=FOUR,
                               exp_offset_m=(-26, -26, -27, -28, -29, -28, -26),
                               attn_group_m=GROUP4),
    "A4_reduced_exponent": replace(BASE, exp_bits_m=(3, 3, 3, 3, 2, 3, 3),
                                   exp_offset_m=(-18, -18, -19, -20, -17, -20, -18),
                                   attn_group_m=GROUP4),
}


def roundtrip(x, profile):
    blocks = x.reshape(-1, profile.block)
    bands = haar_forward(blocks, profile.levels)
    reconstructed = []
    for k, (coefficients, bits) in enumerate(zip(bands, profile.bits_m)):
        mantissa, exponent, attenuator = quantize_attenuated(coefficients, k, bits, profile, ch="M")
        reconstructed.append(dequantize(mantissa, exponent, k, bits, profile, "M", attenuator))
    return haar_inverse(reconstructed).reshape(-1)


def main():
    with open(os.path.join(ROOT, "eval_audio/lossless/manifest.json"), encoding="utf-8") as source:
        sources = json.load(source)["sources"]
    rows = []
    for source in sources:
        reference = prepare(source, 5.0)[:, 0]
        for input_db in (0, -20, -40):
            gain = 10 ** (input_db / 20)
            x = reference * gain
            for name, profile in LAYOUTS.items():
                y = roundtrip(x, profile)
                row = dict(material=source["name"], input_db=input_db, layout=name,
                           snr_db=round(float(metrics.snr_db(x, y)), 2))
                rows.append(row)
                print(f"{source['name']:10s} {input_db:3d} dB {name:20s} {row['snr_db']:6.2f} dB", flush=True)
    layouts = {}
    for name, profile in LAYOUTS.items():
        layouts[name] = dict(exponent_widths=[profile.exponent_bits("M", k) for k in range(profile.nbands)],
                             fixed_offsets=[exp_range(k, bits, profile, "M")[0]
                                            for k, bits in enumerate(profile.bits_m)],
                             high_band_attenuator_bits=profile.attenuator_bits("M", 6),
                             protected_bits_per_frame=Layout(profile).n_prot_crc,
                             audio_kbps=profile.audio_kbps(),
                             radio_gross_kbps=channel.symbol_rate(profile) * 4 / 1000)
    result = dict(sources=sources, seconds=5.0, segment_start_s=1.0,
                  preprocessing="same as lossless_benchmark.json; mono 32 kHz, peak 0.89",
                  metric="codec-only waveform SNR", input_db=[0, -20, -40],
                  layouts=layouts, rows=rows)
    destination = os.path.join(ROOT, "docs/results/lossless_layout_validation.json")
    with open(destination, "w", encoding="utf-8") as output:
        json.dump(result, output, ensure_ascii=False, indent=2, allow_nan=False)
        output.write("\n")


if __name__ == "__main__":
    main()
