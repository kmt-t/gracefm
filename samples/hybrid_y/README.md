# Y系・位相＋振幅ハイブリッド方式の試聴音源

高域Mの標準仮数幅は8 bitで、上位2 bitを位相、下位6 bitを連続半径に割り当てます。

`fishin` と `vibeace` はモノラル `B200MHY-A4`＋副系 `S50M`、`demo` はステレオ `B200HY-A4`＋副系 `S100`。高域Mの各係数を4位相＋連続半径の1複素シンボルで送り、上位1bitをFECで保護します。32 kHz Y主系のMには4〜8 kHz（16係数を2係数ずつ）と8〜16 kHz（32係数を4係数ずつ）に各8 bitの区間アッテネータを置き、FECで保護します。`demo` のS成分は高域を含めて送ります。復号時はSを逆Haar変換だけで復元し、Mのポストフィルタだけをソフトウェアで有効にしています。

| 素材 | 原音 | Y系コーデック単体 | Y系・理想シンボル | Y系・AWGN 66dB-Hz | 半径を使わない対照・66dB-Hz |
|---|---|---|---|---|---|
| Fishin | [原音](fishin_orig.flac) | [コーデック](fishin_B200MHY-A4.flac) | [理想送受信](fishin_Y_ideal_symbols.flac) | [AWGN66](fishin_final_cn0-66.flac) | [位相のみ](fishin_Y_phaseonly_cn0-66.flac) |
| Vibe Ace | [原音](vibeace_orig.flac) | [コーデック](vibeace_B200MHY-A4.flac) | [理想送受信](vibeace_Y_ideal_symbols.flac) | [AWGN66](vibeace_final_cn0-66.flac) | [位相のみ](vibeace_Y_phaseonly_cn0-66.flac) |
| 合成ステレオ | [原音](demo_orig.flac) | [コーデック](demo_B200HY-A4.flac) | [理想送受信](demo_Y_ideal_symbols.flac) | [AWGN66](demo_final_cn0-66.flac) | [位相のみ](demo_Y_phaseonly_cn0-66.flac) |

原音は従来の16bit FLACをそのまま複製し、復号音は32kHz・各10秒・24bit FLACです。入力区間と0.89のピーク正規化は従来の `tools/make_samples.py` と同じです。`*_B200*Y-A4.flac` は従来のプロファイル名付きファイルと同じコーデック単体の条件。`*_Y_ideal_symbols.flac` は実際のY系変調器・FEC・復調器を通した雑音なしの送受信です。雑音ありの条件は、従来の `*_final_*` と同じ主系＋副系、電力50:50、seed=1、半ブロックずらしと帯域別融合を使います。

追加の条件：

| 素材 | AWGN 80 | AWGN 60 | AWGN 57 | AWGN 54 | レイリー 60 | 主系−10dB・66 |
|---|---|---|---|---|---|---|
| Fishin | [80](fishin_final_cn0-80.flac) | [60](fishin_final_cn0-60.flac) | [57](fishin_final_cn0-57.flac) | [54](fishin_final_cn0-54.flac) | [レイリー](fishin_final_rayleigh_cn0-60.flac) | [主系低下](fishin_final_fade10_cn0-66.flac) |
| Vibe Ace | [80](vibeace_final_cn0-80.flac) | [60](vibeace_final_cn0-60.flac) | [57](vibeace_final_cn0-57.flac) | [54](vibeace_final_cn0-54.flac) | [レイリー](vibeace_final_rayleigh_cn0-60.flac) | [主系低下](vibeace_final_fade10_cn0-66.flac) |
| 合成ステレオ | [80](demo_final_cn0-80.flac) | [60](demo_final_cn0-60.flac) | [57](demo_final_cn0-57.flac) | [54](demo_final_cn0-54.flac) | [レイリー](demo_final_rayleigh_cn0-60.flac) | [主系低下](demo_final_fade10_cn0-66.flac) |

測定値、CRC失敗率、PLC使用率、送信レート、占有帯域、ファイルのSHA-256は[結果JSON](../../docs/results/hybrid_y_samples.json)に保存します。方式は[Y系の設計・評価報告](../../docs/HYBRID_Y_PAPER.md)、従来方式との音質比較は[音質評価レポート](../../docs/HYBRID_Y_AUDIO_QUALITY.md)を参照してください。
