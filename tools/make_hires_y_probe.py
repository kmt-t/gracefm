#!/usr/bin/env python3
"""Generate a 48 kHz/24-bit, 12–24 kHz-rich stereo probe and M700 Y pairs."""

import argparse
import json
import os
import sys

import numpy as np
from scipy.signal import butter, sosfilt

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.dirname(__file__))

from gracefm import channel, wavio  # noqa: E402
from gracefm.codec import haar_forward  # noqa: E402
from gracefm.profiles import PROFILES  # noqa: E402
from gracefm.txrx import Transmitter, receive  # noqa: E402
from eval_hybrid import score  # noqa: E402
from make_hybrid_y_samples import atomic_json, sha256  # noqa: E402
from make_monitor_y_samples import filename_for  # noqa: E402
from make_samples import codec, make_demo  # noqa: E402

PAIRS = (("M700", "M700Y", (70, 65)),
         ("M700H", "M700HY", (80, 75, 70, 65)))


def make_probe():
    fs = 48000
    audio = make_demo(fs)
    n = len(audio)
    t = np.arange(n) / fs
    rng = np.random.default_rng(2026)
    sos = butter(6, (12000, 22000), btype="bandpass", fs=fs, output="sos")
    high = sosfilt(sos, rng.standard_normal(n))
    high /= max(float(np.sqrt(np.mean(high ** 2))), 1e-12)
    envelope = np.full(n, 0.12)
    for onset in np.arange(0, 10, 0.5):
        i = int(onset * fs)
        length = min(int(0.32 * fs), n - i)
        envelope[i:i + length] += 0.9 * np.exp(-np.arange(length) / fs * 18)
    shimmer = (0.010 * np.sin(2 * np.pi * 14200 * t)
               + 0.008 * np.sin(2 * np.pi * 17700 * t)
               + 0.006 * np.sin(2 * np.pi * 21400 * t))
    high = 0.13 * envelope * high + shimmer * (0.4 + 0.6 * np.sin(np.pi * 0.7 * t) ** 2)
    audio[:, 0] += high
    audio[:, 1] += 0.92 * high
    return audio * (0.89 / np.max(np.abs(audio)))


def highest_band_snr(reference, degraded):
    """12–24 kHz SNR of L/R signal, using the sixth Haar detail band."""
    sig = err = 0.0
    for ch in range(2):
        original = haar_forward(reference[:, ch].reshape(-1, 64), 6)[6]
        difference = haar_forward((degraded[:, ch] - reference[:, ch]).reshape(-1, 64), 6)[6]
        sig += float(np.sum(original ** 2))
        err += float(np.sum(difference ** 2))
    return float(10 * np.log10(max(sig, 1e-30) / max(err, 1e-30)))


def transmit(audio, profile, case):
    if case == "codec":
        return codec(audio, profile), None, None
    if case == "ideal":
        frames = Transmitter(profile).run(audio)
        output, stats = receive(profile, frames, None, len(audio), 0)
        return output, stats, None
    return channel.link(audio, profile, int(case[4:]), sub=None, seed=1)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--no-visqol", action="store_true")
    parser.add_argument("--out", default=os.path.join(ROOT, "samples/monitor_y"))
    parser.add_argument("--json", default=os.path.join(ROOT, "docs/results/monitor_y_hires_probe.json"))
    parser.add_argument("--profiles", default="M700,M700Y,M700H,M700HY")
    args = parser.parse_args()
    selected_profiles = args.profiles.split(",")
    if any(name not in ("M700", "M700Y", "M700H", "M700HY") for name in selected_profiles):
        parser.error("unknown profile")
    os.makedirs(args.out, exist_ok=True)
    os.makedirs(os.path.dirname(args.json), exist_ok=True)
    filename = "hires_probe__48k__reference.flac"
    original_path = os.path.join(args.out, filename)
    if not (args.resume and os.path.exists(original_path)):
        wavio.write_flac24(original_path, make_probe(), 48000)
    reference, fs = wavio.read(original_path)
    if fs != 48000 or len(reference) != 480000:
        raise ValueError("probe reference must be 10 s at 48 kHz")
    source_bands = haar_forward(((reference[:, 0] + reference[:, 1]) / 2).reshape(-1, 64), 6)
    energies = [float(np.sum(band ** 2)) for band in source_bands]
    report = {"version": 1, "description": "Deterministic 48 kHz 24-bit synthetic stereo high-band probe",
              "reference_file": filename, "reference_sha256": sha256(original_path),
              "source_m_12_24khz_energy_fraction": energies[6] / sum(energies),
              "sample_rate_hz": fs, "seconds": 10, "seed": 1,
              "channel": "single main carrier, AWGN, perfect symbol synchronization",
              "samples": [], "comparison": []}
    if args.resume and os.path.exists(args.json):
        with open(args.json, encoding="utf-8") as stream:
            previous = json.load(stream)
        if previous["reference_sha256"] != report["reference_sha256"]:
            raise ValueError("probe source changed; regenerate without --resume")
        report = previous

    for old_name, y_name, cn0_values in PAIRS:
        for name in (old_name, y_name):
            if name not in selected_profiles:
                continue
            profile = PROFILES[name]
            cases = ("codec", *(f"awgn{cn0}" for cn0 in cn0_values))
            if name == y_name:
                cases = ("codec", "ideal", *(f"awgn{cn0}" for cn0 in cn0_values))
            for case in cases:
                old = next((row for row in report["samples"]
                            if (row["profile"], row["case"]) == (name, case)), None)
                if old and old.get("profile_signature") == repr(profile):
                    path = os.path.join(args.out, old["file"])
                    if os.path.exists(path) and sha256(path) == old["sha256"]:
                        print(name, case, "reused", flush=True)
                        continue
                output, stats, link_info = transmit(reference, profile, case)
                if not np.all(np.isfinite(output)):
                    raise ValueError(f"{name} {case}: non-finite output")
                output_name = filename_for("hires_probe", name, case)
                output_path = os.path.join(args.out, output_name)
                wavio.write_flac24(output_path, output, fs)
                stored, _ = wavio.read(output_path)
                measurements = score(reference, stored, profile, stats, use_visqol=not args.no_visqol)
                measurements["highest_12_24khz"] = highest_band_snr(reference, stored)
                measurements["samples_clipped_at_flac"] = int(np.count_nonzero(np.abs(output) > 1.0))
                report["samples"] = [row for row in report["samples"]
                                     if (row["profile"], row["case"]) != (name, case)]
                report["samples"].append({"profile": name, "case": case,
                                          "profile_signature": repr(profile),
                                          "file": output_name, "sha256": sha256(output_path),
                                          "link": link_info, "measurements": measurements})
                atomic_json(args.json, report)
                print(name, case, "finished", flush=True)
        report["comparison"] = []
        for base, hybrid, cn0s in PAIRS:
            for case in ("codec", *(f"awgn{cn0}" for cn0 in cn0s)):
                left = next((r for r in report["samples"] if (r["profile"], r["case"]) == (base, case)), None)
                right = next((r for r in report["samples"] if (r["profile"], r["case"]) == (hybrid, case)), None)
                if left and right:
                    report["comparison"].append({
                        "baseline": base, "y": hybrid, "case": case,
                        "baseline_file": left["file"], "y_file": right["file"],
                        "baseline_measurements": left["measurements"],
                        "y_measurements": right["measurements"],
                    })
        atomic_json(args.json, report)
    print(args.json, len(report["samples"]), "samples", len(report["comparison"]), "pairs", flush=True)


if __name__ == "__main__":
    main()
