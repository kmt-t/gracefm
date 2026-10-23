# 48 kHz Y系の試聴音源

`M700Y` はQPSK、`M700HY` は階層16QAMを使う実験用主系です。高域Mの標準仮数は8 bitで、上位2 bitを位相、下位6 bitを連続半径へ送り、6〜24 kHzの各係数を1複素シンボルに載せます。指数と仮数上位bitはFECで保護します。`M700HY` は高域Sの次位bitを強い位置、低域Mの一部の下位bitを弱い位置へ配置します。

各音源は48 kHz・10秒です。従来版と同じ入力区間、単一主系、C/N0、乱数種1を使います。`demo` は合成ステレオ、`fishin` と `vibeace` は32 kHz原音を48 kHzへ再標本化したモノラルです。復号時はSにポストフィルタを適用せず、Mのポストフィルタだけをソフトウェアで有効にしています。

| 素材 | 原音 | `M700Y` コーデック | `M700Y` AWGN 70 / 65 | `M700HY` コーデック | `M700HY` AWGN 80 / 75 / 70 / 65 |
|---|---|---|---|---|---|
| demo | [原音](demo_orig48.flac) | [コーデック](demo_M700Y.flac) | [70](demo_M700Y_cn0-70.flac) / [65](demo_M700Y_cn0-65.flac) | [コーデック](demo_M700HY.flac) | [80](demo_M700HY_cn0-80.flac) / [75](demo_M700HY_cn0-75.flac) / [70](demo_M700HY_cn0-70.flac) / [65](demo_M700HY_cn0-65.flac) |
| Fishin | [原音](fishin_orig48.flac) | [コーデック](fishin_M700Y.flac) | [70](fishin_M700Y_cn0-70.flac) / [65](fishin_M700Y_cn0-65.flac) | [コーデック](fishin_M700HY.flac) | [80](fishin_M700HY_cn0-80.flac) / [75](fishin_M700HY_cn0-75.flac) / [70](fishin_M700HY_cn0-70.flac) / [65](fishin_M700HY_cn0-65.flac) |
| Vibe Ace | [原音](vibeace_orig48.flac) | [コーデック](vibeace_M700Y.flac) | [70](vibeace_M700Y_cn0-70.flac) / [65](vibeace_M700Y_cn0-65.flac) | [コーデック](vibeace_M700HY.flac) | [80](vibeace_M700HY_cn0-80.flac) / [75](vibeace_M700HY_cn0-75.flac) / [70](vibeace_M700HY_cn0-70.flac) / [65](vibeace_M700HY_cn0-65.flac) |

雑音なしの実シンボル往復は、各素材の `*_M700Y_ideal.flac` と `*_M700HY_ideal.flac` です。測定値、FEC・CRC・PLC、ファイルハッシュは[結果JSON](../../docs/results/monitor_y_samples.json)、従来方式と対になる評価は[比較JSON](../../docs/results/monitor_y_vs_legacy.json)に保存します。

## 12〜24 kHzを含む試験音源

[hires_probe原音](hires_probe_orig48.flac)は合成ステレオに12〜24 kHzのM成分を加えた48 kHz・24 bitの試験音源です。自然音源のハイレゾ録音ではありません。

| プロファイル | コーデック | AWGN 80 / 75 / 70 / 65 |
|---|---|---|
| `M700` | [音声](hires_probe_M700.flac) | [70](hires_probe_M700_cn0-70.flac) / [65](hires_probe_M700_cn0-65.flac) |
| `M700Y` | [音声](hires_probe_M700Y.flac) | [70](hires_probe_M700Y_cn0-70.flac) / [65](hires_probe_M700Y_cn0-65.flac) |
| `M700H` | [音声](hires_probe_M700H.flac) | [80](hires_probe_M700H_cn0-80.flac) / [75](hires_probe_M700H_cn0-75.flac) / [70](hires_probe_M700H_cn0-70.flac) / [65](hires_probe_M700H_cn0-65.flac) |
| `M700HY` | [音声](hires_probe_M700HY.flac) | [80](hires_probe_M700HY_cn0-80.flac) / [75](hires_probe_M700HY_cn0-75.flac) / [70](hires_probe_M700HY_cn0-70.flac) / [65](hires_probe_M700HY_cn0-65.flac) |

12〜24 kHzのSNRを含む結果は[高域試験JSON](../../docs/results/monitor_y_hires_probe.json)に保存します。

## 高域Mの半径分解能

標準の8 bitに加え、10 bitと12 bitを同じ1係数/1シンボルで比較します。FEC保護量とフレーム長は各幅で同じです。

| 素材 | 8 bit標準 | 10 bit | 12 bit |
|---|---|---|---|
| demo・コーデック | [音声](demo_M700HY.flac) | [音声](demo_M700HY-R10.flac) | [音声](demo_M700HY-R12.flac) |
| demo・AWGN 70 | [音声](demo_M700HY_cn0-70.flac) | [音声](demo_M700HY-R10_cn0-70.flac) | [音声](demo_M700HY-R12_cn0-70.flac) |
| hires_probe・コーデック | [音声](hires_probe_M700HY.flac) | [音声](hires_probe_M700HY-R10.flac) | [音声](hires_probe_M700HY-R12.flac) |
| hires_probe・AWGN 70 | [音声](hires_probe_M700HY_cn0-70.flac) | [音声](hires_probe_M700HY-R10_cn0-70.flac) | [音声](hires_probe_M700HY-R12_cn0-70.flac) |

全条件の測定値とSHA-256は[分解能比較JSON](../../docs/results/monitor_y_radius_precision.json)に保存します。方式と測定結果は[設計・評価報告](../../docs/HYBRID_Y_PAPER.md)と[音質評価レポート](../../docs/HYBRID_Y_AUDIO_QUALITY.md)に記載します。
