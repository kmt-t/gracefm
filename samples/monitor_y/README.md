# 現行サンプル音声 — 48 kHz Y系・高域試験

**全デジタル主系・副系に標準アッテネータを含む現行設定の音声です。** 各10秒。保存したFLACを読み戻して波形SNRを再測定しています。

[命名規則](../NAMING.md) · [設定表](../../docs/PROFILES.md) · [全音源の設定・測定値・SHA-256](../../docs/results/samples.json)

32 kHzの2系統は電力50:50。48 kHzの `M700+SUB100-48K` は75:25。それ以外の48 kHz音声は主系1系統です。`codec` は通信路なし、`ideal` は雑音なしのシンボル送受信。AWGN等は同期既知のシミュレーションです。

`M700-base` は実際の基本層を保持し、拡張層の事後確率だけを0.5にした比較音源です。標準アッテネータを含みます。`R10` / `R12` はY仮数幅の比較条件です。

波形SNRは原音との差であり、聴感の点数ではありません。

| 音源 | 構成 | 条件 | 試聴 | 波形SNR dB |
|---|---|---|---|---:|
| demo | M700MY | awgn-cn0-65dBHz | [再生](demo__48k__M700MY__awgn-cn0-65dBHz.flac) | 14.26 |
| demo | M700MY | awgn-cn0-70dBHz | [再生](demo__48k__M700MY__awgn-cn0-70dBHz.flac) | 16.67 |
| demo | M700MY | codec | [再生](demo__48k__M700MY__codec.flac) | 24.27 |
| demo | M700MY | ideal | [再生](demo__48k__M700MY__ideal.flac) | 24.27 |
| demo | M700Y-R10 | awgn-cn0-65dBHz | [再生](demo__48k__M700Y-R10__awgn-cn0-65dBHz.flac) | 14.29 |
| demo | M700Y-R10 | awgn-cn0-70dBHz | [再生](demo__48k__M700Y-R10__awgn-cn0-70dBHz.flac) | 16.21 |
| demo | M700Y-R10 | awgn-cn0-75dBHz | [再生](demo__48k__M700Y-R10__awgn-cn0-75dBHz.flac) | 21.11 |
| demo | M700Y-R10 | awgn-cn0-80dBHz | [再生](demo__48k__M700Y-R10__awgn-cn0-80dBHz.flac) | 32.23 |
| demo | M700Y-R10 | codec | [再生](demo__48k__M700Y-R10__codec.flac) | 40.34 |
| demo | M700Y-R12 | awgn-cn0-65dBHz | [再生](demo__48k__M700Y-R12__awgn-cn0-65dBHz.flac) | 14.31 |
| demo | M700Y-R12 | awgn-cn0-70dBHz | [再生](demo__48k__M700Y-R12__awgn-cn0-70dBHz.flac) | 16.24 |
| demo | M700Y-R12 | awgn-cn0-75dBHz | [再生](demo__48k__M700Y-R12__awgn-cn0-75dBHz.flac) | 21.17 |
| demo | M700Y-R12 | awgn-cn0-80dBHz | [再生](demo__48k__M700Y-R12__awgn-cn0-80dBHz.flac) | 32.20 |
| demo | M700Y-R12 | codec | [再生](demo__48k__M700Y-R12__codec.flac) | 40.34 |
| demo | M700Y | awgn-cn0-65dBHz | [再生](demo__48k__M700Y__awgn-cn0-65dBHz.flac) | 14.30 |
| demo | M700Y | awgn-cn0-70dBHz | [再生](demo__48k__M700Y__awgn-cn0-70dBHz.flac) | 16.22 |
| demo | M700Y | awgn-cn0-75dBHz | [再生](demo__48k__M700Y__awgn-cn0-75dBHz.flac) | 21.14 |
| demo | M700Y | awgn-cn0-80dBHz | [再生](demo__48k__M700Y__awgn-cn0-80dBHz.flac) | 32.19 |
| demo | M700Y | codec | [再生](demo__48k__M700Y__codec.flac) | 40.32 |
| demo | M700Y | ideal | [再生](demo__48k__M700Y__ideal.flac) | 40.32 |
| fishin | M700MY | awgn-cn0-65dBHz | [再生](fishin__48k__M700MY__awgn-cn0-65dBHz.flac) | 13.61 |
| fishin | M700MY | awgn-cn0-70dBHz | [再生](fishin__48k__M700MY__awgn-cn0-70dBHz.flac) | 16.47 |
| fishin | M700MY | codec | [再生](fishin__48k__M700MY__codec.flac) | 55.46 |
| fishin | M700MY | ideal | [再生](fishin__48k__M700MY__ideal.flac) | 55.46 |
| fishin | M700Y | awgn-cn0-65dBHz | [再生](fishin__48k__M700Y__awgn-cn0-65dBHz.flac) | 13.05 |
| fishin | M700Y | awgn-cn0-70dBHz | [再生](fishin__48k__M700Y__awgn-cn0-70dBHz.flac) | 15.12 |
| fishin | M700Y | awgn-cn0-75dBHz | [再生](fishin__48k__M700Y__awgn-cn0-75dBHz.flac) | 20.17 |
| fishin | M700Y | awgn-cn0-80dBHz | [再生](fishin__48k__M700Y__awgn-cn0-80dBHz.flac) | 33.53 |
| fishin | M700Y | codec | [再生](fishin__48k__M700Y__codec.flac) | 55.46 |
| fishin | M700Y | ideal | [再生](fishin__48k__M700Y__ideal.flac) | 55.46 |
| hires_probe | M700MY | awgn-cn0-65dBHz | [再生](hires_probe__48k__M700MY__awgn-cn0-65dBHz.flac) | 13.53 |
| hires_probe | M700MY | awgn-cn0-70dBHz | [再生](hires_probe__48k__M700MY__awgn-cn0-70dBHz.flac) | 16.24 |
| hires_probe | M700MY | codec | [再生](hires_probe__48k__M700MY__codec.flac) | 24.33 |
| hires_probe | M700MY | ideal | [再生](hires_probe__48k__M700MY__ideal.flac) | 24.33 |
| hires_probe | M700M | awgn-cn0-65dBHz | [再生](hires_probe__48k__M700M__awgn-cn0-65dBHz.flac) | 13.34 |
| hires_probe | M700M | awgn-cn0-70dBHz | [再生](hires_probe__48k__M700M__awgn-cn0-70dBHz.flac) | 16.33 |
| hires_probe | M700M | codec | [再生](hires_probe__48k__M700M__codec.flac) | 24.32 |
| hires_probe | M700Y-R10 | awgn-cn0-65dBHz | [再生](hires_probe__48k__M700Y-R10__awgn-cn0-65dBHz.flac) | 13.22 |
| hires_probe | M700Y-R10 | awgn-cn0-70dBHz | [再生](hires_probe__48k__M700Y-R10__awgn-cn0-70dBHz.flac) | 15.38 |
| hires_probe | M700Y-R10 | awgn-cn0-75dBHz | [再生](hires_probe__48k__M700Y-R10__awgn-cn0-75dBHz.flac) | 20.41 |
| hires_probe | M700Y-R10 | awgn-cn0-80dBHz | [再生](hires_probe__48k__M700Y-R10__awgn-cn0-80dBHz.flac) | 30.39 |
| hires_probe | M700Y-R10 | codec | [再生](hires_probe__48k__M700Y-R10__codec.flac) | 40.40 |
| hires_probe | M700Y-R12 | awgn-cn0-65dBHz | [再生](hires_probe__48k__M700Y-R12__awgn-cn0-65dBHz.flac) | 13.25 |
| hires_probe | M700Y-R12 | awgn-cn0-70dBHz | [再生](hires_probe__48k__M700Y-R12__awgn-cn0-70dBHz.flac) | 15.43 |
| hires_probe | M700Y-R12 | awgn-cn0-75dBHz | [再生](hires_probe__48k__M700Y-R12__awgn-cn0-75dBHz.flac) | 20.44 |
| hires_probe | M700Y-R12 | awgn-cn0-80dBHz | [再生](hires_probe__48k__M700Y-R12__awgn-cn0-80dBHz.flac) | 30.43 |
| hires_probe | M700Y-R12 | codec | [再生](hires_probe__48k__M700Y-R12__codec.flac) | 40.41 |
| hires_probe | M700Y | awgn-cn0-65dBHz | [再生](hires_probe__48k__M700Y__awgn-cn0-65dBHz.flac) | 13.23 |
| hires_probe | M700Y | awgn-cn0-70dBHz | [再生](hires_probe__48k__M700Y__awgn-cn0-70dBHz.flac) | 15.39 |
| hires_probe | M700Y | awgn-cn0-75dBHz | [再生](hires_probe__48k__M700Y__awgn-cn0-75dBHz.flac) | 20.39 |
| hires_probe | M700Y | awgn-cn0-80dBHz | [再生](hires_probe__48k__M700Y__awgn-cn0-80dBHz.flac) | 30.27 |
| hires_probe | M700Y | codec | [再生](hires_probe__48k__M700Y__codec.flac) | 40.26 |
| hires_probe | M700Y | ideal | [再生](hires_probe__48k__M700Y__ideal.flac) | 40.26 |
| hires_probe | M700 | awgn-cn0-65dBHz | [再生](hires_probe__48k__M700__awgn-cn0-65dBHz.flac) | 12.86 |
| hires_probe | M700 | awgn-cn0-70dBHz | [再生](hires_probe__48k__M700__awgn-cn0-70dBHz.flac) | 15.10 |
| hires_probe | M700 | awgn-cn0-75dBHz | [再生](hires_probe__48k__M700__awgn-cn0-75dBHz.flac) | 20.88 |
| hires_probe | M700 | awgn-cn0-80dBHz | [再生](hires_probe__48k__M700__awgn-cn0-80dBHz.flac) | 34.57 |
| hires_probe | M700 | codec | [再生](hires_probe__48k__M700__codec.flac) | 39.90 |
| vibeace | M700MY | awgn-cn0-65dBHz | [再生](vibeace__48k__M700MY__awgn-cn0-65dBHz.flac) | 14.34 |
| vibeace | M700MY | awgn-cn0-70dBHz | [再生](vibeace__48k__M700MY__awgn-cn0-70dBHz.flac) | 17.25 |
| vibeace | M700MY | codec | [再生](vibeace__48k__M700MY__codec.flac) | 68.19 |
| vibeace | M700MY | ideal | [再生](vibeace__48k__M700MY__ideal.flac) | 68.19 |
| vibeace | M700Y | awgn-cn0-65dBHz | [再生](vibeace__48k__M700Y__awgn-cn0-65dBHz.flac) | 13.80 |
| vibeace | M700Y | awgn-cn0-70dBHz | [再生](vibeace__48k__M700Y__awgn-cn0-70dBHz.flac) | 15.70 |
| vibeace | M700Y | awgn-cn0-75dBHz | [再生](vibeace__48k__M700Y__awgn-cn0-75dBHz.flac) | 20.64 |
| vibeace | M700Y | awgn-cn0-80dBHz | [再生](vibeace__48k__M700Y__awgn-cn0-80dBHz.flac) | 34.59 |
| vibeace | M700Y | codec | [再生](vibeace__48k__M700Y__codec.flac) | 68.19 |
| vibeace | M700Y | ideal | [再生](vibeace__48k__M700Y__ideal.flac) | 68.19 |

## 原音

- [demo](demo__48k__reference.flac)
- [fishin](fishin__48k__reference.flac)
- [hires_probe](hires_probe__48k__reference.flac)
- [vibeace](vibeace__48k__reference.flac)
