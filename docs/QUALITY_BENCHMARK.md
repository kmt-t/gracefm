# GraceFM 音質ベンチマーク

## 評価条件

公開ライセンスのロスレス PCM WAV 3素材から各5秒を取り、モノラルに変換して32 kHzへ再標本化し、ピークを0.89にそろえた。主系 `B200MH-A4` と副系 `S50M` を電力50:50で送る。FMとGraceFMは同じ直接波 C/N0 を使う。波形SNRは原音との差、ViSQOL Audio MOS-LQOは48 kHzへ再標本化して測った予測指標であり、聴取試験の点数ではない。

音源のライセンス、出典、SHA-256、全条件の値は[AWGN・コーデック評価JSON](results/lossless_benchmark.json)に保存する。元のWAVはGit管理外で、この文書の数値は保存済みJSONから転記した。再測定には `python tools/fetch_lossless_benchmark_audio.py` と `python tools/eval_lossless_benchmark.py` を使用する。

## AWGN

各セルは **波形SNR [dB] / ViSQOL Audio MOS-LQO**。C/N0 は dB-Hz。

| 素材 | C/N0 | GraceFM | FM |
|---|---:|---:|---:|
| ピアノ | 54 | 12.84 / 2.262 | 7.25 / 1.665 |
| ピアノ | 60 | 26.76 / 2.178 | 27.78 / 2.499 |
| ピアノ | 66 | 41.10 / 3.163 | 42.70 / 2.948 |
| ピアノ | 80 | 70.76 / 4.728 | 54.03 / 4.138 |
| 打楽器 | 54 | 13.42 / 2.639 | 2.82 / 1.667 |
| 打楽器 | 60 | 27.46 / 3.673 | 22.77 / 2.255 |
| 打楽器 | 66 | 43.06 / 4.256 | 36.49 / 2.805 |
| 打楽器 | 80 | 70.20 / 4.731 | 48.89 / 3.829 |
| ギター | 54 | 13.55 / 2.707 | 6.21 / 1.855 |
| ギター | 60 | 30.19 / 2.831 | 26.62 / 2.686 |
| ギター | 66 | 44.05 / 3.989 | 39.82 / 3.319 |
| ギター | 80 | 72.45 / 4.731 | 45.14 / 4.310 |

コーデック単体の `B200MH-A4` と MP3 CBR 128/192/320 kbps の比較は同じ[評価JSON](results/lossless_benchmark.json)の `channel=codec` に収めた。レイリーフェージングと主系10 dB低下の条件は[通信路評価JSON](results/lossless_impairments.json)に収めた。

## 静的反射波

[反射波評価JSON](results/ghost_eval.json)は送受信 RRC、1本の静的反射波、11タップの線形等化器を使った結果を収める。同期と搬送波位相は既知とし、100フレームで伝搬路を較正する。直接波 C/N0 は66および80 dB-Hz。反射波なし、等化なし、等化あり、FMの各条件と、CRC失敗率・PLC使用率を素材別に保存した。`python tools/eval_ghost.py --seconds 5 --cn0 66,80 --workers 3 --json docs/results/ghost_eval.json` で再測定できる。

## aptX 比較

<a id="aptx-benchmark"></a>

[aptX比較JSON](results/aptx_benchmark.json)は、ステレオ `B200H-A4`、aptX、aptX HD の**コーデック単体**を同じ3素材で比較する。共通16 kHz帯域の入力と、元の48 kHz帯域を含む評価を分ける。aptXとaptX HDはBluetooth通信路を含まない。共通16 kHz帯域での ViSQOL 平均は、ピアノが GraceFM 4.346 / aptX 4.721 / aptX HD 4.732、打楽器が4.649 / 4.683 / 4.730、ギターが4.683 / 4.723 / 4.732だった。この条件ではViSQOLが示す aptX 系の優位を覆さない。`python tools/eval_aptx_benchmark.py` で再測定できる。
