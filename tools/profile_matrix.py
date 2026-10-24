#!/usr/bin/env python3
"""Generate/check the current profile matrix and derived frame budgets."""
import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from gracefm.codec import exp_range
from gracefm.profiles import PROFILES
from gracefm.txrx import Transmitter


def vector(values):
    return ', '.join(map(str, values))


def render():
    lines = ['# 現行プロファイル設定マトリクス', '',
             '`gracefm/profiles.py` の `PROFILE_MATRIX` から生成。更新は `python tools/profile_matrix.py`、一致確認は `--check`。アルゴリズムと測定条件は[技術論文](SPEC.md)を参照。', '',
             '全登録プロファイルに区間アッテネータを標準装備する。名前の数字は系列名であり、現在の実ビットレートは下表を参照。', '',
             '共通設定：64サンプル、Haar 6段、指数4bit/送信帯域、基本CRC-16とH1/H2用の高域CRC-16（該当帯域を送る場合のみ）、畳み込み符号 K=7・r=1/2。ヘッダは非暗号化24bit（カウンタ16bit）、暗号化32bit（カウンタ24bit）。ID 0・13～15は予約。副系SUBはQPSK、ステレオ差分Sは主系の階層QAMで送る。', '',
             '## ID・方式・伝送予算', '',
             '非暗号化の値。シンボル数にはプリアンブル16シンボルとY専用シンボルを含む。理論支持幅は `(1+β)Rs` で、99%占有帯域の実測値ではない。音声量には指数とアッテネータを含む。', '',
             '| ID | 名前 | fs kHz | M/S | 変調 / α | Y開始k | FEC上位bit/係数 | 音声 kbps | CRC本数 | 保護部CRC込 bit | FEC後 bit | 非保護デジタル bit | シンボル/フレーム | Rs ksym/s | RRC β / span | 理論支持幅 kHz |',
             '|---|---|---:|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---|---:|']
    budgets=[]
    for p in PROFILES.values():
        tx=Transmitter(p); l=tx.layout; ns=tx.nsym+16; rs=tx.symbol_rate()
        lines.append(f'| {p.pid} | {p.name} | {p.fs/1000:g} | {"M/S" if any(p.bits_s) else "M"} | {p.modulation} / {p.alpha:g} | {p.hybrid_start_k if p.hybrid else "—"} | {p.protect_k} | {p.audio_kbps():g} | {2 if l.has_high_crc else 1} | {l.n_prot_crc} | {l.n_coded} | {l.n_unp} | {ns} | {rs/1000:g} | {p.pulse_beta:g} / {p.pulse_span} | {rs*(1+p.pulse_beta)/1000:g} |')
        budgets.append(dict(profile=asdict(p), header_bits=l.header_bits, crc_count=2 if l.has_high_crc else 1,
                            protected_crc_bits=l.n_prot_crc,
                            fec_bits=l.n_coded, digital_unprotected_bits=l.n_unp,
                            symbols_per_frame=ns, symbol_rate=rs,
                            audio_kbps=p.audio_kbps(), theoretical_bandwidth_hz=rs*(1+p.pulse_beta)))
    lines += ['', '## 成分ごとの全設定', '',
              'ベクトルは `k=0…6`。M/Sの各行に同じ項目を表示する。アッテネータ区間長0はその帯域では不使用。副系も各成分の最高送信帯域に配置し、4係数を基本とする（係数数が4未満ならその係数数）。B200HのM最高域だけは調整済みの8係数区間を維持。Yの高域Mは各帯域8区間。', '',
              '基本層はFEC保護bitを含む。係数別の追加割当も基本層として数え、強い位置に拡張層が暗黙に入り込むことはない。追加欄の `k:j +1` は、その帯域の係数j（0始まり）だけ基本層を1bit増やす。Y高域Mの `H` は専用シンボルで、デジタル層分割の対象外。QPSKは層分割なし。', '',
              '| ID | 名前 | 成分 | 全幅 | 基本層 | 拡張層 | 基本層追加 | アッテネータ区間長 | 指数幅 | 指数最小値 |',
              '|---|---|---|---|---|---|---|---|---|---|']
    for p in PROFILES.values():
        for ch,bits in [('M',p.bits_m),('S',p.bits_s)]:
            if not any(bits):
                lines.append(f'| {p.pid} | {p.name} | {ch} | — | — | — | — | — | — | — |'); continue
            base=[]; ext=[]
            for k,b in enumerate(bits):
                if p.hybrid and ch in p.hybrid_channels and k>=p.hybrid_start_k:
                    base.append('H');ext.append('H')
                elif p.layered:
                    base.append(p.base_bits(ch,k));ext.append(b-p.base_bits(ch,k))
                else: base.append('—');ext.append('—')
            extra=', '.join(f'{k}:{j} +1' for c,k,j in p.base_extra if c==ch) or '—'
            exps=[p.exponent_bits(ch,k) if b else '—' for k,b in enumerate(bits)]
            offsets=[exp_range(k,b,p,ch)[0] if b else '—' for k,b in enumerate(bits)]
            lines.append(f'| {p.pid} | {p.name} | {ch} | {vector(bits)} | {vector(base)} | {vector(ext)} | {extra} | {vector(p.attenuator_group(ch,k) for k in range(7))} | {vector(exps)} | {vector(offsets)} |')
    lines += ['', '追加基本層の対象係数では、その分だけ拡張層が減る。総仮数幅は変えない。YはMのみ、標準8bit（位相2bit＋半径6bit）、半径間隔は `0.08 * 7.5 / 31.5`。Yの暗号化は未対応。受信ポストフィルタは任意、標準反復4回でMのみ。', '',
              'フレーム予算は現行設定から計算した値。', '']
    return '\n'.join(lines), json.dumps(dict(profiles=budgets), ensure_ascii=False, indent=2)+'\n'


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check',action='store_true')
    args=parser.parse_args()
    md,data=render()
    for path,content in [(ROOT/'docs/PROFILES.md',md),(ROOT/'docs/results/profile_matrix.json',data)]:
        if args.check:
            if not path.exists() or path.read_text()!=content:
                raise SystemExit(f'out of date: {path}')
        else: path.write_text(content)
    print('profile matrix matches implementation' if args.check else 'profile matrix generated')

if __name__=='__main__': main()
