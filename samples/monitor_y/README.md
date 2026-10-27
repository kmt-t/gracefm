# 現行サンプル音声 — 48 kHz Y系・高域試験

**全デジタル主系・副系に標準アッテネータを含む現行設定の音声です。** 各10秒。保存したFLACを読み戻して波形SNRを再測定しています。

[命名規則](../NAMING.md) · [設定表](../../docs/PROFILES.md) · [全音源の設定・測定値・SHA-256](../../docs/results/samples.json)

2系統は主系・副系とも独立のチャンネルで、電力を分け合わない（C/N0は同じ値）。それ以外の48 kHz音声は主系1系統です。`codec` は通信路なし、`ideal` は雑音なしのシンボル送受信。AWGN等は同期既知のシミュレーションです。

`M700-base` は実際の基本層を保持し、拡張層の事後確率だけを0.5にした比較音源です。標準アッテネータを含みます。`R10` / `R12` はY仮数幅の比較条件です。

波形SNRは原音との差であり、聴感の点数ではありません。

| 音源 | 構成 | 条件 | 試聴 | 波形SNR dB |
|---|---|---|---|---:|
| demo | M700MY | awgn-cn0-65dBHz | [再生](demo__48k__M700MY__awgn-cn0-65dBHz.flac) | 23.49 |
| demo | M700MY | awgn-cn0-70dBHz | [再生](demo__48k__M700MY__awgn-cn0-70dBHz.flac) | 23.97 |
| demo | M700MY | codec | [再生](demo__48k__M700MY__codec.flac) | 24.27 |
| demo | M700MY | ideal | [再生](demo__48k__M700MY__ideal.flac) | 24.27 |
| demo | M700Y-R10 | awgn-cn0-65dBHz | [再生](demo__48k__M700Y-R10__awgn-cn0-65dBHz.flac) | 26.73 |
| demo | M700Y-R10 | awgn-cn0-70dBHz | [再生](demo__48k__M700Y-R10__awgn-cn0-70dBHz.flac) | 32.26 |
| demo | M700Y-R10 | awgn-cn0-75dBHz | [再生](demo__48k__M700Y-R10__awgn-cn0-75dBHz.flac) | 38.10 |
| demo | M700Y-R10 | awgn-cn0-80dBHz | [再生](demo__48k__M700Y-R10__awgn-cn0-80dBHz.flac) | 44.17 |
| demo | M700Y-R10 | codec | [再生](demo__48k__M700Y-R10__codec.flac) | 66.45 |
| demo | M700Y-R12 | awgn-cn0-65dBHz | [再生](demo__48k__M700Y-R12__awgn-cn0-65dBHz.flac) | 26.71 |
| demo | M700Y-R12 | awgn-cn0-70dBHz | [再生](demo__48k__M700Y-R12__awgn-cn0-70dBHz.flac) | 32.23 |
| demo | M700Y-R12 | awgn-cn0-75dBHz | [再生](demo__48k__M700Y-R12__awgn-cn0-75dBHz.flac) | 38.05 |
| demo | M700Y-R12 | awgn-cn0-80dBHz | [再生](demo__48k__M700Y-R12__awgn-cn0-80dBHz.flac) | 44.11 |
| demo | M700Y-R12 | codec | [再生](demo__48k__M700Y-R12__codec.flac) | 66.75 |
| demo | M700Y | awgn-cn0-65dBHz | [再生](demo__48k__M700Y__awgn-cn0-65dBHz.flac) | 26.70 |
| demo | M700Y | awgn-cn0-70dBHz | [再生](demo__48k__M700Y__awgn-cn0-70dBHz.flac) | 32.25 |
| demo | M700Y | awgn-cn0-75dBHz | [再生](demo__48k__M700Y__awgn-cn0-75dBHz.flac) | 38.10 |
| demo | M700Y | awgn-cn0-80dBHz | [再生](demo__48k__M700Y__awgn-cn0-80dBHz.flac) | 44.12 |
| demo | M700Y | codec | [再生](demo__48k__M700Y__codec.flac) | 59.19 |
| demo | M700Y | ideal | [再生](demo__48k__M700Y__ideal.flac) | 59.19 |
| fishin | M700MY | awgn-cn0-65dBHz | [再生](fishin__48k__M700MY__awgn-cn0-65dBHz.flac) | 26.16 |
| fishin | M700MY | awgn-cn0-70dBHz | [再生](fishin__48k__M700MY__awgn-cn0-70dBHz.flac) | 30.75 |
| fishin | M700MY | codec | [再生](fishin__48k__M700MY__codec.flac) | 54.86 |
| fishin | M700MY | ideal | [再生](fishin__48k__M700MY__ideal.flac) | 54.86 |
| fishin | M700Y | awgn-cn0-65dBHz | [再生](fishin__48k__M700Y__awgn-cn0-65dBHz.flac) | 24.45 |
| fishin | M700Y | awgn-cn0-70dBHz | [再生](fishin__48k__M700Y__awgn-cn0-70dBHz.flac) | 28.73 |
| fishin | M700Y | awgn-cn0-75dBHz | [再生](fishin__48k__M700Y__awgn-cn0-75dBHz.flac) | 34.08 |
| fishin | M700Y | awgn-cn0-80dBHz | [再生](fishin__48k__M700Y__awgn-cn0-80dBHz.flac) | 39.49 |
| fishin | M700Y | codec | [再生](fishin__48k__M700Y__codec.flac) | 54.86 |
| fishin | M700Y | ideal | [再生](fishin__48k__M700Y__ideal.flac) | 54.86 |
| hires_probe | M700MY | awgn-cn0-65dBHz | [再生](hires_probe__48k__M700MY__awgn-cn0-65dBHz.flac) | 21.87 |
| hires_probe | M700MY | awgn-cn0-70dBHz | [再生](hires_probe__48k__M700MY__awgn-cn0-70dBHz.flac) | 23.31 |
| hires_probe | M700MY | codec | [再生](hires_probe__48k__M700MY__codec.flac) | 24.32 |
| hires_probe | M700MY | ideal | [再生](hires_probe__48k__M700MY__ideal.flac) | 24.32 |
| hires_probe | M700M | awgn-cn0-65dBHz | [再生](hires_probe__48k__M700M__awgn-cn0-65dBHz.flac) | 22.70 |
| hires_probe | M700M | awgn-cn0-70dBHz | [再生](hires_probe__48k__M700M__awgn-cn0-70dBHz.flac) | 23.81 |
| hires_probe | M700M | codec | [再生](hires_probe__48k__M700M__codec.flac) | 24.32 |
| hires_probe | M700Y-R10 | awgn-cn0-65dBHz | [再生](hires_probe__48k__M700Y-R10__awgn-cn0-65dBHz.flac) | 23.19 |
| hires_probe | M700Y-R10 | awgn-cn0-70dBHz | [再生](hires_probe__48k__M700Y-R10__awgn-cn0-70dBHz.flac) | 27.41 |
| hires_probe | M700Y-R10 | awgn-cn0-75dBHz | [再生](hires_probe__48k__M700Y-R10__awgn-cn0-75dBHz.flac) | 32.56 |
| hires_probe | M700Y-R10 | awgn-cn0-80dBHz | [再生](hires_probe__48k__M700Y-R10__awgn-cn0-80dBHz.flac) | 37.79 |
| hires_probe | M700Y-R10 | codec | [再生](hires_probe__48k__M700Y-R10__codec.flac) | 65.53 |
| hires_probe | M700Y-R12 | awgn-cn0-65dBHz | [再生](hires_probe__48k__M700Y-R12__awgn-cn0-65dBHz.flac) | 23.17 |
| hires_probe | M700Y-R12 | awgn-cn0-70dBHz | [再生](hires_probe__48k__M700Y-R12__awgn-cn0-70dBHz.flac) | 27.39 |
| hires_probe | M700Y-R12 | awgn-cn0-75dBHz | [再生](hires_probe__48k__M700Y-R12__awgn-cn0-75dBHz.flac) | 32.54 |
| hires_probe | M700Y-R12 | awgn-cn0-80dBHz | [再生](hires_probe__48k__M700Y-R12__awgn-cn0-80dBHz.flac) | 37.77 |
| hires_probe | M700Y-R12 | codec | [再生](hires_probe__48k__M700Y-R12__codec.flac) | 66.71 |
| hires_probe | M700Y | awgn-cn0-65dBHz | [再生](hires_probe__48k__M700Y__awgn-cn0-65dBHz.flac) | 23.38 |
| hires_probe | M700Y | awgn-cn0-70dBHz | [再生](hires_probe__48k__M700Y__awgn-cn0-70dBHz.flac) | 27.61 |
| hires_probe | M700Y | awgn-cn0-75dBHz | [再生](hires_probe__48k__M700Y__awgn-cn0-75dBHz.flac) | 32.78 |
| hires_probe | M700Y | awgn-cn0-80dBHz | [再生](hires_probe__48k__M700Y__awgn-cn0-80dBHz.flac) | 37.94 |
| hires_probe | M700Y | codec | [再生](hires_probe__48k__M700Y__codec.flac) | 53.31 |
| hires_probe | M700Y | ideal | [再生](hires_probe__48k__M700Y__ideal.flac) | 53.31 |
| hires_probe | M700 | awgn-cn0-65dBHz | [再生](hires_probe__48k__M700__awgn-cn0-65dBHz.flac) | 24.77 |
| hires_probe | M700 | awgn-cn0-70dBHz | [再生](hires_probe__48k__M700__awgn-cn0-70dBHz.flac) | 28.56 |
| hires_probe | M700 | awgn-cn0-75dBHz | [再生](hires_probe__48k__M700__awgn-cn0-75dBHz.flac) | 34.48 |
| hires_probe | M700 | awgn-cn0-80dBHz | [再生](hires_probe__48k__M700__awgn-cn0-80dBHz.flac) | 40.14 |
| hires_probe | M700 | codec | [再生](hires_probe__48k__M700__codec.flac) | 40.31 |
| vibeace | M700MY | awgn-cn0-65dBHz | [再生](vibeace__48k__M700MY__awgn-cn0-65dBHz.flac) | 32.83 |
| vibeace | M700MY | awgn-cn0-70dBHz | [再生](vibeace__48k__M700MY__awgn-cn0-70dBHz.flac) | 37.60 |
| vibeace | M700MY | codec | [再生](vibeace__48k__M700MY__codec.flac) | 64.37 |
| vibeace | M700MY | ideal | [再生](vibeace__48k__M700MY__ideal.flac) | 64.37 |
| vibeace | M700Y | awgn-cn0-65dBHz | [再生](vibeace__48k__M700Y__awgn-cn0-65dBHz.flac) | 31.24 |
| vibeace | M700Y | awgn-cn0-70dBHz | [再生](vibeace__48k__M700Y__awgn-cn0-70dBHz.flac) | 34.99 |
| vibeace | M700Y | awgn-cn0-75dBHz | [再生](vibeace__48k__M700Y__awgn-cn0-75dBHz.flac) | 42.39 |
| vibeace | M700Y | awgn-cn0-80dBHz | [再生](vibeace__48k__M700Y__awgn-cn0-80dBHz.flac) | 51.42 |
| vibeace | M700Y | codec | [再生](vibeace__48k__M700Y__codec.flac) | 64.37 |
| vibeace | M700Y | ideal | [再生](vibeace__48k__M700Y__ideal.flac) | 64.37 |

## 原音

- [demo](demo__48k__reference.flac)
- [fishin](fishin__48k__reference.flac)
- [hires_probe](hires_probe__48k__reference.flac)
- [vibeace](vibeace__48k__reference.flac)
