# 現行サンプル音声 — 48 kHz Y系・高域試験

**全デジタル主系・副系に標準アッテネータを含む現行設定の音声です。** 各10秒。保存したFLACを読み戻して波形SNRを再測定しています。

[命名規則](../NAMING.md) · [設定表](../../docs/PROFILES.md) · [全音源の設定・測定値・SHA-256](../../docs/results/samples.json)

32 kHzの2系統は電力50:50。48 kHzの `M700+SUB100-48K` は75:25。それ以外の48 kHz音声は主系1系統です。`codec` は通信路なし、`ideal` は雑音なしのシンボル送受信。AWGN等は同期既知のシミュレーションです。

`M700-base` は実際の基本層を保持し、拡張層の事後確率だけを0.5にした比較音源です。標準アッテネータを含みます。`R10` / `R12` はY仮数幅の比較条件です。

波形SNRは原音との差であり、聴感の点数ではありません。

| 音源 | 構成 | 条件 | 試聴 | 波形SNR dB |
|---|---|---|---|---:|
| demo | M700MY | awgn-cn0-65dBHz | [再生](demo__48k__M700MY__awgn-cn0-65dBHz.flac) | 23.49 |
| demo | M700MY | awgn-cn0-70dBHz | [再生](demo__48k__M700MY__awgn-cn0-70dBHz.flac) | 23.97 |
| demo | M700MY | codec | [再生](demo__48k__M700MY__codec.flac) | 24.27 |
| demo | M700MY | ideal | [再生](demo__48k__M700MY__ideal.flac) | 24.27 |
| demo | M700Y-R10 | awgn-cn0-65dBHz | [再生](demo__48k__M700Y-R10__awgn-cn0-65dBHz.flac) | 24.26 |
| demo | M700Y-R10 | awgn-cn0-70dBHz | [再生](demo__48k__M700Y-R10__awgn-cn0-70dBHz.flac) | 24.98 |
| demo | M700Y-R10 | awgn-cn0-75dBHz | [再生](demo__48k__M700Y-R10__awgn-cn0-75dBHz.flac) | 25.40 |
| demo | M700Y-R10 | awgn-cn0-80dBHz | [再生](demo__48k__M700Y-R10__awgn-cn0-80dBHz.flac) | 25.50 |
| demo | M700Y-R10 | codec | [再生](demo__48k__M700Y-R10__codec.flac) | 25.52 |
| demo | M700Y-R12 | awgn-cn0-65dBHz | [再生](demo__48k__M700Y-R12__awgn-cn0-65dBHz.flac) | 24.26 |
| demo | M700Y-R12 | awgn-cn0-70dBHz | [再生](demo__48k__M700Y-R12__awgn-cn0-70dBHz.flac) | 24.98 |
| demo | M700Y-R12 | awgn-cn0-75dBHz | [再生](demo__48k__M700Y-R12__awgn-cn0-75dBHz.flac) | 25.40 |
| demo | M700Y-R12 | awgn-cn0-80dBHz | [再生](demo__48k__M700Y-R12__awgn-cn0-80dBHz.flac) | 25.50 |
| demo | M700Y-R12 | codec | [再生](demo__48k__M700Y-R12__codec.flac) | 25.52 |
| demo | M700Y | awgn-cn0-65dBHz | [再生](demo__48k__M700Y__awgn-cn0-65dBHz.flac) | 24.27 |
| demo | M700Y | awgn-cn0-70dBHz | [再生](demo__48k__M700Y__awgn-cn0-70dBHz.flac) | 24.98 |
| demo | M700Y | awgn-cn0-75dBHz | [再生](demo__48k__M700Y__awgn-cn0-75dBHz.flac) | 25.41 |
| demo | M700Y | awgn-cn0-80dBHz | [再生](demo__48k__M700Y__awgn-cn0-80dBHz.flac) | 25.50 |
| demo | M700Y | codec | [再生](demo__48k__M700Y__codec.flac) | 25.52 |
| demo | M700Y | ideal | [再生](demo__48k__M700Y__ideal.flac) | 25.52 |
| fishin | M700MY | awgn-cn0-65dBHz | [再生](fishin__48k__M700MY__awgn-cn0-65dBHz.flac) | 26.16 |
| fishin | M700MY | awgn-cn0-70dBHz | [再生](fishin__48k__M700MY__awgn-cn0-70dBHz.flac) | 30.75 |
| fishin | M700MY | codec | [再生](fishin__48k__M700MY__codec.flac) | 54.86 |
| fishin | M700MY | ideal | [再生](fishin__48k__M700MY__ideal.flac) | 54.86 |
| fishin | M700Y | awgn-cn0-65dBHz | [再生](fishin__48k__M700Y__awgn-cn0-65dBHz.flac) | 25.00 |
| fishin | M700Y | awgn-cn0-70dBHz | [再生](fishin__48k__M700Y__awgn-cn0-70dBHz.flac) | 29.33 |
| fishin | M700Y | awgn-cn0-75dBHz | [再生](fishin__48k__M700Y__awgn-cn0-75dBHz.flac) | 34.81 |
| fishin | M700Y | awgn-cn0-80dBHz | [再生](fishin__48k__M700Y__awgn-cn0-80dBHz.flac) | 40.08 |
| fishin | M700Y | codec | [再生](fishin__48k__M700Y__codec.flac) | 54.86 |
| fishin | M700Y | ideal | [再生](fishin__48k__M700Y__ideal.flac) | 54.86 |
| hires_probe | M700MY | awgn-cn0-65dBHz | [再生](hires_probe__48k__M700MY__awgn-cn0-65dBHz.flac) | 21.87 |
| hires_probe | M700MY | awgn-cn0-70dBHz | [再生](hires_probe__48k__M700MY__awgn-cn0-70dBHz.flac) | 23.31 |
| hires_probe | M700MY | codec | [再生](hires_probe__48k__M700MY__codec.flac) | 24.32 |
| hires_probe | M700MY | ideal | [再生](hires_probe__48k__M700MY__ideal.flac) | 24.32 |
| hires_probe | M700M | awgn-cn0-65dBHz | [再生](hires_probe__48k__M700M__awgn-cn0-65dBHz.flac) | 22.70 |
| hires_probe | M700M | awgn-cn0-70dBHz | [再生](hires_probe__48k__M700M__awgn-cn0-70dBHz.flac) | 23.81 |
| hires_probe | M700M | codec | [再生](hires_probe__48k__M700M__codec.flac) | 24.32 |
| hires_probe | M700Y-R10 | awgn-cn0-65dBHz | [再生](hires_probe__48k__M700Y-R10__awgn-cn0-65dBHz.flac) | 21.77 |
| hires_probe | M700Y-R10 | awgn-cn0-70dBHz | [再生](hires_probe__48k__M700Y-R10__awgn-cn0-70dBHz.flac) | 23.78 |
| hires_probe | M700Y-R10 | awgn-cn0-75dBHz | [再生](hires_probe__48k__M700Y-R10__awgn-cn0-75dBHz.flac) | 24.96 |
| hires_probe | M700Y-R10 | awgn-cn0-80dBHz | [再生](hires_probe__48k__M700Y-R10__awgn-cn0-80dBHz.flac) | 25.38 |
| hires_probe | M700Y-R10 | codec | [再生](hires_probe__48k__M700Y-R10__codec.flac) | 25.58 |
| hires_probe | M700Y-R12 | awgn-cn0-65dBHz | [再生](hires_probe__48k__M700Y-R12__awgn-cn0-65dBHz.flac) | 21.76 |
| hires_probe | M700Y-R12 | awgn-cn0-70dBHz | [再生](hires_probe__48k__M700Y-R12__awgn-cn0-70dBHz.flac) | 23.78 |
| hires_probe | M700Y-R12 | awgn-cn0-75dBHz | [再生](hires_probe__48k__M700Y-R12__awgn-cn0-75dBHz.flac) | 24.96 |
| hires_probe | M700Y-R12 | awgn-cn0-80dBHz | [再生](hires_probe__48k__M700Y-R12__awgn-cn0-80dBHz.flac) | 25.38 |
| hires_probe | M700Y-R12 | codec | [再生](hires_probe__48k__M700Y-R12__codec.flac) | 25.58 |
| hires_probe | M700Y | awgn-cn0-65dBHz | [再生](hires_probe__48k__M700Y__awgn-cn0-65dBHz.flac) | 21.88 |
| hires_probe | M700Y | awgn-cn0-70dBHz | [再生](hires_probe__48k__M700Y__awgn-cn0-70dBHz.flac) | 23.85 |
| hires_probe | M700Y | awgn-cn0-75dBHz | [再生](hires_probe__48k__M700Y__awgn-cn0-75dBHz.flac) | 24.99 |
| hires_probe | M700Y | awgn-cn0-80dBHz | [再生](hires_probe__48k__M700Y__awgn-cn0-80dBHz.flac) | 25.39 |
| hires_probe | M700Y | codec | [再生](hires_probe__48k__M700Y__codec.flac) | 25.58 |
| hires_probe | M700Y | ideal | [再生](hires_probe__48k__M700Y__ideal.flac) | 25.58 |
| hires_probe | M700 | awgn-cn0-65dBHz | [再生](hires_probe__48k__M700__awgn-cn0-65dBHz.flac) | 23.85 |
| hires_probe | M700 | awgn-cn0-70dBHz | [再生](hires_probe__48k__M700__awgn-cn0-70dBHz.flac) | 24.65 |
| hires_probe | M700 | awgn-cn0-75dBHz | [再生](hires_probe__48k__M700__awgn-cn0-75dBHz.flac) | 25.39 |
| hires_probe | M700 | awgn-cn0-80dBHz | [再生](hires_probe__48k__M700__awgn-cn0-80dBHz.flac) | 25.58 |
| hires_probe | M700 | codec | [再生](hires_probe__48k__M700__codec.flac) | 25.58 |
| vibeace | M700MY | awgn-cn0-65dBHz | [再生](vibeace__48k__M700MY__awgn-cn0-65dBHz.flac) | 32.83 |
| vibeace | M700MY | awgn-cn0-70dBHz | [再生](vibeace__48k__M700MY__awgn-cn0-70dBHz.flac) | 37.60 |
| vibeace | M700MY | codec | [再生](vibeace__48k__M700MY__codec.flac) | 64.37 |
| vibeace | M700MY | ideal | [再生](vibeace__48k__M700MY__ideal.flac) | 64.37 |
| vibeace | M700Y | awgn-cn0-65dBHz | [再生](vibeace__48k__M700Y__awgn-cn0-65dBHz.flac) | 30.65 |
| vibeace | M700Y | awgn-cn0-70dBHz | [再生](vibeace__48k__M700Y__awgn-cn0-70dBHz.flac) | 35.59 |
| vibeace | M700Y | awgn-cn0-75dBHz | [再生](vibeace__48k__M700Y__awgn-cn0-75dBHz.flac) | 43.71 |
| vibeace | M700Y | awgn-cn0-80dBHz | [再生](vibeace__48k__M700Y__awgn-cn0-80dBHz.flac) | 52.58 |
| vibeace | M700Y | codec | [再生](vibeace__48k__M700Y__codec.flac) | 64.37 |
| vibeace | M700Y | ideal | [再生](vibeace__48k__M700Y__ideal.flac) | 64.37 |

## 原音

- [demo](demo__48k__reference.flac)
- [fishin](fishin__48k__reference.flac)
- [hires_probe](hires_probe__48k__reference.flac)
- [vibeace](vibeace__48k__reference.flac)
