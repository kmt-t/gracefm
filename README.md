# GraceFM

近距離モニター・放送向けの低遅延音声伝送方式とPython参照実装。短いHaarフレーム、重要ビットのFEC保護、階層変調、任意の2系統融合で、受信条件に応じた音質低下を扱う。実RF・実時間動作は未実証。

## 現行プロファイル

**区間アッテネータは全主系・副系の標準機能。** 有無による派生を廃止し、IDを再採番した。名前の数値は系列名で、実ビットレートは設定マトリクスを参照。

| 用途 | 構成 | QPSK | 階層16QAM | QPSK＋Y | 階層16QAM＋Y |
|---|---|---|---|---|---|
| 32kHz主系 | モノラル | — | 1: B200MH | — | 3: B200MHY |
| 32kHz主系 | ステレオ | — | 2: B200H | — | 4: B200Y、5: B200HY |
| 32kHz副系 | モノラル | 6: SUB50M | — | — | — |
| 32kHz副系 | ステレオ | 7: SUB100 | — | — | — |
| 48kHz主系 | ステレオ | — | 8: M700、9: M700H | — | 10: M700Y、11: M700HY |
| 48kHz副系 | ステレオ | 12: SUB100-48K | — | — | — |

`SUB` は別周波数で送る副系の名前で、ステレオ差分成分 `S=(L-R)/2` とは異なる。副系は雑音耐性を優先してQPSK、ステレオ主系のSは階層16QAMを使う。M700とM700Hはともに階層16QAMで、Hは高い音声ビット割当を区別する。`SUB100-48K` は48 kHz主系用の約100 kbpsステレオ副系。

`—` は未定義の組合せで、自動生成しない。全登録プロファイルに区間アッテネータを標準装備する。

### 全設定と基本層・拡張層

**[プロファイル設定マトリクス](docs/PROFILES.md)** に、ID、サンプリング周波数、変調、FEC、M/Sの仮数全幅・基本層・拡張層、係数別昇格、区間アッテネータ、指数幅・オフセット、RRC、伝送予算を同じ項目で掲載する。設定元 `gracefm/profiles.py` から自動生成し、表と実装の不一致をチェックできる。

- 階層方式の基本層は強い象限位置、拡張層は弱い振幅位置に置く。基本層幅はFEC保護の上位bitを含み、基本層全体をFEC保護する意味ではない。
- 強い位置に余った1bitは、係数別の `base_extra` 設定で次位bitを基本層へ昇格する。B200HYはM帯域4の係数0、M700HはM帯域6の係数0、M700HYはS帯域0の係数0。暗黙の拡張層流入はない。
- 32 kHzのB200Y/B200HYはS基本層が送信帯域ごとに1bitで、各係数の上位1bitをFEC経由で強い位置へ置く。次位bitは弱い位置へ送る。48 kHzのM700HYはS基本層が `1,1,1,1,1,2,2` で、最低域Sの係数0も1bit昇格する。
- Yの高域Mは8bitの専用位相・半径シンボルであり、通常デジタル層の区分を適用しない。QPSKには音声の基本層／拡張層の区分がない。
- 副系は別周波数で送る独立した音声ストリームで、M/SのS成分や拡張層とは別物。副系のアッテネータは各成分の最高送信帯域に置く。詳細な区間長は設定マトリクス参照。

## 仕様と検証状況

[技術論文](docs/SPEC.md)にHaar量子化、変調、FEC、欠損処理、フィルタ、フレーム形式、ビットレートと占有帯域をまとめた。ID 0・13～15は予約。

64サンプル／フレーム。処理時間・フィルタ遅延0の伝送時刻モデルは32kHzで4ms、48kHzで約2.667ms。送受信RRC・等化器・実処理・ADC/DAC・同期取得の遅延は別途必要。実装はオフラインの配列処理であり、実機の遅延保証ではない。

高域の保護bitとその他の保護bitは別々のCRC-16で検査する。基本CRC不一致はフレーム欠落、高域CRCだけの不一致はH1/H2を消去して低中域を採用する。32 kHz主系の占有帯域は[測定結果](docs/SPEC.md)を参照。実RF・実時間動作は未実証。

[FM・aptX・DAB+比較](docs/COMPARISON.md)は方式ごとに条件と未測定項目を明示する。Y系の係数配置と伝送予算は[現行仕様](docs/SPEC.md)と[設定マトリクス](docs/PROFILES.md)を参照。

[試聴音源](samples/README.md)は標準アッテネータを含む現行設定で再生成する。ファイル名は[命名規則](samples/NAMING.md)に統一し、現行音源だけを掲載する。[全音源の設定・測定値・ハッシュ](docs/results/samples.json)を参照。

## 使い方

```sh
pip install -r requirements.txt
python tools/codec_wav.py 入力.wav 出力.wav --profile B200H
python tools/sim_link.py 入力.wav 出力.wav --profile B200MH --snr 8 --single
python tools/regenerate_samples.py     # 現行音源・評価値・試聴ページを一括再生成（評価依存が必要）
python tools/profile_matrix.py          # 設定表と計算予算を更新
python tools/profile_matrix.py --check  # 実装との一致を確認
python tests/test_profiles.py
python tests/test_gracefm.py
python tests/test_hybrid.py
python tests/test_equalizer.py
```

評価を実行するツールは現行プロファイル名で動作する。音質評価の追加依存は `requirements-eval.txt`。音源・試聴評価JSON・試聴ページは現行版へ置き換える。各ツールの `--help` を参照。

## 構成

- `gracefm/`：プロファイル・音声符号化・変復調・FEC・融合・PLC・時刻モデル。
- `tools/`：WAV変換、シミュレーション、設定表生成、評価。
- `tests/`：プロファイル、アッテネータ保護、実配置、送受信、等化の検証。
- `docs/`：現行仕様、設定表、評価結果。
- `samples/`：現行仕様で生成した試聴音源と出典。

## ライセンス

非商用は無料。商用利用は別途ライセンスが必要（著作権者に問い合わせ）。

| 対象 | ライセンス |
|---|---|
| ソースコード（`gracefm/`、`tools/`、`tests/`） | [PolyForm Noncommercial License 1.0.0](LICENSE)。`NOTICE` の表示を残すこと |
| 文書・図・評価結果 | CC BY-NC 4.0 |
| 加工サンプル音声 | CC BY-NC 4.0。原曲のライセンス・出典は[samples/README.md](samples/README.md)を参照 |
