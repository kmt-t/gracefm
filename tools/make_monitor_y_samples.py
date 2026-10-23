#!/usr/bin/env python3
"""Create paired 48 kHz M700Y/M700HY monitor samples and measurements."""

import argparse
import json
import os
import shutil
import sys

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.dirname(__file__))

from gracefm import channel, wavio  # noqa: E402
from gracefm.profiles import PROFILES  # noqa: E402
from gracefm.txrx import Transmitter, receive  # noqa: E402
from eval_hybrid import budget, score, spectrum  # noqa: E402
from make_hybrid_y_samples import atomic_json, sha256  # noqa: E402
from make_samples import codec, make_demo  # noqa: E402

SOURCES = ("demo", "fishin", "vibeace")
PAIRS = {"M700Y": ("M700", (70, 65)),
         "M700HY": ("M700H", (80, 75, 70, 65))}


def filename_for(source, profile, case):
    return f"{source}_{profile}{'_cn0-' + case[4:] if case.startswith('awgn') else '_ideal' if case == 'ideal' else ''}.flac"


def input_audio(source, seconds):
    """Rebuild the exact input used by tools/make_samples.py monitor()."""
    if source == "demo":
        audio = make_demo(48000)
        audio = audio * (0.89 / np.max(np.abs(audio)))
    else:
        audio, fs = wavio.read(os.path.join(ROOT, "samples", f"{source}_orig.flac"))
        if fs != 32000 or len(audio) < 320000:
            raise ValueError(f"{source}: 10 s, 32 kHz source required")
        audio = audio[:320000]
        audio = audio * (0.89 / np.max(np.abs(audio)))
        audio = np.repeat(audio[:, :1], 2, axis=1)
        audio = wavio.resample(audio, 32000, 48000)
    need = seconds * 48000
    if len(audio) < need:
        raise ValueError(f"{source}: input shorter than {seconds} s")
    return audio[:need]


def transmit(audio, profile, case):
    if case == "codec":
        return codec(audio, profile), None, None
    if case == "ideal":
        frames = Transmitter(profile).run(audio)
        output, stats = receive(profile, frames, None, len(audio), 0)
        return output, stats, None
    cn0 = int(case[4:])
    return channel.link(audio, profile, cn0, sub=None, seed=1)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seconds", type=int, default=10)
    parser.add_argument("--sources", default=",".join(SOURCES))
    parser.add_argument("--profiles", default=",".join(PAIRS))
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--no-visqol", action="store_true")
    parser.add_argument("--out", default=os.path.join(ROOT, "samples/monitor_y"))
    parser.add_argument("--json", default=os.path.join(ROOT, "docs/results/monitor_y_samples.json"))
    args = parser.parse_args()
    sources = args.sources.split(",")
    profiles = args.profiles.split(",")
    if (args.seconds < 3 or args.seconds > 10 or
            any(source not in SOURCES for source in sources) or
            any(profile not in PAIRS for profile in profiles)):
        parser.error("unknown source/profile or duration outside 3…10 s")
    os.makedirs(args.out, exist_ok=True)
    os.makedirs(os.path.dirname(args.json), exist_ok=True)
    report = {"version": 1, "description": "48 kHz Y monitor, synchronized symbol simulation; no RF capture",
              "sample_rate_hz": 48000, "seconds": args.seconds, "seed": 1,
              "channel": "single main carrier, AWGN, perfect symbol synchronization",
              "sources": {}, "profiles": {}, "samples": []}
    if args.resume and os.path.exists(args.json):
        with open(args.json, encoding="utf-8") as stream:
            report = json.load(stream)
        if report["version"] != 1 or report["seconds"] != args.seconds or report["sample_rate_hz"] != 48000:
            raise ValueError("saved monitor Y results use a different configuration")

    stale_profiles = {name: (report["profiles"].get(name, {}).get("y_budget") != budget(PROFILES[name])
                             or report["profiles"].get(name, {}).get("profile_signature") != repr(PROFILES[name]))
                      for name in profiles}
    for source in sources:
        audio = input_audio(source, args.seconds)
        reference_name = f"{source}_orig48.flac"
        reference_path = os.path.join(ROOT, "samples/monitor", reference_name)
        output_reference = os.path.join(args.out, reference_name)
        shutil.copyfile(reference_path, output_reference)
        reference, fs = wavio.read(reference_path)
        reference = reference[:len(audio)]
        if fs != 48000 or len(reference) != len(audio):
            raise ValueError(f"{reference_path}: incompatible reference")
        reference_hash = sha256(output_reference)
        source_changed = report["sources"].get(source, {}).get("reference_sha256") != reference_hash
        report["sources"][source] = {
            "reference_file": reference_name, "reference_sha256": reference_hash,
            "channels": 2 if source == "demo" else 1,
            "max_input_reference_difference": float(np.max(np.abs(audio - reference))),
            "construction": "tools/make_samples.py monitor(): demo48 or normalized 32 kHz source resampled to 48 kHz",
        }
        atomic_json(args.json, report)
        for y_name in profiles:
            base_name, cn0_values = PAIRS[y_name]
            profile = PROFILES[y_name]
            profile_signature = repr(profile)
            current_budget = budget(profile)
            profile_changed = stale_profiles[y_name]
            if source == "demo" and (args.force or profile_changed):
                report["profiles"][y_name] = {
                    "baseline": base_name, "baseline_budget": budget(PROFILES[base_name]),
                    "y_budget": current_budget,
                    "profile_signature": profile_signature,
                    "baseline_spectrum_3s": spectrum(PROFILES[base_name], audio[:3 * fs]),
                    "y_spectrum_3s": spectrum(profile, audio[:3 * fs]),
                }
                atomic_json(args.json, report)
            for case in ("codec", "ideal", *(f"awgn{cn0}" for cn0 in cn0_values)):
                old = next((row for row in report["samples"]
                            if row["source"] == source and row["profile"] == y_name and row["case"] == case), None)
                if (not args.force and not source_changed and old and
                        old.get("profile_signature") == profile_signature and
                        old.get("reference_sha256") == reference_hash):
                    existing = os.path.join(args.out, old["file"])
                    if os.path.exists(existing) and sha256(existing) == old["sha256"]:
                        print(source, y_name, case, "reused", flush=True)
                        continue
                output, stats, link_info = transmit(audio, profile, case)
                if not np.all(np.isfinite(output)):
                    raise ValueError(f"{source}, {y_name}, {case}: non-finite output")
                filename = filename_for(source, y_name, case)
                output_path = os.path.join(args.out, filename)
                wavio.write_flac24(output_path, output[:, :2] if source == "demo" else output[:, :1], fs)
                restored, _ = wavio.read(output_path)
                measurements = score(reference, restored, profile, stats, use_visqol=not args.no_visqol)
                measurements["samples_clipped_at_flac"] = int(np.count_nonzero(np.abs(output) > 1.0))
                report["samples"] = [row for row in report["samples"]
                                     if (row["source"], row["profile"], row["case"]) != (source, y_name, case)]
                report["samples"].append({
                    "source": source, "profile": y_name, "baseline": base_name,
                    "profile_signature": profile_signature, "reference_sha256": reference_hash,
                    "case": case, "file": filename, "sha256": sha256(output_path),
                    "link": link_info, "measurements": measurements,
                })
                atomic_json(args.json, report)
                print(source, y_name, case, "finished", flush=True)
    print(args.json, len(report["samples"]), "samples", flush=True)


if __name__ == "__main__":
    main()
