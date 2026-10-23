#!/usr/bin/env python3
"""Generate listenable Y-profile radio samples and measurements.

Uses the real hybrid transmitter/receiver, including phase/radius symbols and
FEC, for both ideal and impaired cases.  The usual secondary carrier is kept.
"""

import argparse
import hashlib
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
from make_samples import codec  # noqa: E402

SOURCES = {
    "fishin": ("B200MHY-A4", "S50M", True),
    "vibeace": ("B200MHY-A4", "S50M", True),
    "demo": ("B200HY-A4", "S100", False),
}
CASES = ("codec", "ideal", "awgn80", "awgn66", "awgn60", "awgn57", "awgn54",
         "rayleigh60", "main_minus10db66", "phase_only66")


def filename_for(source, profile_name, case):
    """Match tools/make_samples.py basenames inside samples/hybrid_y/."""
    if case == "codec":
        return f"{source}_{profile_name}.flac"
    if case == "ideal":
        return f"{source}_Y_ideal_symbols.flac"
    if case.startswith("awgn"):
        return f"{source}_final_cn0-{case[4:]}.flac"
    if case == "rayleigh60":
        return f"{source}_final_rayleigh_cn0-60.flac"
    if case == "main_minus10db66":
        return f"{source}_final_fade10_cn0-66.flac"
    if case == "phase_only66":
        return f"{source}_Y_phaseonly_cn0-66.flac"
    raise ValueError(case)


