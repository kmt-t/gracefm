#!/usr/bin/env python3
"""Validate the complete current listening set and rebuild its manifest/indexes."""
import hashlib
import json
import os
from pathlib import Path
import sys
from dataclasses import asdict

import numpy as np
import soundfile as sf

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from gracefm import metrics, wavio
from gracefm.profiles import PROFILES
from sample_names import sample_name, reference_name


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def expected_files():
    from make_hybrid_y_samples import filename_for as hybrid, CASES
    from make_monitor_y_samples import filename_for as monitor, PAIRS
    from make_hires_y_probe import PAIRS as probe_pairs
    result = set()
    for source in ('demo', 'fishin', 'vibeace'):
        mono = source != 'demo'
        main, base, sub = ('B200MH', 'B200M', 'S50M') if mono else ('B200H', 'B200', 'S100')
        names = [sample_name(source, 32000, main), sample_name(source, 32000, base),
                 sample_name(source, 32000, base, postfilter=False)]
        for case in ('awgn80', 'awgn66', 'awgn60', 'awgn57', 'awgn54', 'rayleigh60', 'main_minus10db66'):
            names.append(sample_name(source, 32000, main, case, sub=sub))
            if mono: names.append(sample_name(source, 32000, 'FM', case))
        result.update('samples/' + n for n in names)
        for profile, cases in [('M700', ('codec', 'awgn70', 'awgn65')),
                               ('M700H', ('codec', 'awgn80', 'awgn75', 'awgn70', 'awgn65')),
                               ('M700H-base', ('codec',))]:
            result.update('samples/monitor/' + monitor(source, profile, case) for case in cases)
        result.update('samples/hybrid_y/' + hybrid(source, main + 'Y', case) for case in CASES)
        for profile, (_, cn0s) in PAIRS.items():
            result.update('samples/monitor_y/' + monitor(source, profile, case)
                          for case in ('codec', 'ideal', *(f'awgn{c}' for c in cn0s)))
    for base, hybrid_name, cn0s in probe_pairs:
        for profile in (base, hybrid_name):
            cases = ('codec', *(f'awgn{c}' for c in cn0s)) + (('ideal',) if profile == hybrid_name else ())
            result.update('samples/monitor_y/' + monitor('hires_probe', profile, case) for case in cases)
    for source in ('demo', 'hires_probe'):
        for bits in (10, 12):
            result.update('samples/monitor_y/' + monitor(source, f'M700HY-R{bits}', case)
                          for case in ('codec', 'awgn80', 'awgn75', 'awgn70', 'awgn65'))
    for cn0 in (80, 75, 70, 65):
        result.add('samples/monitor/' + sample_name('demo', 48000, 'M700H', f'awgn{cn0}', sub='S100-48K'))
    return result


def profile_for(name):
    if name == 'M700H-base':
        return PROFILES['M700H']
    if name.startswith('M700HY-R'):
        from eval_m700hy_radius_precision import variant
        return variant(int(name.split('-R')[1]))
    return PROFILES[name]


