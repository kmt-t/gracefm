# GraceFM

近距離モニター・放送向けの低遅延デジタル音声伝送方式と、整数演算のみで動く Python 参照実装です（実RF・実時間動作は未実証）。

64 サンプル／フレームの短い帯域分割（Haar または LeGall 5/3）、FEC 付きヘッダと係数部の分離、階層 16QAM / QPSK / Y 方式（QASK）、任意の 2 系統融合と LPC 補間により、受信条件に応じた音質低下を扱います。

> [!NOTE]
> 派生プロジェクト **[gracefm-ultra](../gracefm-ultra)** は、本家 GraceFM と同一の送信ビット列・フレーム形式・全 22 プロファイルを受け取り、PC（RTL-SDR など）上で Rust + ONNX Runtime（MendNet / PostNet）により浮動小数点で高性能復号する受信実装です。本リポジトリはハードウェア（Zynq-7010 等）向けの整数参照実装と方式仕様の正本を扱います。

## 現行プロファイル

全登録プロファイルに区間アッテネータを標準装備しています。名前の数値は系列名で、実ビットレートや詳細パラメータは [プロファイル設定マトリクス](docs/PROFILES.md) を参照してください。

| 用途 | 構成 | QPSK（副系） | 階層16QAM（主系） | 階層16QAM＋Y（主系） |
|---|---|---|---|---|
| 32 kHz 主系 | モノラル | — | 1: B200M | 3: B200MY |
| 32 kHz 主系 | ステレオ | — | 2: B200 | 4: B200Y |
| 32 kHz 副系 | モノラル | 5: SUB50M | — | — |
| 32 kHz 副系 | ステレオ | 6: SUB100 | — | — |
| 48 kHz 主系 | モノラル | — | 7: M700M | 9: M700MY |
| 48 kHz 主系 | ステレオ | — | 8: M700 | 10: M700Y |
| 48 kHz 副系 | ステレオ | 11: SUB100-48K | — | — |

- 各プロファイルには、同じ ID のまま帯域分割をブロックをまたぐ LeGall 5/3 に替えた `-L` 版（例: `B200M-L`）があり、全 22 プロファイルとなります（ID 0・12〜15 は予約）。
- 末尾 `M` はモノラル（なしはステレオ）、`Y` は高域 M/S を 1 係数 1 複素シンボルで送る QASK 方式、`SUB` は別周波数で冗長伝送する副系を表します。
- 最小の一定再生遅延（処理時間・フィルタ遅延 0）は 32 kHz で 4 ms、48 kHz で約 2.667 ms です（`-L` は先読み 30 サンプル分増加）。

## ドキュメント

| 文書 | 内容 |
|---|---|
| [docs/SPEC.md](docs/SPEC.md) | 方式仕様（帯域分割、量子化、フレーム形式、変調、受信・融合・PLC・等化器、遅延モデル） |
| [docs/EVALUATION.md](docs/EVALUATION.md) | 評価・測定結果（占有帯域、16 bit PCM 換算、ダイナミックレンジ、`-L` 比較、設計トレードオフ） |
| [docs/PROFILES.md](docs/PROFILES.md) | 全 22 プロファイルの設定マトリクスと伝送予算（`gracefm/profiles.py` から自動生成） |
| [docs/SYMBOLS.md](docs/SYMBOLS.md) | フレーム内のシンボル形式・ビット配置（`gracefm/layout.py` から自動生成） |
| [docs/FIXED.md](docs/FIXED.md) | Zynq-7010 DSP48E1 向けの固定小数点仕様・ビット幅・CPU/DSP 分担 |
| [docs/COMPARISON.md](docs/COMPARISON.md) | FM・aptX・HE-AAC・DRM+ との比較条件・評価結果・回路規模見積もり |
| [docs/RTP.md](docs/RTP.md) | IP 網伝送向け GraceFM/RTP ペイロード形式の設計（実装・評価なし） |
| [samples/README.md](samples/README.md) | 現行設定で生成した試聴音源一覧（命名規則は [samples/NAMING.md](samples/NAMING.md)、測定値・ハッシュは [samples/index.json](samples/index.json)） |

## 使い方

```sh
pip install -r requirements.txt
python tools/sim/codec_wav.py 入力.wav 出力.wav --profile B200
python tools/sim/sim_link.py 入力.wav 出力.wav --profile B200M --snr 8 --single
python tools/eval/fetch_lossless_benchmark_audio.py  # 原音を eval_audio/lossless/ へ取得（試料の再生成と評価に必要）
python tools/samples/regenerate_samples.py     # 試聴音源・索引・一覧を一括再生成（評価値は作り直さない）
python tools/samples/sample_catalog.py --check # 試聴音源が索引と今のコードに一致するかを確認
python tools/report/profile_matrix.py          # 設定表と計算予算を更新
python tools/report/profile_matrix.py --check  # 実装との一致を確認
python -m pytest                               # テスト
```

評価を実行するツールは現行プロファイル名で動作します。各ツールの `--help` を参照してください。

## 構成

- `gracefm/`：プロファイル、帯域分割・量子化、FEC、変復調、フレーム配置、2 系統融合、PLC、等化器、IIR・出力段、暗号化、時刻モデル。
- `tools/`：`sim/`（WAV 変換・通信路シミュレーション）、`report/`（設定表・シンボル配置・スペクトル・回路見積もり生成）、`samples/`（試聴音源の生成と検証）、`eval/`（評価）、`gen/`（定数表生成）。
- `tests/`：プロファイル、固定小数点幅、FEC、基本層、LeGall 5/3、Y 方式、等化器、送受信の検証。
- `docs/`：仕様書、設定表、図表、測定結果 JSON。
- `samples/`：現行仕様で生成した試聴音源と出典。

## ライセンス

非商用は無料。商用利用は別途ライセンスが必要（著作権者に問い合わせ）。

| 対象 | ライセンス |
|---|---|
| ソースコード（`gracefm/`、`tools/`、`tests/`） | [PolyForm Noncommercial License 1.0.0](LICENSE)。`NOTICE` の表示を残すこと |
| 文書・図・評価結果 | CC BY-NC 4.0 |
| 加工サンプル音声 | CC BY-NC 4.0。原曲のライセンス・出典は[samples/README.md](samples/README.md)を参照 |
