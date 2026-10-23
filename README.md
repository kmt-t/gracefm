# GraceFM

FM帯で、理想時刻モデルの伝送遅延4msを基準とし、受信電力の低下に応じて音質がなだらかに劣化する（graceful degradation）デジタル音声伝送方式。送受信フィルタと等化器を使う場合は、その遅延を加算する。仕様書とリファレンス実装（Python パッケージ `gracefm`）。

## 仕様

| 項目 | 放送（FM放送の代替・災害時） | モニター（据え置き機・近距離） |
|---|---|---|
| 構成 | 主系 B200H-A4 / B200MH-A4 ＋ 副系 S100 / S50M | M700H |
| 伝送込みの遅延（処理時間・フィルタ遅延0） | 4.00ms | 2.67ms |
| サンプリング / 音声帯域 | 32kHz / 16kHz | 48kHz / 24kHz |
| 音声ビットレート | 主系 536 / 474kbps（基本層 206 / 198）＋ 副系 95 / 46kbps | 854kbps（基本層329） |
| 変調 | 主系 階層16QAM、副系 QPSK | 階層16QAM |
| 符号化 | 各チャンネル64サンプル/フレーム、Haar 6詳細帯域＋低域近似1群を個別量子化（指数4bit/群）。最高域の区間アッテネータはステレオ M が8係数ごと、S が4係数ごと、モノラル M が4係数ごと | 各チャンネル64サンプル/フレーム、Haar 6詳細帯域＋低域近似1群を個別量子化（指数4bit/群） |
| 誤り訂正 | 指数・仮数の上位1bitと主系のアッテネータ（畳み込み符号 K=7 r=1/2 ＋フレームCRC-16） | 指数・仮数の上位1bit（同左） |
| 占有帯域（99%） | 主系 182 / 167kHz＋ 副系 104 / 65kHz | 302kHz |
| 冗長性 | 2周波数・半ブロックずらし・帯域ごとに逆分散重みで融合 | なし |
| 欠落時 | 片方の欠落は他方で補う。両方欠けたら LPC で外挿（30ms まで） | LPC で外挿（30ms まで） |
| 受信処理 | 軟判定の復号、量子化区間への射影による量子化雑音の除去、融合、欠落の外挿（広義のカルマンフィルタとして構成） | 同左（融合なし） |
| 暗号化 | AES-128-CTR（任意。放送評価では無効） | AES-128-CTR（任意） |

### プロファイルごとの仮数ビット割当

