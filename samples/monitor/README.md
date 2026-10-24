# 現行サンプル音声 — 48 kHz モニター

**全デジタル主系・副系に標準アッテネータを含む現行設定の音声です。** 各10秒。保存したFLACを読み戻して波形SNRを再測定しています。

[命名規則](../NAMING.md) · [設定表](../../docs/PROFILES.md) · [全音源の設定・測定値・SHA-256](../../docs/results/samples.json)

32 kHzの2系統は電力50:50。48 kHzの `M700+SUB100-48K` は75:25。それ以外の48 kHz音声は主系1系統です。`codec` は通信路なし、`ideal` は雑音なしのシンボル送受信。AWGN等は同期既知のシミュレーションです。

`M700-base` は実際の基本層を保持し、拡張層の事後確率だけを0.5にした比較音源です。標準アッテネータを含みます。`R10` / `R12` はY仮数幅の比較条件です。

波形SNRは原音との差であり、聴感の点数ではありません。

| 音源 | 構成 | 条件 | 試聴 | 波形SNR dB |
|---|---|---|---|---:|
| demo | M700+SUB100-48K | awgn-cn0-65dBHz | [再生](demo__48k__M700+SUB100-48K__awgn-cn0-65dBHz.flac) | 25.80 |
| demo | M700+SUB100-48K | awgn-cn0-70dBHz | [再生](demo__48k__M700+SUB100-48K__awgn-cn0-70dBHz.flac) | 29.54 |
| demo | M700+SUB100-48K | awgn-cn0-75dBHz | [再生](demo__48k__M700+SUB100-48K__awgn-cn0-75dBHz.flac) | 32.90 |
| demo | M700+SUB100-48K | awgn-cn0-80dBHz | [再生](demo__48k__M700+SUB100-48K__awgn-cn0-80dBHz.flac) | 38.81 |
| demo | M700-base | codec | [再生](demo__48k__M700-base__codec.flac) | 13.18 |
| demo | M700M | awgn-cn0-65dBHz | [再生](demo__48k__M700M__awgn-cn0-65dBHz.flac) | 14.50 |
| demo | M700M | awgn-cn0-70dBHz | [再生](demo__48k__M700M__awgn-cn0-70dBHz.flac) | 17.38 |
| demo | M700M | codec | [再生](demo__48k__M700M__codec.flac) | 24.27 |
| demo | M700 | awgn-cn0-65dBHz | [再生](demo__48k__M700__awgn-cn0-65dBHz.flac) | 14.18 |
| demo | M700 | awgn-cn0-70dBHz | [再生](demo__48k__M700__awgn-cn0-70dBHz.flac) | 16.27 |
| demo | M700 | awgn-cn0-75dBHz | [再生](demo__48k__M700__awgn-cn0-75dBHz.flac) | 21.77 |
| demo | M700 | awgn-cn0-80dBHz | [再生](demo__48k__M700__awgn-cn0-80dBHz.flac) | 35.55 |
| demo | M700 | codec | [再生](demo__48k__M700__codec.flac) | 40.28 |
| fishin | M700-base | codec | [再生](fishin__48k__M700-base__codec.flac) | 11.84 |
| fishin | M700M | awgn-cn0-65dBHz | [再生](fishin__48k__M700M__awgn-cn0-65dBHz.flac) | 13.87 |
| fishin | M700M | awgn-cn0-70dBHz | [再生](fishin__48k__M700M__awgn-cn0-70dBHz.flac) | 17.34 |
| fishin | M700M | codec | [再生](fishin__48k__M700M__codec.flac) | 54.13 |
| fishin | M700 | awgn-cn0-65dBHz | [再生](fishin__48k__M700__awgn-cn0-65dBHz.flac) | 13.21 |
| fishin | M700 | awgn-cn0-70dBHz | [再生](fishin__48k__M700__awgn-cn0-70dBHz.flac) | 15.56 |
| fishin | M700 | awgn-cn0-75dBHz | [再生](fishin__48k__M700__awgn-cn0-75dBHz.flac) | 21.41 |
| fishin | M700 | awgn-cn0-80dBHz | [再生](fishin__48k__M700__awgn-cn0-80dBHz.flac) | 36.64 |
| fishin | M700 | codec | [再生](fishin__48k__M700__codec.flac) | 54.13 |
| vibeace | M700-base | codec | [再生](vibeace__48k__M700-base__codec.flac) | 12.85 |
| vibeace | M700M | awgn-cn0-65dBHz | [再生](vibeace__48k__M700M__awgn-cn0-65dBHz.flac) | 14.60 |
| vibeace | M700M | awgn-cn0-70dBHz | [再生](vibeace__48k__M700M__awgn-cn0-70dBHz.flac) | 18.01 |
| vibeace | M700M | codec | [再生](vibeace__48k__M700M__codec.flac) | 67.24 |
| vibeace | M700 | awgn-cn0-65dBHz | [再生](vibeace__48k__M700__awgn-cn0-65dBHz.flac) | 14.04 |
| vibeace | M700 | awgn-cn0-70dBHz | [再生](vibeace__48k__M700__awgn-cn0-70dBHz.flac) | 16.37 |
| vibeace | M700 | awgn-cn0-75dBHz | [再生](vibeace__48k__M700__awgn-cn0-75dBHz.flac) | 22.11 |
| vibeace | M700 | awgn-cn0-80dBHz | [再生](vibeace__48k__M700__awgn-cn0-80dBHz.flac) | 34.51 |
| vibeace | M700 | codec | [再生](vibeace__48k__M700__codec.flac) | 67.24 |

## 原音

- [demo](demo__48k__reference.flac)
- [fishin](fishin__48k__reference.flac)
- [vibeace](vibeace__48k__reference.flac)
