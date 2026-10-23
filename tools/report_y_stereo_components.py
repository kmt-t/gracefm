#!/usr/bin/env python3
"""Measure M/S component quality of stored, matched Y listening samples."""

import hashlib
import json
import os
import sys

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from gracefm import metrics, wavio  # noqa: E402
from gracefm.codec import haar_forward  # noqa: E402


def read_json(name):
    with open(os.path.join(ROOT, "docs/results", name), encoding="utf-8") as stream:
        return json.load(stream)


def audio(path, expected_hash=None):
    full_path = os.path.join(ROOT, path)
    if expected_hash is not None:
        digest = hashlib.sha256()
        with open(full_path, "rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
        if digest.hexdigest() != expected_hash:
            raise ValueError(f"stored audio hash changed: {path}")
    return wavio.read(full_path)


def band_snr(reference, output, indices):
    ref = haar_forward(reference.reshape(-1, 64), 6)
    err = haar_forward((output - reference).reshape(-1, 64), 6)
    power = sum(float(np.sum(ref[k] ** 2)) for k in indices)
    error = sum(float(np.sum(err[k] ** 2)) for k in indices)
    return float(10 * np.log10(max(power, 1e-30) / max(error, 1e-30)))


def band_level_change(reference, output, indices):
    ref = haar_forward(reference.reshape(-1, 64), 6)
    out = haar_forward(output.reshape(-1, 64), 6)
    power_ref = sum(float(np.sum(ref[k] ** 2)) for k in indices)
    power_out = sum(float(np.sum(out[k] ** 2)) for k in indices)
    return float(10 * np.log10(max(power_out, 1e-30) / max(power_ref, 1e-30)))


def measure(reference, output):
    if reference.shape != output.shape or reference.ndim != 2 or reference.shape[1] != 2:
        raise ValueError("matched stereo signals are required")
    if len(reference) % 64:
        raise ValueError("audio length must be a multiple of the frame size")
    m_ref, s_ref = (reference[:, 0] + reference[:, 1]) / 2, (reference[:, 0] - reference[:, 1]) / 2
    m_out, s_out = (output[:, 0] + output[:, 1]) / 2, (output[:, 0] - output[:, 1]) / 2
    return {
        "m_wave_snr_db": float(metrics.snr_db(m_ref, m_out)),
        "s_wave_snr_db": float(metrics.snr_db(s_ref, s_out)),
        "m_low_snr_db": band_snr(m_ref, m_out, range(5)),
        "m_high_snr_db": band_snr(m_ref, m_out, (5, 6)),
        "s_low_snr_db": band_snr(s_ref, s_out, range(5)),
        "s_high_snr_db": band_snr(s_ref, s_out, (5, 6)),
        "s_high_level_change_db": band_level_change(s_ref, s_out, (5, 6)),
    }


def pair(group, source, case, fs, reference, baseline_file, y_file,
         baseline_hash=None, y_hash=None, baseline_name=None, y_name=None):
    old, old_fs = audio(baseline_file, baseline_hash)
    new, new_fs = audio(y_file, y_hash)
    if old_fs != fs or new_fs != fs or old.shape != reference.shape or new.shape != reference.shape:
        raise ValueError(f"incompatible matched audio: {group}/{source}/{case}")
    return {"group": group, "source": source, "case": case, "sample_rate_hz": fs,
            "baseline_profile": baseline_name, "y_profile": y_name,
            "baseline_file": baseline_file, "y_file": y_file,
            "baseline": measure(reference, old), "y": measure(reference, new)}


def main():
    rows = []
    reference32, fs32 = audio("samples/demo_orig.flac")
    reference32 = reference32[:10 * fs32]
    if fs32 != 32000:
        raise ValueError("32 kHz reference expected")
    for row in read_json("hybrid_y_vs_legacy.json")["comparison"]:
        if row["source"] != "demo":
            continue
        rows.append(pair("32k_main_plus_secondary", "demo", row["case"], fs32, reference32,
                         row["baseline_file"], row["y_file"], row["baseline_sha256"],
                         row["y_sha256"], row["baseline_profile"], row["y_profile"]))

    reference48, fs48 = audio("samples/monitor/demo_orig48.flac")
    reference48 = reference48[:10 * fs48]
    if fs48 != 48000:
        raise ValueError("48 kHz reference expected")
    for row in read_json("monitor_y_vs_legacy.json")["comparison"]:
        if row["source"] != "demo":
            continue
        rows.append(pair("48k_single_main", "demo", row["case"], fs48, reference48,
                         row["baseline_file"], row["y_file"], row["baseline_sha256"],
                         row["y_sha256"], row["baseline_profile"], row["profile"]))

    report = {"description": "M/S component metrics from stored matched 10 s FLACs; low bands k=0..4, high bands k=5..6",
              "method": "orthonormal 6-level Haar; RMS level change is reconstructed/reference, not a perceptual quality score",
              "rows": rows}
    output = os.path.join(ROOT, "docs/results/y_stereo_components.json")
    temporary = output + ".tmp"
    with open(temporary, "w", encoding="utf-8") as stream:
        json.dump(report, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write("\n")
    os.replace(temporary, output)
    print(output, len(rows), "matched stereo comparisons")


if __name__ == "__main__":
    main()