各列は **低域近似 `k=0`、6つの詳細帯域 `k=1…6`** の順で、値は1係数あたりの仮数ビット数。ステレオは `M=(L+R)/2` と `S=(L−R)/2` を個別に符号化する。`0` はその成分を送らず、`—` はモノラルのため S 成分がないことを表す。M 基本層が `—` のプロファイルは階層化しない。区間アッテネータのビット数はこの表に含めない。比較用プロファイルを含む詳しい一覧と各係数群の周波数範囲は[仕様書の付録B](docs/SPEC.md#mantissa-allocation)に示す。

Y系の高域Mは標準8 bitで、表の基本層幅の高域欄はデジタル配置には使わない。

| プロファイル | M 全幅 `k=0…6` | S 全幅 `k=0…6` | M 基本層 `k=0…6` | S 基本層 `k=0…6` |
|---|---|---|---|---|
| B200H-A4（放送ステレオ主系） | 16, 16, 16, 13, 10, 7, 7 | 14, 12, 11, 8, 7, 7, 7 | 12, 11, 9, 7, 4, 2, 2 | 7, 6, 5, 3, 2, 2, 2 |
| B200MH-A4（放送モノラル主系） | 16, 16, 16, 16, 16, 15, 13 | — | 9, 9, 9, 9, 8, 6, 4 | — |
| B200HY-A4（実験用ステレオ主系） | 16, 16, 16, 13, 10, 8, 8 | 14, 12, 11, 8, 7, 7, 7 | 12, 11, 5, 3, 1, 2, 2 | 1, 1, 1, 1, 1, 2, 2 |
| B200MHY-A4（実験用モノラル主系） | 16, 16, 16, 16, 16, 8, 8 | — | 9, 9, 9, 9, 8, 6, 4 | — |
| S100（放送ステレオ副系） | 10, 9, 8, 6, 4, 2, 0 | 6, 5, 4, 2, 0, 0, 0 | — | — |
| S50M（放送モノラル副系） | 8, 7, 6, 5, 3, 0, 0 | — | — | — |
| M700H（モニター主系） | 16, 16, 16, 15, 12, 9, 7 | 16, 13, 11, 9, 9, 7, 7 | 11, 10, 9, 8, 6, 3, 2 | 7, 5, 4, 3, 3, 2, 2 |
| M700Y（実験用48kHz QPSK主系） | 16, 14, 13, 12, 11, 8, 8 | 12, 9, 8, 9, 7, 5, 3 | — | — |
| M700HY（実験用48kHz階層16QAM主系） | 16, 16, 16, 15, 12, 8, 8 | 16, 13, 11, 9, 9, 7, 7 | 11, 10, 5, 4, 3, 3, 2 | 1, 1, 1, 1, 1, 2, 2 |
| S100W（モニター副系） | 9, 8, 7, 6, 4, 0, 0 | 5, 4, 3, 0, 0, 0, 0 | — | — |

実験用の高域位相・振幅ハイブリッド主系は[Y系の設計・評価報告](docs/HYBRID_Y_PAPER.md)と[音質評価レポート](docs/HYBRID_Y_AUDIO_QUALITY.md)にまとめる。32kHz版はMの4kHz以上、48kHzのM700系はMの6kHz以上を1係数/複素シンボルに載せる。32kHz Y主系のMは4〜8kHzと8〜16kHzに各8bitの区間アッテネータを持ち、FECで保護する。Sの仮数幅・指数・区間アッテネータは同じ周波数の従来主系と共通である。階層16QAMのY主系は高域Sの次位bitを強い位置、低域Mの一部の下位bitを弱い位置へ配置する。受信後のポストフィルタはM側だけに適用し、Sは軟復号係数をそのままHaar逆変換する。ポストフィルタ自体はソフトウェア復号器の任意機能で、送信フレームとFECは変わらない。実験用主系のAES-CTR暗号化は未対応として明示的にエラーにする。

新方式Y系の10秒試聴音源は[音源一覧](samples/hybrid_y/README.md)から再生できる。

48kHzモニター用の `M700Y` / `M700HY` の試聴音源は[モニターY系の音源一覧](samples/monitor_y/README.md)にまとめる。

## 性能

[公開ライセンスのロスレス PCM WAV 3素材](docs/QUALITY_BENCHMARK.md)を用い、`B200MH-A4`＋`S50M` とアナログFMを同じ受信電力で比較する。以下は白色雑音での **波形SNR [dB] / ViSQOL Audio MOS-LQO**。ViSQOL は聴感品質の予測値で、実際の聴取試験の点数ではない。

| 素材 | C/N0 | GraceFM | FM |
|---|---:|---:|---:|
| ピアノ | 54dB-Hz | 12.84 / 2.262 | 7.25 / 1.665 |
| ピアノ | 80dB-Hz | 70.76 / 4.728 | 54.03 / 4.138 |
| 打楽器 | 54dB-Hz | 13.42 / 2.639 | 2.82 / 1.667 |
| 打楽器 | 80dB-Hz | 70.20 / 4.731 | 48.89 / 3.829 |
| ギター | 54dB-Hz | 13.55 / 2.707 | 6.21 / 1.855 |
| ギター | 80dB-Hz | 72.45 / 4.731 | 45.14 / 4.310 |

- 54・80dB-Hz では波形SNR・ViSQOLとも3素材で GraceFM が高い。中間の60・66dB-Hzでは素材や指標ごとに優劣が分かれる。全条件は[音質ベンチマーク](docs/QUALITY_BENCHMARK.md)を参照。
- 静的な反射波1本と送受信 RRC を含む評価では、11タップの線形等化器により、80dB-Hz の反射波あり21条件すべてで同じ直接波 C/N0 の FM より波形SNRが9.37〜25.84dB高い。66dB-Hz では21条件中18条件で高い。反射波なしでは等化の効果はほぼなく、強い逆位相の反射を等化なしで受けると保護部にも失敗する条件がある。条件別の数値は[静的反射波の評価](docs/QUALITY_BENCHMARK.md)を参照。
- 同じ3素材でコーデックだけを比較した結果も掲載した。A4 は音声474kbps、MP3 は CBR 128・192・320kbps。無線総レートは A4 主系604kbps、副系を含め722kbps。
- ステレオ主系 B200H-A4 と aptX・aptX HD の同一音源での波形SNR / ViSQOL 比較は[音質ベンチマーク](docs/QUALITY_BENCHMARK.md#aptx-benchmark)に掲載した。共通16kHz帯域と元音源帯域を分けて評価している。
- A4 の1フレーム（2ms）では保護部132bit、仮数全量912bit（うち非保護848bit）。保護部：非保護仮数は **1：6.42**。内訳と量子化特性は[仕様書5.8節](docs/SPEC.md)に示す。
- `B200MH-A4`（プロファイルID 14）は帯域ごとの指数4bitと固定オフセット、4係数ごとのアッテネータ8bitを使用する。
- `B200H-A4`（プロファイルID 10）は M/S ジョイントステレオで、最高域の M を8係数ごと（計4bit）、S を4係数ごと（計8bit）に区切る。`A4` は S 側の4係数区間を表す。音声536kbps、主系無線総レート716kbps。RRC ロールオフ0.10で99%占有帯域は約182kHz、−30dB幅は約197kHz。
- ステレオ・モニターを含む音声サンプルと保存後の波形SNRは [samples/README.md](samples/README.md) に記録した。

## 制約

- 白色雑音・フェージングの基準評価は同期済みシンボル列のモデル。静的な反射波1本の評価では送受信 RRC の等価応答と訓練済みの線形 MMSE 等化器を使う。どちらもシンボル時刻・搬送波位相の同期は理想
- 未評価：FMステレオとの比較、複数反射波・移動受信、実RF
- 処理はオフラインの配列処理（実時間ではない）。4.00ms はフィルタ遅延を0とした時刻モデル値。最大4シンボル先読みの静的等化器と送受信 RRC を含めると、モノラル放送の定常受信は4.339ms、ステレオ放送は4.212ms（処理時間と初期較正時間を除く）

## 使い方

```sh
pip install -r requirements.txt

python tools/codec_wav.py 入力.wav 出力.wav --profile B200H-A4         # コーデックだけ
python tools/sim_link.py 入力.wav 出力.wav --profile B200MH-A4 --snr 8 --single  # 主系1系統の簡易通信路
python tools/make_samples.py --workers 3                            # ステレオ・モノラル・モニター音声を生成
python tools/make_samples.py --monitor-only --workers 3             # 48kHzの比較用モニター音声だけ再生成
pip install -r requirements-eval.txt                                # 聴感指標を使う評価だけ追加
python tools/fetch_lossless_benchmark_audio.py                      # 公開ライセンスの PCM WAV を Git 管理外へ取得
python tools/eval_lossless_benchmark.py                             # MP3 と FM を同じ原音で比較
python tools/eval_aptx_benchmark.py                                # B200H-A4 と aptX・aptX HD のステレオ比較
python tools/eval_lossless_benchmark.py --channels rayleigh,fade10 --cn0 60,66 --skip-codec --json docs/results/lossless_impairments.json
python tools/eval_ghost.py --seconds 5 --cn0 66,80 --workers 3 --json docs/results/ghost_eval.json
python tools/fig_lossless_benchmark.py
python tools/fetch_exp_audio.py                                 # 公開ライセンス音源をGit管理外へ取得
python tools/eval_attn_layout.py --seconds 3 --headroom-db 6 --skip-perceptual --skip-link --json docs/results/attn_layout_scan.json
python tools/validate_attn_headroom.py                           # 帯域別オフセットの保留検証
python tools/validate_lossless_layout.py                           # ロスレス音源で指数幅・固定オフセットを評価
python tools/eval_stereo_attn.py --perceptual-seconds 2 --rf-seconds 4 --json docs/results/stereo_attn_eval.json
python tools/eval_hybrid.py --seconds 3                          # 実験用高域変調の帯域・音質・ViSQOL比較
python tests/test_gracefm.py                                        # テスト（または python -m pytest tests/）
python tests/test_hybrid.py                                         # 実験用高域変調のテスト
```

評価ツール：

| ツール | 内容 | SPEC の節 |
|---|---|---|
| `tools/eval_lossless_benchmark.py` | Git 管理外のロスレス音源で採用方式・FM・MP3 を比較 | [音質ベンチマーク](docs/QUALITY_BENCHMARK.md) |
| `tools/eval_aptx_benchmark.py` | 同じ音源で B200H-A4・aptX・aptX HD のステレオ符号化を比較 | [音質ベンチマーク](docs/QUALITY_BENCHMARK.md) |
| `tools/eval_ghost.py` | 静的な反射波1本で FM・等化なし・等化ありを比較 | [音質ベンチマーク](docs/QUALITY_BENCHMARK.md) |
| `tools/eval_final.py` | 採用構成とアナログFMの比較 | 5.2 |
| `tools/eval_am.py` | アナログAM との比較 | 5.2 |
| `tools/eval_attn_layout.py`、`tools/validate_attn_headroom.py` | 指数幅・固定オフセット・区間アッテネータの感度分析 | [仕様書5.8節](docs/SPEC.md) |
| `tools/validate_lossless_layout.py` | ロスレス音源による指数幅・固定オフセット・アッテネータの量子化評価 | [仕様書5.8節](docs/SPEC.md) |
| `tools/eval_stereo_attn.py` | M/S 区間アッテネータの音質・保護部・占有帯域の比較 | [仕様書5.8節](docs/SPEC.md) |
| `tools/eval_hybrid.py` | 実験用高域位相・振幅主系のフレーム予算、帯域、音質、ViSQOL | [Y系の設計・評価報告](docs/HYBRID_Y_PAPER.md) |
| `tools/eval_distortion.py` | 歪み率（THD・THD+N、FM のゴースト） | 5.3 |
| `tools/eval_asym.py` | 主系と副系のビットレート差 | 5.4 |
| `tools/eval_softdec.py` | 軟判定の復号 | 5.5 |
| `tools/eval_m700.py` | モニターの主系の変調 | 5.6 |
| `tools/spectrum.py` | 送信スペクトル・音声のスペクトル | 5.7 |
| `tools/fig_postfilter.py`、`tools/eval_pf_link.py` | ポストフィルタ（量子化雑音の除去）の図と効果 | 3.6.3・5.8 |
| `tools/eval_postfilter.py`、`tools/eval_expbits.py` | ポストフィルタの回数、指数のビット数 | 5.8 |
| `tools/eval_kalman.py` | 帯域カルマン（時間方向の予測） | 5.8 |
| `tools/eval_loss.py` | フレーム欠落（ランダム・遮断） | 5.9 |
| `tools/alloc_search.py` | ビット割り当ての探索 | 付録B |

## 構成

```
docs/SPEC.md             方式の説明（論文形式：概要・方式・評価・付録に仕様）
docs/figures/            スペクトルの図
docs/results/            評価結果（JSON）
gracefm/                 リファレンス実装（対応は SPEC 付録E）
tools/                   変換・評価ツール
samples/                 サンプル音声（出力は24bit FLAC。放送用32kHz、monitor/ にモニター用48kHz）
tests/                  方式と静的マルチパス等化器のテスト
```

## サンプル音声

- 同じ受信電力の FM と並べた聴き比べ、条件と波形SNR は [samples/README.md](samples/README.md)
- 楽曲は [librosa/data](https://github.com/librosa/data) の CC BY 3.0 の2曲の10秒の抜粋（出典は samples/README.md）
- `demo_*` は全帯域の合成ステレオ信号、`samples/monitor/` は48kHzのモニター用サンプル。ベンチマーク用のロスレス原音は Git に含めない

## ライセンス

非商用は無料。商用利用は別途ライセンスが必要（著作権者に問い合わせ）。

| 対象 | ライセンス |
|---|---|
| ソースコード（`gracefm/`、`tools/`、`tests/`） | [PolyForm Noncommercial License 1.0.0](LICENSE)（特許の利用許諾を含む）。`NOTICE` の表示を残すこと |
| 文書・図・評価結果（`docs/`、README） | [CC BY-NC 4.0](https://creativecommons.org/licenses/by-nc/4.0/) |
| サンプル音声（`samples/`） | 加工したサンプルは [CC BY-NC 4.0](https://creativecommons.org/licenses/by-nc/4.0/)。元の楽曲は CC BY 3.0（出典は [samples/README.md](samples/README.md)） |
