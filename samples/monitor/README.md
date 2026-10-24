# 現行サンプル音声 — 48 kHz モニター

**全デジタル主系・副系に標準アッテネータを含む現行設定の音声です。** 各10秒。保存したFLACを読み戻して波形SNRを再測定しています。

[命名規則](../NAMING.md) · [設定表](../../docs/PROFILES.md) · [全音源の設定・測定値・SHA-256](../../docs/results/samples.json)

32 kHzの2系統は電力50:50。48 kHzの `M700H+SUB100-48K` は75:25。それ以外の48 kHz音声は主系1系統です。`codec` は通信路なし、`ideal` は雑音なしのシンボル送受信。AWGN等は同期既知のシミュレーションです。

`M700H-base` は実際の基本層を保持し、拡張層の事後確率だけを0.5にした比較音源です。係数別昇格1bitと標準アッテネータを含みます。`R10` / `R12` はY仮数幅の比較条件です。

波形SNRは原音との差であり、聴感の点数ではありません。

| 音源 | 構成 | 条件 | 試聴 | 波形SNR dB |
|---|---|---|---|---:|
| demo | M700H+SUB100-48K | awgn-cn0-65dBHz | [再生](demo__48k__M700H+SUB100-48K__awgn-cn0-65dBHz.flac) | 27.50 |
| demo | M700H+SUB100-48K | awgn-cn0-70dBHz | [再生](demo__48k__M700H+SUB100-48K__awgn-cn0-70dBHz.flac) | 30.11 |
| demo | M700H+SUB100-48K | awgn-cn0-75dBHz | [再生](demo__48k__M700H+SUB100-48K__awgn-cn0-75dBHz.flac) | 34.06 |
| demo | M700H+SUB100-48K | awgn-cn0-80dBHz | [再生](demo__48k__M700H+SUB100-48K__awgn-cn0-80dBHz.flac) | 45.60 |
| demo | M700H-base | codec | [再生](demo__48k__M700H-base__codec.flac) | 28.22 |
| demo | M700H | awgn-cn0-65dBHz | [再生](demo__48k__M700H__awgn-cn0-65dBHz.flac) | 26.35 |
| demo | M700H | awgn-cn0-70dBHz | [再生](demo__48k__M700H__awgn-cn0-70dBHz.flac) | 30.79 |
| demo | M700H | awgn-cn0-75dBHz | [再生](demo__48k__M700H__awgn-cn0-75dBHz.flac) | 35.89 |
| demo | M700H | awgn-cn0-80dBHz | [再生](demo__48k__M700H__awgn-cn0-80dBHz.flac) | 49.92 |
| demo | M700H | codec | [再生](demo__48k__M700H__codec.flac) | 57.42 |
| demo | M700 | awgn-cn0-65dBHz | [再生](demo__48k__M700__awgn-cn0-65dBHz.flac) | 30.52 |
| demo | M700 | awgn-cn0-70dBHz | [再生](demo__48k__M700__awgn-cn0-70dBHz.flac) | 40.28 |
| demo | M700 | codec | [再生](demo__48k__M700__codec.flac) | 40.28 |
| fishin | M700H-base | codec | [再生](fishin__48k__M700H-base__codec.flac) | 29.71 |
| fishin | M700H | awgn-cn0-65dBHz | [再生](fishin__48k__M700H__awgn-cn0-65dBHz.flac) | 27.06 |
| fishin | M700H | awgn-cn0-70dBHz | [再生](fishin__48k__M700H__awgn-cn0-70dBHz.flac) | 32.10 |
| fishin | M700H | awgn-cn0-75dBHz | [再生](fishin__48k__M700H__awgn-cn0-75dBHz.flac) | 36.86 |
| fishin | M700H | awgn-cn0-80dBHz | [再生](fishin__48k__M700H__awgn-cn0-80dBHz.flac) | 49.61 |
| fishin | M700H | codec | [再生](fishin__48k__M700H__codec.flac) | 54.24 |
| fishin | M700 | awgn-cn0-65dBHz | [再生](fishin__48k__M700__awgn-cn0-65dBHz.flac) | 28.71 |
| fishin | M700 | awgn-cn0-70dBHz | [再生](fishin__48k__M700__awgn-cn0-70dBHz.flac) | 50.23 |
| fishin | M700 | codec | [再生](fishin__48k__M700__codec.flac) | 54.13 |
| vibeace | M700H-base | codec | [再生](vibeace__48k__M700H-base__codec.flac) | 43.16 |
| vibeace | M700H | awgn-cn0-65dBHz | [再生](vibeace__48k__M700H__awgn-cn0-65dBHz.flac) | 32.88 |
| vibeace | M700H | awgn-cn0-70dBHz | [再生](vibeace__48k__M700H__awgn-cn0-70dBHz.flac) | 45.63 |
| vibeace | M700H | awgn-cn0-75dBHz | [再生](vibeace__48k__M700H__awgn-cn0-75dBHz.flac) | 50.52 |
| vibeace | M700H | awgn-cn0-80dBHz | [再生](vibeace__48k__M700H__awgn-cn0-80dBHz.flac) | 62.61 |
| vibeace | M700H | codec | [再生](vibeace__48k__M700H__codec.flac) | 67.46 |
| vibeace | M700 | awgn-cn0-65dBHz | [再生](vibeace__48k__M700__awgn-cn0-65dBHz.flac) | 28.93 |
| vibeace | M700 | awgn-cn0-70dBHz | [再生](vibeace__48k__M700__awgn-cn0-70dBHz.flac) | 63.54 |
| vibeace | M700 | codec | [再生](vibeace__48k__M700__codec.flac) | 67.24 |

## 原音

- [demo](demo__48k__reference.flac)
- [fishin](fishin__48k__reference.flac)
- [vibeace](vibeace__48k__reference.flac)