def build():
    expected = expected_files()
    found = {str(p.relative_to(ROOT)) for p in (ROOT / 'samples').rglob('*.flac') if '__reference.' not in p.name}
    if expected != found:
        raise ValueError({'missing': sorted(expected-found), 'unexpected': sorted(found-expected)})
    measurements_by_file = {}
    for stem in ('hybrid_y_samples', 'monitor_y_samples', 'monitor_y_hires_probe',
                 'monitor_y_radius_precision', 'secondary_monitor_samples'):
        report = json.loads((ROOT/'docs/results'/(stem+'.json')).read_text())
        for row in report.get('samples', report.get('comparison', [])):
            matching = [name for name in expected if Path(name).name == row['file']]
            assert len(matching) == 1, (stem, row['file'])
            assert digest(ROOT/matching[0]) == row['sha256'], (stem, row['file'])
            measurements_by_file[row['file']] = row.get('measurements', row.get('variant_measurements'))
    entries = []
    for relative in sorted(expected):
        path = ROOT / relative
        source, rate, config, condition = path.stem.split('__')
        audio, fs = wavio.read(path)
        refpath = path.with_name(reference_name(source, fs))
        reference, ref_fs = wavio.read(refpath)
        assert fs == int(rate[:-1])*1000 == ref_fs and audio.shape == reference.shape
        assert len(audio) == fs*10 and np.all(np.isfinite(audio))
        profiles = []
        if config != 'FM':
            for name in config.split('+'):
                p = profile_for(name)
                assert p.experimental_tag == 3
                for ch, bits in (('M', p.bits_m), ('S', p.bits_s)):
                    assert not any(bits) or any(p.attenuator_bits(ch,k) for k in range(p.nbands))
                profiles.append(asdict(p))
        entries.append(dict(file=relative, sha256=digest(path), source=source,
                            reference_file=str(refpath.relative_to(ROOT)), reference_sha256=digest(refpath),
                            sample_rate_hz=fs, seconds=len(audio)/fs, channels=sf.info(path).channels,
                            configuration=config,
                            condition=condition, profiles=profiles,
                            detailed_measurements=measurements_by_file.get(path.name),
                            snr_db=float(metrics.snr_db(reference, audio))))
    covered = {p['name'] for row in entries for p in row['profiles'] if p['name'] in PROFILES}
    assert covered == set(PROFILES), ('uncovered profiles', set(PROFILES)-covered)
    code = {str(p.relative_to(ROOT)):digest(p) for folder in ('gracefm','tools')
            for p in sorted((ROOT/folder).glob('*.py'))}
    report = dict(description='Current 10-second listening samples; decoded FLAC measurements, not RF capture',
                  expected_sample_count=len(expected), seed=1, code_sha256=code,
                  base_comparison_note='M700H-base retains the actual basic layer including base_extra; only extension posterior probabilities are set to 0.5',
                  samples=entries)
    destination=ROOT/'docs/results/samples.json'
    destination.write_text(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False)+'\n')
    from make_samples import README_TAIL
    for folder, title in [('samples','32 kHz 主系・副系'),('samples/monitor','48 kHz モニター'),
                          ('samples/hybrid_y','32 kHz Y系'),('samples/monitor_y','48 kHz Y系・高域試験')]:
        directory=ROOT/folder
        rel=lambda target: os.path.relpath(ROOT/target, directory)
        lines=[f'# 現行サンプル音声 — {title}', '',
               '**全デジタル主系・副系に標準アッテネータを含む現行設定の音声です。** 各10秒。保存したFLACを読み戻して波形SNRを再測定しています。', '',
               f'[命名規則]({rel("samples/NAMING.md")}) · [設定表]({rel("docs/PROFILES.md")}) · [全音源の設定・測定値・SHA-256]({rel("docs/results/samples.json")})', '',
               '32 kHzの2系統は電力50:50。48 kHzの `M700H+S100-48K` は75:25。それ以外の48 kHz音声は主系1系統です。`codec` は通信路なし、`ideal` は雑音なしのシンボル送受信。AWGN等は同期既知のシミュレーションです。', '',
               '`M700H-base` は実際の基本層を保持し、拡張層の事後確率だけを0.5にした比較音源です。係数別昇格1bitと標準アッテネータを含みます。`R10` / `R12` はY仮数幅の比較条件です。', '',
               '波形SNRは原音との差であり、聴感の点数ではありません。', '',
               '| 音源 | 構成 | 条件 | 試聴 | 波形SNR dB |', '|---|---|---|---|---:|']
        for row in entries:
            p=Path(row['file'])
            if str(p.parent)!=folder:continue
            lines.append(f'| {row["source"]} | {row["configuration"]} | {row["condition"]} | [再生]({p.name}) | {row["snr_db"]:.2f} |')
        lines += ['', '## 原音', '']
        for p in sorted(directory.glob('*__reference.flac')):
            lines.append(f'- [{p.stem.split("__")[0]}]({p.name})')
        if folder=='samples':
            lines += ['', '## その他の試聴', '', '[48 kHzモニター](monitor/README.md) · [32 kHz Y系](hybrid_y/README.md) · [48 kHz Y系・高域試験](monitor_y/README.md)', '', README_TAIL]
        (directory/'README.md').write_text('\n'.join(lines)+'\n')
    print(destination, len(entries), 'validated samples')


if __name__ == '__main__':
    build()
