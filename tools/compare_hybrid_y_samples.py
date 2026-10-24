#!/usr/bin/env python3
"""Compare stored Y samples with the original GraceFM files, case for case."""

import hashlib
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.dirname(__file__))

from gracefm import wavio  # noqa: E402
from gracefm.profiles import PROFILES  # noqa: E402
from eval_hybrid import score  # noqa: E402
from make_hybrid_y_samples import SOURCES, filename_for  # noqa: E402

CASES = ("codec", "awgn80", "awgn66", "awgn60", "awgn57", "awgn54",
         "rayleigh60", "main_minus10db66")


def digest(path):
    with open(path, "rb") as stream:
        return hashlib.sha256(stream.read()).hexdigest()


def baseline_name(source, baseline_profile, case):
    return filename_for(source, baseline_profile, case)


def main():
    y_manifest_path = os.path.join(ROOT, "docs/results/hybrid_y_samples.json")
    with open(y_manifest_path, encoding="utf-8") as stream:
        y_manifest = json.load(stream)
    result_path = os.path.join(ROOT, "docs/results/hybrid_y_comparison.json")
    result = {"description": "Generation-2 10s FLACs, exact matched source and channel case",
              "comparison": []}
    if os.path.exists(result_path):
        with open(result_path, encoding="utf-8") as stream:
            result = json.load(stream)
    for source, (y_profile, _, mono) in SOURCES.items():
        baseline_profile = "B200M" if mono else "B200"
        input_path = os.path.join(ROOT, "samples", f"{source}__32k__reference.flac")
        original, _ = wavio.read(input_path)
        original = original[:y_manifest["seconds"] * 32000]
        for case in CASES:
            name_old = baseline_name(source, baseline_profile, case)
            name_y = filename_for(source, y_profile, case)
            old_path = os.path.join(ROOT, "samples", name_old)
            y_path = os.path.join(ROOT, "samples/hybrid_y", name_y)
            if not os.path.exists(y_path):
                raise FileNotFoundError(f"Y sample missing: {y_path}")
            old_hash, y_hash = digest(old_path), digest(y_path)
            existing = next((row for row in result["comparison"]
                             if row["source"] == source and row["case"] == case), None)
            if existing and existing["baseline_sha256"] == old_hash and existing["y_sha256"] == y_hash:
                continue
            old, fs_old = wavio.read(old_path)
            y, fs_y = wavio.read(y_path)
            if fs_old != 32000 or fs_y != 32000 or len(old) < len(original) or len(y) != len(original):
                raise ValueError(f"mismatched audio size: {source}, {case}")
            old = old[:len(original)]
            baseline_scores = score(original, old, PROFILES[baseline_profile],
                                    use_visqol=True)
            y_row = next(row for row in y_manifest["samples"]
                         if row["source"] == source and row["case"] == case)
            y_scores = y_row["measurements"]
            result["comparison"] = [row for row in result["comparison"]
                                    if row["source"] != source or row["case"] != case]
            result["comparison"].append({
                "source": source, "case": case,
                "baseline_profile": baseline_profile, "y_profile": y_profile,
                "baseline_file": os.path.relpath(old_path, ROOT),
                "y_file": os.path.relpath(y_path, ROOT),
                "baseline_sha256": old_hash, "y_sha256": y_hash,
                "baseline": baseline_scores,
                "y": {key: y_scores[key] for key in ("snr_db", "low_0_4khz",
                                                       "high_4_16khz", "visqol_moslqo")},
                "y_minus_baseline": {key: y_scores[key] - baseline_scores[key]
                                     for key in ("snr_db", "low_0_4khz",
                                                 "high_4_16khz", "visqol_moslqo")},
            })
            temporary = result_path + ".tmp"
            with open(temporary, "w", encoding="utf-8") as stream:
                json.dump(result, stream, ensure_ascii=False, indent=2, allow_nan=False)
                stream.write("\n")
            os.replace(temporary, result_path)
            print(source, case, "compared", flush=True)
    print(result_path, len(result["comparison"]), "matched comparisons", flush=True)


if __name__ == "__main__":
    main()
