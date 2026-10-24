#!/usr/bin/env python3
"""Compare saved M700MY/M700Y FLACs with matching current conventional monitor cases."""

import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.dirname(__file__))

from gracefm import wavio  # noqa: E402
from gracefm.profiles import PROFILES  # noqa: E402
from eval_hybrid import score  # noqa: E402
from make_hybrid_y_samples import atomic_json, sha256  # noqa: E402
from make_monitor_y_samples import PAIRS, SOURCES, filename_for  # noqa: E402


def main():
    manifest_path = os.path.join(ROOT, "docs/results/monitor_y_samples.json")
    with open(manifest_path, encoding="utf-8") as stream:
        manifest = json.load(stream)
    out_path = os.path.join(ROOT, "docs/results/monitor_y_comparison.json")
    result = {"description": "Generation-2 48 kHz FLACs; paired material, C/N0, one carrier and seed",
              "comparison": []}
    if os.path.exists(out_path):
        with open(out_path, encoding="utf-8") as stream:
            result = json.load(stream)
    for source in SOURCES:
        original, fs = wavio.read(os.path.join(ROOT, "samples/monitor", f"{source}__48k__reference.flac"))
        original = original[:manifest["seconds"] * fs]
        for y_name, (base_name, cn0_values) in PAIRS.items():
            for case in ("codec", *(f"awgn{cn0}" for cn0 in cn0_values)):
                old_path = os.path.join(ROOT, "samples/monitor", filename_for(source, base_name, case))
                y_path = os.path.join(ROOT, "samples/monitor_y", filename_for(source, y_name, case))
                old_hash, y_hash = sha256(old_path), sha256(y_path)
                existing = next((row for row in result["comparison"]
                                 if (row["source"], row["profile"], row["case"]) == (source, y_name, case)), None)
                if existing and existing["baseline_sha256"] == old_hash and existing["y_sha256"] == y_hash:
                    continue
                old, fs_old = wavio.read(old_path)
                y, fs_y = wavio.read(y_path)
                if fs_old != fs or fs_y != fs or len(old) < len(original) or len(y) != len(original):
                    raise ValueError(f"{source}, {y_name}, {case}: incompatible stored audio")
                baseline_scores = score(original, old[:len(original)], PROFILES[base_name])
                y_row = next(row for row in manifest["samples"]
                             if (row["source"], row["profile"], row["case"]) == (source, y_name, case))
                y_scores = y_row["measurements"]
                keys = ("snr_db", "low_0_6khz", "high_6_24khz", "visqol_moslqo")
                result["comparison"] = [row for row in result["comparison"]
                                        if (row["source"], row["profile"], row["case"]) != (source, y_name, case)]
                result["comparison"].append({
                    "source": source, "profile": y_name, "case": case,
                    "baseline_profile": base_name,
                    "baseline_file": os.path.relpath(old_path, ROOT),
                    "y_file": os.path.relpath(y_path, ROOT),
                    "baseline_sha256": old_hash, "y_sha256": y_hash,
                    "baseline": {key: baseline_scores[key] for key in keys},
                    "y": {key: y_scores[key] for key in keys},
                    "y_minus_baseline": {key: y_scores[key] - baseline_scores[key] for key in keys},
                })
                atomic_json(out_path, result)
                print(source, y_name, case, "compared", flush=True)
    print(out_path, len(result["comparison"]), "matched comparisons", flush=True)


if __name__ == "__main__":
    main()
