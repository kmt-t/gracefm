#!/usr/bin/env python3
"""Compare 10/12-bit continuous-radius variants against the standard 8-bit M700Y."""

import argparse
import json
import os
import sys

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.dirname(__file__))

from sample_names import sample_name

from gracefm import channel, metrics, wavio  # noqa: E402
from gracefm.codec import haar_forward  # noqa: E402
from gracefm.profiles import PROFILES, make_hybrid  # noqa: E402
from eval_hybrid import budget, score, spectrum  # noqa: E402
from make_hires_y_probe import highest_band_snr  # noqa: E402
from make_hybrid_y_samples import atomic_json, sha256  # noqa: E402
from make_monitor_y_samples import input_audio  # noqa: E402
from make_samples import codec  # noqa: E402


def s_quality(reference, output):
    """S成分の波形と6〜24 kHzのSNR。"""
    s_ref = (reference[:, 0] - reference[:, 1]) / 2
    s_out = (output[:, 0] - output[:, 1]) / 2
    bands_ref = haar_forward(s_ref.reshape(-1, 64), 6)
    bands_err = haar_forward((s_out - s_ref).reshape(-1, 64), 6)
    sig = sum(float(np.sum(band ** 2)) for band in bands_ref[5:])
    err = sum(float(np.sum(band ** 2)) for band in bands_err[5:])
    return {"s_wave_snr_db": float(metrics.snr_db(s_ref, s_out)),
            "s_high_6_24khz_snr_db": float(10 * np.log10(max(sig, 1e-30) / max(err, 1e-30)))}


def source_audio(source):
    if source == "demo":
        transmitted = input_audio("demo", 10)
        reference, fs = wavio.read(os.path.join(ROOT, "samples/monitor/demo__48k__reference.flac"))
    else:
        path = os.path.join(ROOT, "samples/monitor_y/hires_probe__48k__reference.flac")
        transmitted, fs = wavio.read(path)
        reference = transmitted
    if fs != 48000 or len(transmitted) != 480000 or len(reference) != len(transmitted):
        raise ValueError("48 kHz、10秒のステレオ音源が必要です")
    return transmitted, reference


