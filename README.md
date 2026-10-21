# GraceFM

FM帯で、遅延4ms以下・電波が弱くなっても途切れずになだらかに劣化する（graceful degradation）デジタル音声伝送方式。仕様書とリファレンス実装（Python パッケージ `gracefm`）。

## 仕様

| 項目 | 放送（FM放送の代替・災害時） | モニター（据え置き機・近距離） |
|---|---|---|
| 構成 | 主系 B200H / B200MH ＋ 副系 S100 / S50M | M700H |
| 伝送込みの遅延（処理時間0） | 4.00ms | 2.67ms |
| サンプリング / 音声帯域 | 32kHz / 16kHz | 48kHz / 24kHz |
| 音声ビットレート | 主系 530 / 470kbps（基本層 200 / 194）＋ 副系 95 / 46kbps | 854kbps（基本層329） |
| 変調 | 主系 階層16QAM、副系 QPSK | 階層16QAM |
| 符号化 | Haar 6段、帯域ごとのブロック浮動小数点（指数4bit） | 同左 |
| 誤り訂正 | 指数・仮数の上位1bit のみ（畳み込み符号 K=7 r=1/2 ＋ CRC-16） | 同左 |
| 占有帯域（99%） | 主系 191 / 162kHz ＋ 副系 104 / 65kHz | 302kHz |
| 冗長性 | 2周波数・半ブロックずらし・帯域ごとに逆分散重みで融合 | なし |
| 欠落時 | 片方の欠落は他方で補う。両方欠けたら LPC で外挿（30ms まで） | LPC で外挿（30ms まで） |
| 受信処理 | 軟判定の復号、量子化区間への射影による量子化雑音の除去、融合、欠落の外挿（広義のカルマンフィルタとして構成） | 同左（融合なし） |
| 暗号化 | なし | AES-128-CTR（任意） |

## 性能（同じ受信電力、歌入りの楽曲、波形SNR）

| 条件 | C/N0（C/N） | GraceFM（B200MH＋S50M） | アナログFM | アナログAM |
|---|---|---|---|---|
| 白色雑音 | 54dB-Hz（1.4dB） | **11.8dB** | 4.3dB | -0.1dB |
| 白色雑音 | 57dB-Hz（4.4dB） | **17.9dB** | 11.7dB | 2.8dB |
| 白色雑音 | 60dB-Hz（7.4dB） | 23.6dB | **24.6dB** | 5.8dB |
| 白色雑音（5m の見積もり） | 66dB-Hz（13.4dB） | 33.9dB | **38.4dB** | 11.5dB |
| 白色雑音 | 80dB-Hz（27.4dB） | **56.8dB** | 50.4dB | 20.8dB |
| フェージング | 60dB-Hz（7.4dB） | **13.3dB** | 5.2dB | — |
| 片方の周波数が −10dB | 60dB-Hz（7.4dB） | **16.4dB** | -0.8dB | — |
| 歪み率 THD（1kHz） | 80dB-Hz | 0.0027% | 0.0035%（ゴースト 10µs・−6dB で 1.55%） | — |
| 伝送遅延 | — | 4.0ms | — | — |

- 弱い電波・フェージング・片方の周波数の落ち込みで FM・AM を大きく上回る
- 強い電波では拡張層が届き、FM を上回る
- 中間の受信電力（C/N 7〜22dB）・白色雑音のみでは、歌入りの素材の波形SNR で FM が上
- 片方の周波数が毎秒200ms 遮断されても無音0%（1系統では16.7%）。両系統が同時に30ms 以上欠けたときだけ無音
- 遅延は BT（A2DP）の100〜200ms に対し 4ms
- 詳細・条件：[docs/SPEC.md](docs/SPEC.md)（概要・5節）

## 制約

- 同期・等化・パルス成形・実RF は未実装（同期済みのシンボル列に雑音を加えるモデル）
- 未評価：FMステレオとの比較、ゴーストのある通信路、実RF
- 処理はオフラインの配列処理（実時間ではない）。遅延は時刻モデルの計算値

## 使い方

```sh
pip install -r requirements.txt

python tools/codec_wav.py 入力.wav 出力.wav --profile B200H         # コーデックだけ
python tools/sim_link.py 入力.wav 出力.wav --profile B200M --snr 8  # 送信 → 通信路 → 受信
python tools/make_samples.py                                        # samples/ を作り直す
python tests/test_gracefm.py                                        # テスト（または python -m pytest tests/）
```

評価ツール：

| ツール | 内容 | SPEC の節 |
|---|---|---|
| `tools/eval_final.py` | 最終構成とアナログFMの比較 | 5.2 |
| `tools/eval_am.py` | アナログAM との比較 | 5.2 |
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
samples/                 サンプル音声（16bit FLAC。放送用32kHz、monitor/ にモニター用48kHz）
tests/test_gracefm.py    テスト
```

## サンプル音声

- 同じ受信電力の FM と並べた聴き比べ、条件と波形SNR は [samples/README.md](samples/README.md)
- 楽曲は [librosa/data](https://github.com/librosa/data) の CC BY 3.0 の2曲の10秒の抜粋（出典は samples/README.md）

## ライセンス

非商用は無料。商用利用は別途ライセンスが必要（著作権者に問い合わせ）。

| 対象 | ライセンス |
|---|---|
| ソースコード（`gracefm/`、`tools/`、`tests/`） | [PolyForm Noncommercial License 1.0.0](LICENSE)（特許の利用許諾を含む）。`NOTICE` の表示を残すこと |
| 文書・図・評価結果（`docs/`、README） | [CC BY-NC 4.0](https://creativecommons.org/licenses/by-nc/4.0/) |
| サンプル音声（`samples/`） | 加工したサンプルは [CC BY-NC 4.0](https://creativecommons.org/licenses/by-nc/4.0/)。元の楽曲は CC BY 3.0（出典は [samples/README.md](samples/README.md)） |
