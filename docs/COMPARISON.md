# GraceFM と FM・aptX・DAB+ の比較（現行設定）

比較の基準は GraceFM の現行設定。方式のアルゴリズム、フレーム予算、ビットレートと占有帯域は[技術論文](SPEC.md)にまとめた。32 kHz のB200MH/B200H/B200HYは99%占有帯域が約180 kHz、B200Y/B200MHYは約160 kHzである。以下の数値はシミュレーションとコーデック評価であり、実機・実電波の測定値ではない。

## アナログ FM：通信路を含む比較

同じ32 kHzモノラル原音を10秒ずつ使い、GraceFM `B200MH+SUB50M`（主系・副系の送信電力50:50）とアナログ FM を同じ直接波 C/N0 で評価した。同期既知のシミュレーションで、各セルは原音に対する保存済みFLACの波形 SNR（dB）。[個々の音源と条件・ハッシュ](results/samples.json)を参照。

| 素材 | C/N0 dB-Hz | GraceFM | FM |
|---|---:|---:|---:|
| fishin | 54 | 10.73 | 4.02 |
| fishin | 60 | 22.39 | 24.07 |
| fishin | 66 | 32.63 | 38.16 |
| fishin | 80 | 55.33 | 51.16 |
| vibeace | 54 | 13.73 | 2.81 |
| vibeace | 60 | 29.53 | 22.85 |
| vibeace | 66 | 44.39 | 36.62 |
| vibeace | 80 | 68.21 | 50.66 |

素材と受信条件によって優劣が変わる。波形 SNR だけで聴感上の優劣は決められない。FM は既存のアナログ受信機を使えるが、GraceFM のデータは専用復調器が必要。

## aptX / aptX HD：コーデック単体の比較

3素材を各5秒、同じピーク値で評価した。GraceFM は現行 `B200H`、aptX と aptX HD は FFmpeg のコーデック往復。共通16 kHz帯域では全方式に同じ32 kHz化原音を与え、aptX側は48 kHzに再標本化した。ViSQOL MOS-LQO と波形 SNR は各素材・左右チャンネルの平均。通信路、Bluetooth のペアリング・再送・バッファ遅延、GraceFM のRF通信路は含まない。[素材別の全測定値](results/aptx_benchmark.json)を参照。

| 評価帯域 | 方式 | 音声ビットレート kb/s | ViSQOL 平均 | 波形 SNR 平均 dB |
|---|---|---:|---:|---:|
| 共通16 kHz | B200H | 512 | 4.411 | 55.50 |
| 共通16 kHz | aptX | 384 | 4.709 | 51.45 |
| 共通16 kHz | aptX HD | 576 | 4.731 | 60.51 |
| 元の48 kHz | B200H | 512 | 3.925 | 52.07 |
| 元の48 kHz | aptX | 384 | 4.703 | 50.29 |
| 元の48 kHz | aptX HD | 576 | 4.731 | 58.95 |

この条件の ViSQOL では aptX 系が上回る。元の48 kHz帯域の比較には、GraceFM B200H の音声帯域上限16 kHzも含まれる。ビットレートは音声データであり、無線フレーム全体の速度ではない。

## MPEG HE-AAC v2：DAB+の音声コーデックとの比較

[ETSI TS 102 563](https://www.etsi.org/deliver/etsi_ts/102500_102599/102563/02.01.01_60/ts_102563v020101p.pdf) は、DAB+の音声にMPEG-4 HE-AAC v2のサブセットを規定する。このプロファイルにはAAC-LC、SBR、高効率ステレオ用のPSが含まれる。ここでは**HE-AAC v2（SBR+PSを有効化）**をGraceFM `B200H`と比べる。DAB+ではAAC変換長を960サンプルに限定するが、今回使用した通常のFDK AACエンコーダはそのDAB+専用設定を使っていない。したがって下表は**MPEG HE-AAC v2のコーデック実装との比較**であり、DAB+準拠ストリームの実測値ではない。

aptX比較と同じ3素材の同じ5秒区間を使い、ピークを0.89に合わせた。GraceFMは32 kHz、HE-AAC v2は48 kHzのステレオ入力で符号化・復号した。共通16 kHz帯域の評価では両者に同じ32 kHz化原音を与え、HE-AAC v2の入力だけ48 kHzへ再標本化する。「元の48 kHz」は原音を基準とし、GraceFMの16 kHz音声帯域上限も結果に含める。[DAB+向けODR-AudioEnc](https://github.com/Opendigitalradio/ODR-AudioEnc/blob/master/README.md#dab-aac-encoder-configuration)の既定設定ではステレオ48 kb/s以下でPSを使うため、32/48 kb/sを選んだ。HE-AAC v2は[FDK AAC](https://github.com/mstorsjo/fdk-aac)のAOT 29を`fdkaac`でCBRに設定し、FFmpegで復号した。復号出力の一定遅延を相互相関で測って除去した。ViSQOL Audio MOS-LQOは素材・左右チャンネルの平均、波形SNRは素材ごとにステレオ全体で計算して平均した。通信路、FEC、DAB+スーパーフレーム、受信バッファは含まない。[素材別測定値・ビルド情報](results/heaacv2_benchmark.json)と[再現用スクリプト](../tools/eval_heaacv2_benchmark.py)を参照。

| 評価帯域 | 方式 | 音声ビットレート kb/s | ViSQOL 平均 | 波形 SNR 平均 dB |
|---|---|---:|---:|---:|
| 共通16 kHz | B200H | 512 | 4.411 | 55.50 |
| 共通16 kHz | HE-AAC v2 | 32 | 3.816 | 17.78 |
| 共通16 kHz | HE-AAC v2 | 48 | 3.776 | 18.23 |
| 元の48 kHz | B200H | 512 | 3.925 | 52.07 |
| 元の48 kHz | HE-AAC v2 | 32 | 4.146 | 17.77 |
| 元の48 kHz | HE-AAC v2 | 48 | 4.182 | 18.22 |

共通帯域ではB200HのViSQOLが高く、元の48 kHzを基準にするとHE-AAC v2のViSQOLが高い。ただしB200Hの音声ペイロードは512 kb/sで、HE-AAC v2の目標32/48 kb/sと大きく異なるため、同一ビットレートでの符号化効率を示す比較ではない。HE-AAC v2のPSはステレオをパラメータから再構成するので、波形SNRの差をそのまま聴感差と読めない。3素材・5秒の小規模測定であり、32 kb/sと48 kb/sのViSQOL順位もこの条件の結果に限る。DAB+固有の960サンプル変換、120 msスーパーフレーム、Reed–Solomon符号と仮想インターリーブを含む品質・遅延は未測定である。