def variant(bits):
    if bits not in (8, 10, 12):
        raise ValueError("this evaluation covers 8, 10, and 12 bits")
    return make_hybrid(PROFILES["M700"], f"M700Y-R{bits}", PROFILES["M700Y"].pid,
                       mantissa_bits=bits, experimental_tag=3)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--sources", default="demo,hires_probe")
    parser.add_argument("--bits", default="10,12")
    parser.add_argument("--generate-only", action="store_true", help="generate current audio before baseline comparison is ready")
    parser.add_argument("--json", default=os.path.join(ROOT, "docs/results/monitor_y_radius_precision.json"))
    args = parser.parse_args()
    sources = args.sources.split(",")
    bit_values = [int(value) for value in args.bits.split(",")]
    if any(source not in ("demo", "hires_probe") for source in sources):
        parser.error("sources must be demo and/or hires_probe")
    if any(bits not in (8, 10, 12) for bits in bit_values):
        parser.error("bits must be 8, 10, and/or 12")

    baseline = PROFILES["M700Y"]
    report_path = args.json
    report = {"description": "10 s stereo, single main carrier, AWGN seed 1; same 48 M-hybrid symbols and FEC top bit",
              "reference_profile": baseline.name,
              "reference_budget": budget(baseline), "variants": {}, "comparison": []}
    if args.resume and os.path.exists(report_path):
        with open(report_path, encoding="utf-8") as stream:
            report = json.load(stream)
        chosen = {f"M700Y-R{bits}" for bits in bit_values}
        report["variants"] = {name: value for name, value in report["variants"].items()
                              if name in chosen}
        report["comparison"] = [row for row in report["comparison"] if row["profile"] in chosen]
        report["reference_profile"] = baseline.name
        report["reference_budget"] = budget(baseline)

    baseline_manifests = {}
    for source, filename in (("demo", "monitor_y_samples.json"),
                             ("hires_probe", "monitor_y_hires_probe.json")):
        if not args.generate_only:
            with open(os.path.join(ROOT, "docs/results", filename), encoding="utf-8") as stream:
                baseline_manifests[source] = json.load(stream)

    for bits in bit_values:
        p = variant(bits)
        profile_data = {"hybrid_bits": bits, "hybrid_amplitude": p.hybrid_amplitude,
                        "budget": budget(p)}
        if profile_data["budget"]["total_symbols_per_frame"] != report["reference_budget"]["total_symbols_per_frame"]:
            raise AssertionError("radius width changed the frame size")
        profile_data["spectrum_3s"] = report["variants"].get(p.name, {}).get("spectrum_3s")
        report["variants"][p.name] = profile_data
        for source in sources:
            transmitted, reference = source_audio(source)
            if not args.generate_only and source == "demo" and not report["variants"][p.name]["spectrum_3s"]:
                report["variants"][p.name]["spectrum_3s"] = spectrum(p, transmitted[:3 * 48000])
                atomic_json(report_path, report)
            for case in ("codec", "awgn80", "awgn75", "awgn70", "awgn65"):
                filename = sample_name(source, 48000, p.name, case)
                path = os.path.join(ROOT, "samples/monitor_y", filename)
                existing = next((row for row in report["comparison"]
                                 if (row["source"], row["profile"], row["case"]) == (source, p.name, case)), None)
                reused = existing and args.resume and os.path.exists(path) and sha256(path) == existing["sha256"]
                if reused:
                    stored, fs = wavio.read(path)
                    measurement = existing["variant_measurements"]
                    print(source, p.name, case, "reused", flush=True)
                else:
                    if case == "codec":
                        output, stats = codec(transmitted, p), None
                    else:
                        output, stats, _ = channel.link(transmitted, p, int(case[4:]), sub=None, seed=1)
                    if not np.all(np.isfinite(output)):
                        raise ValueError(f"non-finite output: {filename}")
                    wavio.write_flac24(path, output, 48000)
                    stored, fs = wavio.read(path)
                    measurement = score(reference, stored, p, stats)
                    measurement.update(s_quality(reference, stored))
                    measurement["samples_clipped_at_flac"] = int(np.count_nonzero(np.abs(output) > 1))
                    if source == "hires_probe":
                        measurement["highest_12_24khz"] = highest_band_snr(reference, stored)
                if fs != 48000 or stored.shape != reference.shape:
                    raise ValueError(f"stored audio mismatch: {filename}")
                if args.generate_only:
                    report["comparison"] = [r for r in report["comparison"] if (r["source"], r["profile"], r["case"]) != (source, p.name, case)]
                    report["comparison"].append(dict(source=source, profile=p.name, case=case,
                                                      file=filename, sha256=sha256(path),
                                                      variant_measurements=measurement))
                    atomic_json(report_path, report)
                    print(source, p.name, case, "generated", flush=True)
                    continue
                base_row = next(row for row in baseline_manifests[source]["samples"]
                                if row["profile"] == baseline.name and row["case"] == case
                                and (source == "hires_probe" or row["source"] == source))
                base_path = os.path.join(ROOT, "samples/monitor_y", base_row["file"])
                baseline_audio, _ = wavio.read(base_path)
                baseline_measurement = dict(base_row["measurements"])
                baseline_measurement.update(s_quality(reference, baseline_audio))
                if source == "hires_probe":
                    baseline_measurement["highest_12_24khz"] = highest_band_snr(reference, baseline_audio)
                row = {"source": source, "profile": p.name, "case": case,
                       "file": filename, "sha256": sha256(path),
                       "reference_file": base_row["file"], "reference_sha256": sha256(base_path),
                       "reference_measurements": baseline_measurement,
                       "variant_measurements": measurement}
                report["comparison"] = [old for old in report["comparison"]
                                        if (old["source"], old["profile"], old["case"]) != (source, p.name, case)]
                report["comparison"].append(row)
                atomic_json(report_path, report)
                print(source, p.name, case, "wave", round(measurement["snr_db"], 2),
                      "MOS", round(measurement["visqol_moslqo"], 2), flush=True)
    print(report_path, len(report["comparison"]), "conditions", flush=True)


if __name__ == "__main__":
    main()
