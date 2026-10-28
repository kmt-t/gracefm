#!/usr/bin/env python3
"""試聴音声の一式を検証し、索引 (samples/index.json) と samples/README.md を作る。"""
import hashlib
import json
from dataclasses import asdict
from pathlib import Path
import sys

import numpy as np
import soundfile as sf

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from tools.common import metrics, wavio
from gracefm.profiles import PROFILES
from tools.samples.make_samples import CASES, CN0_LIST, MATERIALS, SEC, SETS, cn, source_name
from tools.samples.sample_names import reference_name, sample_name

SOURCES = [
    ('piano', '"Emotional piano" by triangelx', 'https://commons.wikimedia.org/wiki/File:Emotional_piano.wav', 'CC0 1.0'),
    ('percussion', '"Ceramic Djembe" by RutgerMuller', 'https://commons.wikimedia.org/wiki/File:Ceramic_Djembe.wav', 'CC0 1.0'),
]


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def expected():
    """(素材, 形, 構成, 条件, ファイル名, サンプリング周波数) の一覧"""
    rows = []
    for material, _, _ in MATERIALS:
        for fs, form, mains, subs in SETS:
            src = source_name(material, form)
            for main in mains:
                rows.append((material, form, main, 'codec', sample_name(src, fs, main), fs))
                for sub in subs:
                    for case in CASES:
                        rows.append((material, form, main + (f'+{sub}' if sub else ''), case,
                                     sample_name(src, fs, main, case, sub=sub), fs))
            if form == 'mono' and fs == 32000:
                for case in CASES:
                    rows.append((material, form, 'FM', case, sample_name(src, fs, 'FM', case), fs))
    return rows


def build():
    rows = expected()
    folder = ROOT / 'samples'
    want = {r[4] for r in rows} | {reference_name(source_name(m, f), fs) for m, _, _ in MATERIALS for fs, f, _, _ in SETS}
    found = {p.name for p in folder.glob('*.flac')}
    if want != found:
        raise ValueError({'missing': sorted(want - found), 'unexpected': sorted(found - want)})
    entries = []
    for material, form, config, case, name, row_fs in rows:
        path = folder / name
        src = source_name(material, form)
        audio, fs = wavio.read(path)
        refpath = folder / reference_name(src, row_fs)
        reference, ref_fs = wavio.read(refpath)
        assert fs == ref_fs == row_fs and audio.shape == reference.shape and len(audio) == fs * SEC
        assert np.all(np.isfinite(audio))
        profiles = [asdict(PROFILES[n]) for n in config.split('+') if n in PROFILES]
        entries.append(dict(file=f'samples/{name}', sha256=digest(path), material=material, form=form,
                            reference_file=f'samples/{refpath.name}', reference_sha256=digest(refpath),
                            sample_rate_hz=fs, seconds=len(audio) / fs, channels=sf.info(path).channels,
                            configuration=config, condition=case, profiles=profiles,
                            snr_db=float(metrics.snr_db(reference, audio))))
    code = {str(p.relative_to(ROOT)): digest(p) for d in ('gracefm', 'tools') for p in sorted((ROOT / d).rglob('*.py'))}
    report = dict(description='10-second listening samples; decoded FLAC measurements, not RF capture',
                  expected_sample_count=len(rows), seed=1, code_sha256=code, samples=entries)
    destination = ROOT / 'samples' / 'index.json'
    destination.write_text(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + '\n')
    write_readme(entries)
    print(destination, len(entries), 'validated samples')


def write_readme(entries):
    by = {(e['material'], e['form'], e['configuration'], e['condition']): e for e in entries}
    lines = ['# サンプル音声（GraceFM）', '',
             'ファイル名の読み方は[命名規則](NAMING.md)。各10秒・32 kHzと48 kHz、劣化音は24bit FLAC。`tools/samples/make_samples.py` で生成し、'
             '`tools/samples/sample_catalog.py` で検証してこのファイルを書く。設定・測定値・SHA-256は[音源一覧JSON](index.json)。', '',
             '## マトリクス', '',
             '素材 3（demo・piano・percussion）× 形 2（モノラル・ステレオ）。モノラル形は (L+R)/2、ステレオ形は原音のまま。'
             '2系統は主系・副系とも独立のチャンネルで、電力を分け合わない（C/N0は同じ値）。', '',
             '| 軸 | 内容 |', '|---|---|',
             '| 32 kHz主系 | モノラル形: B200M・B200MY / ステレオ形: B200・B200Y |',
             '| 32 kHz副系 | なし / SUB50M |',
             '| 48 kHz主系 | モノラル形: M700M・M700MY / ステレオ形: M700・M700Y |',
             '| 48 kHz副系 | なし / SUB100-48K |',
             '| 条件 | コーデックだけ（副系なしのみ）、白色雑音 C/N0 ' + '・'.join(map(str, CN0_LIST)) +
             '、レイリーフェージング（C/N0 60）、主系の周波数だけ10dB低下（C/N0 66） |',
             '| アナログFM | 32 kHzのモノラル形だけ、上の通信路条件 |', '',
             '## 電波の強さ', '', '| C/N0 | C/N（180kHz） |', '|---|---|']
    for c in sorted(CN0_LIST, reverse=True):
        lines.append(f'| {c} dB-Hz | {cn(c):.1f} dB |')
    lines += ['', '66 dB-Hz は5m・室内の保守的な見積もり（SPEC 付録D）。通信路は白色雑音のみ、または系統ごとに独立なレイリーフェージング'
              '（時定数100ms、FMも同じ変動）、主系の周波数だけ10dB低下。同期・等化は理想で、FMのゴーストは含まない。', '']
    for fs, form, mains, subs in SETS:
        label = ('モノラル形' if form == 'mono' else 'ステレオ形') + f'・{fs // 1000} kHz'
        configs = [m + (f'+{s}' if s else '') for m in mains for s in subs] + (['FM'] if form == 'mono' and fs == 32000 else [])
        lines += [f'## {label}（波形SNR dB、保存したFLACと原音の差）', '']
        for material, _, _ in MATERIALS:
            lines += [f'### {material}', '', '| 構成 | ' + ' | '.join(['codec'] + list(CASES)) + ' |',
                      '|---|' + '---:|' * (1 + len(CASES))]
            for config in configs:
                cells = []
                for case in ['codec'] + list(CASES):
                    e = by.get((material, form, config, case))
                    cells.append('—' if e is None else f'[{e["snr_db"]:.1f}]({Path(e["file"]).name})')
                lines.append(f'| {config} | ' + ' | '.join(cells) + ' |')
            lines.append('')
    lines += ['## 原音と出典', '']
    for material, _, _ in MATERIALS:
        for fs, form, _, _ in SETS:
            lines.append(f'- [{source_name(material, form)} ({fs // 1000} kHz)]({reference_name(source_name(material, form), fs)})')
    lines += ['', '- `demo`：合成した試験信号（全帯域・ステレオ）']
    for _, title, url, lic in SOURCES:
        lines.append(f'- {title} — [Wikimedia Commons]({url})、{lic}')
    lines += ['', '加工したサンプルは [CC BY-NC 4.0](https://creativecommons.org/licenses/by-nc/4.0/)。']
    (ROOT / 'samples/README.md').write_text('\n'.join(lines) + '\n')


if __name__ == '__main__':
    build()