def sha256(path):
    digest = hashlib.sha256()
    with open(path, "rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def atomic_json(path, value):
    temporary = path + ".tmp"
    with open(temporary, "w", encoding="utf-8") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write("\n")
    os.replace(temporary, path)


def generate(audio, profile, secondary, case):
    if case == "codec":
        return codec(audio, profile), None, {"esn0_main": None, "esn0_sub": None}
    if case == "ideal":
        frames = Transmitter(profile).run(audio)
        output, stats = receive(profile, frames, None, len(audio), 0)
        return output, stats, {"esn0_main": None, "esn0_sub": None}
    cn0 = int("".join(c for c in case if c.isdigit())[-2:])
    options = dict(sub=secondary, power_main=0.5, seed=1)
    if case.startswith("awgn"):
        return channel.link(audio, profile, cn0, **options)
    if case == "phase_only66":
        return channel.link(audio, profile, cn0, hybrid_phase_only=True, **options)
    if case == "rayleigh60":
        return channel.link(audio, profile, cn0, kind_main="rayleigh",
                            kind_sub="rayleigh", **options)
    if case == "main_minus10db66":
        return channel.link(audio, profile, cn0, kind_main="fade10",
                            kind_sub="awgn", **options)
    raise ValueError(case)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seconds", type=int, default=10)
    parser.add_argument("--sources", default=",".join(SOURCES))
    parser.add_argument("--cases", default=",".join(CASES))
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--force", action="store_true", help="selected source/case files are regenerated")
    parser.add_argument("--no-visqol", action="store_true")
    parser.add_argument("--out", default=os.path.join(ROOT, "samples/hybrid_y"))
    parser.add_argument("--json", default=os.path.join(ROOT, "docs/results/hybrid_y_samples.json"))
    args = parser.parse_args()
    selected_sources = args.sources.split(",")
    selected_cases = args.cases.split(",")
    if args.seconds < 3 or any(s not in SOURCES for s in selected_sources) or any(c not in CASES for c in selected_cases):
        parser.error("unknown source/case, or duration shorter than 3 seconds")
    os.makedirs(args.out, exist_ok=True)
    os.makedirs(os.path.dirname(args.json), exist_ok=True)
    report = {
        "version": 2,
        "description": "GraceFM Y-profile listening samples; synced-symbol simulation, not RF capture",
        "sample_rate_hz": 32000, "seconds": args.seconds, "seed": 1,
        "baseline_match": "tools/make_samples.py: 10s, input peak 0.89, C/N0 80/66/60/57/54, seed 1, main/sub 50:50",
        "noisy_link": {"secondary": "S50M or S100", "power_main": 0.5,
                       "power_secondary": 0.5, "phase_only_on_main": True},
        "sources": {}, "samples": [],
    }
    if args.resume and os.path.exists(args.json):
        with open(args.json, encoding="utf-8") as stream:
            report = json.load(stream)
        if report.get("version") != 2 or report["seconds"] != args.seconds or report["sample_rate_hz"] != 32000:
            raise ValueError("saved results use a different sampling configuration")

    for source in selected_sources:
        profile_name, sub_name, mono = SOURCES[source]
        profile, secondary = PROFILES[profile_name], PROFILES[sub_name]
        input_path = os.path.join(ROOT, "samples", f"{source}_orig.flac")
        audio, fs = wavio.read(input_path)
        need = args.seconds * 32000
        if fs != 32000 or len(audio) < need:
            raise ValueError(f"{input_path}: need {args.seconds}s at 32kHz")
        audio = audio[:need]
        audio = audio * (0.89 / np.max(np.abs(audio)))
        if mono:
            audio = np.repeat(audio[:, :1], 2, axis=1)
        reference_name = f"{source}_orig.flac"
        reference_path = os.path.join(args.out, reference_name)
        shutil.copyfile(input_path, reference_path)
        reference, _ = wavio.read(reference_path)
        input_hash = sha256(input_path)
        profile_signature = repr(profile) + repr(secondary)
        current_budget = budget(profile)
        old_source = report["sources"].get(source, {})
        source_changed = (old_source.get("profile_signature") != profile_signature or
                          old_source.get("main_budget") != current_budget or
                          old_source.get("secondary_budget") != budget(secondary) or
                          old_source.get("input_sha256") != input_hash)
        if source_changed:
            report["sources"][source] = {
                "input_file": os.path.relpath(input_path, ROOT),
                "input_sha256": input_hash, "reference_file": reference_name,
                "reference_sha256": sha256(reference_path),
                "main_profile": profile_name, "secondary_profile": sub_name,
                "profile_signature": profile_signature,
                "channels": 1 if mono else 2,
                "main_budget": current_budget, "secondary_budget": budget(secondary),
                "main_spectrum": spectrum(profile, audio),
                "secondary_spectrum": spectrum(secondary, audio),
            }
            atomic_json(args.json, report)
        for case in selected_cases:
            existing = next((row for row in report["samples"]
                             if row["source"] == source and row["case"] == case), None)
            if (not args.force and existing and
                    existing.get("profile_signature") == profile_signature and
                    existing.get("input_sha256") == input_hash and
                    os.path.exists(os.path.join(args.out, existing["file"]))):
                if sha256(os.path.join(args.out, existing["file"])) == existing["sha256"]:
                    print(source, case, "reused", flush=True)
                    continue
            output, stats, link_info = generate(audio, profile, sub_name, case)
            filename = filename_for(source, profile_name, case)
            output_path = os.path.join(args.out, filename)
            if not np.all(np.isfinite(output)):
                raise ValueError(f"{filename}: non-finite sample")
            wavio.write_flac24(output_path, output[:, :1] if mono else output, fs)
            restored, _ = wavio.read(output_path)
            measurements = score(reference, restored, profile, stats,
                                 use_visqol=not args.no_visqol)
            measurements["samples_clipped_at_flac"] = int(np.count_nonzero(np.abs(output) > 1.0))
            if stats is not None and "B" in stats:
                measurements["secondary_crc_fail_percent"] = (
                    100 * stats["B"]["crc_fail"] / stats["B"]["frames"])
            report["samples"] = [row for row in report["samples"]
                                 if row["source"] != source or row["case"] != case]
            report["samples"].append({
                "source": source, "case": case, "main_profile": profile_name,
                "secondary_profile": None if case in ("codec", "ideal") else sub_name,
                "profile_signature": profile_signature, "input_sha256": input_hash,
                "file": filename, "sha256": sha256(output_path),
                "link": link_info, "measurements": measurements,
            })
            atomic_json(args.json, report)
            print(source, case, "finished", flush=True)
    print(args.json, len(report["samples"]), "samples", flush=True)


if __name__ == "__main__":
    main()
