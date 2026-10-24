# 現行サンプル音声 — 48 kHz Y系・高域試験

**全デジタル主系・副系に標準アッテネータを含む現行設定の音声です。** 各10秒。保存したFLACを読み戻して波形SNRを再測定しています。

[命名規則](../NAMING.md) · [設定表](../../docs/PROFILES.md) · [全音源の設定・測定値・SHA-256](../../docs/results/samples.json)

32 kHzの2系統は電力50:50。48 kHzの `M700H+SUB100-48K` は75:25。それ以外の48 kHz音声は主系1系統です。`codec` は通信路なし、`ideal` は雑音なしのシンボル送受信。AWGN等は同期既知のシミュレーションです。

`M700H-base` は実際の基本層を保持し、拡張層の事後確率だけを0.5にした比較音源です。係数別昇格1bitと標準アッテネータを含みます。`R10` / `R12` はY仮数幅の比較条件です。

波形SNRは原音との差であり、聴感の点数ではありません。

| 音源 | 構成 | 条件 | 試聴 | 波形SNR dB |
|---|---|---|---|---:|
| demo | M700HY-R10 | awgn-cn0-65dBHz | [再生](demo__48k__M700HY-R10__awgn-cn0-65dBHz.flac) | 27.73 |
| demo | M700HY-R10 | awgn-cn0-70dBHz | [再生](demo__48k__M700HY-R10__awgn-cn0-70dBHz.flac) | 32.41 |
| demo | M700HY-R10 | awgn-cn0-75dBHz | [再生](demo__48k__M700HY-R10__awgn-cn0-75dBHz.flac) | 37.66 |
| demo | M700HY-R10 | awgn-cn0-80dBHz | [再生](demo__48k__M700HY-R10__awgn-cn0-80dBHz.flac) | 45.01 |
| demo | M700HY-R10 | codec | [再生](demo__48k__M700HY-R10__codec.flac) | 63.06 |
| demo | M700HY-R12 | awgn-cn0-65dBHz | [再生](demo__48k__M700HY-R12__awgn-cn0-65dBHz.flac) | 27.76 |
| demo | M700HY-R12 | awgn-cn0-70dBHz | [再生](demo__48k__M700HY-R12__awgn-cn0-70dBHz.flac) | 32.44 |
| demo | M700HY-R12 | awgn-cn0-75dBHz | [再生](demo__48k__M700HY-R12__awgn-cn0-75dBHz.flac) | 37.71 |
| demo | M700HY-R12 | awgn-cn0-80dBHz | [再生](demo__48k__M700HY-R12__awgn-cn0-80dBHz.flac) | 45.17 |
| demo | M700HY-R12 | codec | [再生](demo__48k__M700HY-R12__codec.flac) | 63.31 |
| demo | M700HY | awgn-cn0-65dBHz | [再生](demo__48k__M700HY__awgn-cn0-65dBHz.flac) | 27.68 |
| demo | M700HY | awgn-cn0-70dBHz | [再生](demo__48k__M700HY__awgn-cn0-70dBHz.flac) | 32.34 |
| demo | M700HY | awgn-cn0-75dBHz | [再生](demo__48k__M700HY__awgn-cn0-75dBHz.flac) | 37.53 |
| demo | M700HY | awgn-cn0-80dBHz | [再生](demo__48k__M700HY__awgn-cn0-80dBHz.flac) | 44.52 |
| demo | M700HY | codec | [再生](demo__48k__M700HY__codec.flac) | 60.52 |
| demo | M700HY | ideal | [再生](demo__48k__M700HY__ideal.flac) | 60.52 |
| demo | M700Y | awgn-cn0-65dBHz | [再生](demo__48k__M700Y__awgn-cn0-65dBHz.flac) | 14.30 |
| demo | M700Y | awgn-cn0-70dBHz | [再生](demo__48k__M700Y__awgn-cn0-70dBHz.flac) | 16.22 |
| demo | M700Y | codec | [再生](demo__48k__M700Y__codec.flac) | 40.32 |
| demo | M700Y | ideal | [再生](demo__48k__M700Y__ideal.flac) | 40.32 |
| fishin | M700HY | awgn-cn0-65dBHz | [再生](fishin__48k__M700HY__awgn-cn0-65dBHz.flac) | 25.43 |
| fishin | M700HY | awgn-cn0-70dBHz | [再生](fishin__48k__M700HY__awgn-cn0-70dBHz.flac) | 28.90 |
| fishin | M700HY | awgn-cn0-75dBHz | [再生](fishin__48k__M700HY__awgn-cn0-75dBHz.flac) | 33.22 |
| fishin | M700HY | awgn-cn0-80dBHz | [再生](fishin__48k__M700HY__awgn-cn0-80dBHz.flac) | 38.58 |
| fishin | M700HY | codec | [再生](fishin__48k__M700HY__codec.flac) | 55.61 |
| fishin | M700HY | ideal | [再生](fishin__48k__M700HY__ideal.flac) | 55.61 |
| fishin | M700Y | awgn-cn0-65dBHz | [再生](fishin__48k__M700Y__awgn-cn0-65dBHz.flac) | 13.05 |
| fishin | M700Y | awgn-cn0-70dBHz | [再生](fishin__48k__M700Y__awgn-cn0-70dBHz.flac) | 15.12 |
| fishin | M700Y | codec | [再生](fishin__48k__M700Y__codec.flac) | 55.46 |
| fishin | M700Y | ideal | [再生](fishin__48k__M700Y__ideal.flac) | 55.46 |
| hires_probe | M700HY-R10 | awgn-cn0-65dBHz | [再生](hires_probe__48k__M700HY-R10__awgn-cn0-65dBHz.flac) | 21.74 |
| hires_probe | M700HY-R10 | awgn-cn0-70dBHz | [再生](hires_probe__48k__M700HY-R10__awgn-cn0-70dBHz.flac) | 26.50 |
| hires_probe | M700HY-R10 | awgn-cn0-75dBHz | [再生](hires_probe__48k__M700HY-R10__awgn-cn0-75dBHz.flac) | 31.16 |
| hires_probe | M700HY-R10 | awgn-cn0-80dBHz | [再生](hires_probe__48k__M700HY-R10__awgn-cn0-80dBHz.flac) | 36.33 |
| hires_probe | M700HY-R10 | codec | [再生](hires_probe__48k__M700HY-R10__codec.flac) | 61.61 |
| hires_probe | M700HY-R12 | awgn-cn0-65dBHz | [再生](hires_probe__48k__M700HY-R12__awgn-cn0-65dBHz.flac) | 21.76 |
| hires_probe | M700HY-R12 | awgn-cn0-70dBHz | [再生](hires_probe__48k__M700HY-R12__awgn-cn0-70dBHz.flac) | 26.54 |
| hires_probe | M700HY-R12 | awgn-cn0-75dBHz | [再生](hires_probe__48k__M700HY-R12__awgn-cn0-75dBHz.flac) | 31.22 |
| hires_probe | M700HY-R12 | awgn-cn0-80dBHz | [再生](hires_probe__48k__M700HY-R12__awgn-cn0-80dBHz.flac) | 36.47 |
| hires_probe | M700HY-R12 | codec | [再生](hires_probe__48k__M700HY-R12__codec.flac) | 63.07 |
| hires_probe | M700HY | awgn-cn0-65dBHz | [再生](hires_probe__48k__M700HY__awgn-cn0-65dBHz.flac) | 21.70 |
| hires_probe | M700HY | awgn-cn0-70dBHz | [再生](hires_probe__48k__M700HY__awgn-cn0-70dBHz.flac) | 26.42 |
| hires_probe | M700HY | awgn-cn0-75dBHz | [再生](hires_probe__48k__M700HY__awgn-cn0-75dBHz.flac) | 30.97 |
| hires_probe | M700HY | awgn-cn0-80dBHz | [再生](hires_probe__48k__M700HY__awgn-cn0-80dBHz.flac) | 35.86 |
| hires_probe | M700HY | codec | [再生](hires_probe__48k__M700HY__codec.flac) | 54.19 |
| hires_probe | M700HY | ideal | [再生](hires_probe__48k__M700HY__ideal.flac) | 54.19 |
| hires_probe | M700H | awgn-cn0-65dBHz | [再生](hires_probe__48k__M700H__awgn-cn0-65dBHz.flac) | 20.76 |
| hires_probe | M700H | awgn-cn0-70dBHz | [再生](hires_probe__48k__M700H__awgn-cn0-70dBHz.flac) | 23.45 |
| hires_probe | M700H | awgn-cn0-75dBHz | [再生](hires_probe__48k__M700H__awgn-cn0-75dBHz.flac) | 28.31 |
| hires_probe | M700H | awgn-cn0-80dBHz | [再生](hires_probe__48k__M700H__awgn-cn0-80dBHz.flac) | 41.79 |
| hires_probe | M700H | codec | [再生](hires_probe__48k__M700H__codec.flac) | 49.25 |
| hires_probe | M700Y | awgn-cn0-65dBHz | [再生](hires_probe__48k__M700Y__awgn-cn0-65dBHz.flac) | 13.23 |
| hires_probe | M700Y | awgn-cn0-70dBHz | [再生](hires_probe__48k__M700Y__awgn-cn0-70dBHz.flac) | 15.39 |
| hires_probe | M700Y | codec | [再生](hires_probe__48k__M700Y__codec.flac) | 40.26 |
| hires_probe | M700Y | ideal | [再生](hires_probe__48k__M700Y__ideal.flac) | 40.26 |
| hires_probe | M700 | awgn-cn0-65dBHz | [再生](hires_probe__48k__M700__awgn-cn0-65dBHz.flac) | 12.86 |
| hires_probe | M700 | awgn-cn0-70dBHz | [再生](hires_probe__48k__M700__awgn-cn0-70dBHz.flac) | 15.10 |
| hires_probe | M700 | codec | [再生](hires_probe__48k__M700__codec.flac) | 39.90 |
| vibeace | M700HY | awgn-cn0-65dBHz | [再生](vibeace__48k__M700HY__awgn-cn0-65dBHz.flac) | 32.20 |
| vibeace | M700HY | awgn-cn0-70dBHz | [再生](vibeace__48k__M700HY__awgn-cn0-70dBHz.flac) | 39.08 |
| vibeace | M700HY | awgn-cn0-75dBHz | [再生](vibeace__48k__M700HY__awgn-cn0-75dBHz.flac) | 44.34 |
| vibeace | M700HY | awgn-cn0-80dBHz | [再生](vibeace__48k__M700HY__awgn-cn0-80dBHz.flac) | 52.30 |
| vibeace | M700HY | codec | [再生](vibeace__48k__M700HY__codec.flac) | 68.47 |
| vibeace | M700HY | ideal | [再生](vibeace__48k__M700HY__ideal.flac) | 68.47 |
| vibeace | M700Y | awgn-cn0-65dBHz | [再生](vibeace__48k__M700Y__awgn-cn0-65dBHz.flac) | 13.80 |
| vibeace | M700Y | awgn-cn0-70dBHz | [再生](vibeace__48k__M700Y__awgn-cn0-70dBHz.flac) | 15.70 |
| vibeace | M700Y | codec | [再生](vibeace__48k__M700Y__codec.flac) | 68.19 |
| vibeace | M700Y | ideal | [再生](vibeace__48k__M700Y__ideal.flac) | 68.19 |

## 原音

- [demo](demo__48k__reference.flac)
- [fishin](fishin__48k__reference.flac)
- [hires_probe](hires_probe__48k__reference.flac)
- [vibeace](vibeace__48k__reference.flac)
