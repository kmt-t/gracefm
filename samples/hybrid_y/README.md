# 現行サンプル音声 — 32 kHz Y系

**全デジタル主系・副系に標準アッテネータを含む現行設定の音声です。** 各10秒。保存したFLACを読み戻して波形SNRを再測定しています。

[命名規則](../NAMING.md) · [設定表](../../docs/PROFILES.md) · [全音源の設定・測定値・SHA-256](../../docs/results/samples.json)

32 kHzの2系統は電力50:50。48 kHzの `M700H+S100-48K` は75:25。それ以外の48 kHz音声は主系1系統です。`codec` は通信路なし、`ideal` は雑音なしのシンボル送受信。AWGN等は同期既知のシミュレーションです。

`M700H-base` は実際の基本層を保持し、拡張層の事後確率だけを0.5にした比較音源です。係数別昇格1bitと標準アッテネータを含みます。`R10` / `R12` はY仮数幅の比較条件です。

波形SNRは原音との差であり、聴感の点数ではありません。

| 音源 | 構成 | 条件 | 試聴 | 波形SNR dB |
|---|---|---|---|---:|
| demo | B200HY+S100 | awgn-cn0-54dBHz | [再生](demo__32k__B200HY+S100__awgn-cn0-54dBHz.flac) | 4.80 |
| demo | B200HY+S100 | awgn-cn0-57dBHz | [再生](demo__32k__B200HY+S100__awgn-cn0-57dBHz.flac) | 16.72 |
| demo | B200HY+S100 | awgn-cn0-60dBHz | [再生](demo__32k__B200HY+S100__awgn-cn0-60dBHz.flac) | 24.29 |
| demo | B200HY+S100 | awgn-cn0-66dBHz | [再生](demo__32k__B200HY+S100__awgn-cn0-66dBHz.flac) | 30.98 |
| demo | B200HY+S100 | awgn-cn0-80dBHz | [再生](demo__32k__B200HY+S100__awgn-cn0-80dBHz.flac) | 47.13 |
| demo | B200HY+S100 | main-fade-10dB-cn0-66dBHz | [再生](demo__32k__B200HY+S100__main-fade-10dB-cn0-66dBHz.flac) | 26.32 |
| demo | B200HY+S100 | phase-only-awgn-cn0-66dBHz | [再生](demo__32k__B200HY+S100__phase-only-awgn-cn0-66dBHz.flac) | 31.20 |
| demo | B200HY+S100 | rayleigh-cn0-60dBHz | [再生](demo__32k__B200HY+S100__rayleigh-cn0-60dBHz.flac) | 10.52 |
| demo | B200HY | codec | [再生](demo__32k__B200HY__codec.flac) | 60.99 |
| demo | B200HY | ideal | [再生](demo__32k__B200HY__ideal.flac) | 60.99 |
| fishin | B200MHY+S50M | awgn-cn0-54dBHz | [再生](fishin__32k__B200MHY+S50M__awgn-cn0-54dBHz.flac) | 10.55 |
| fishin | B200MHY+S50M | awgn-cn0-57dBHz | [再生](fishin__32k__B200MHY+S50M__awgn-cn0-57dBHz.flac) | 16.40 |
| fishin | B200MHY+S50M | awgn-cn0-60dBHz | [再生](fishin__32k__B200MHY+S50M__awgn-cn0-60dBHz.flac) | 20.57 |
| fishin | B200MHY+S50M | awgn-cn0-66dBHz | [再生](fishin__32k__B200MHY+S50M__awgn-cn0-66dBHz.flac) | 25.38 |
| fishin | B200MHY+S50M | awgn-cn0-80dBHz | [再生](fishin__32k__B200MHY+S50M__awgn-cn0-80dBHz.flac) | 35.12 |
| fishin | B200MHY+S50M | main-fade-10dB-cn0-66dBHz | [再生](fishin__32k__B200MHY+S50M__main-fade-10dB-cn0-66dBHz.flac) | 17.13 |
| fishin | B200MHY+S50M | phase-only-awgn-cn0-66dBHz | [再生](fishin__32k__B200MHY+S50M__phase-only-awgn-cn0-66dBHz.flac) | 22.90 |
| fishin | B200MHY+S50M | rayleigh-cn0-60dBHz | [再生](fishin__32k__B200MHY+S50M__rayleigh-cn0-60dBHz.flac) | 12.56 |
| fishin | B200MHY | codec | [再生](fishin__32k__B200MHY__codec.flac) | 52.22 |
| fishin | B200MHY | ideal | [再生](fishin__32k__B200MHY__ideal.flac) | 52.22 |
| vibeace | B200MHY+S50M | awgn-cn0-54dBHz | [再生](vibeace__32k__B200MHY+S50M__awgn-cn0-54dBHz.flac) | 13.43 |
| vibeace | B200MHY+S50M | awgn-cn0-57dBHz | [再生](vibeace__32k__B200MHY+S50M__awgn-cn0-57dBHz.flac) | 20.33 |
| vibeace | B200MHY+S50M | awgn-cn0-60dBHz | [再生](vibeace__32k__B200MHY+S50M__awgn-cn0-60dBHz.flac) | 28.90 |
| vibeace | B200MHY+S50M | awgn-cn0-66dBHz | [再生](vibeace__32k__B200MHY+S50M__awgn-cn0-66dBHz.flac) | 38.48 |
| vibeace | B200MHY+S50M | awgn-cn0-80dBHz | [再生](vibeace__32k__B200MHY+S50M__awgn-cn0-80dBHz.flac) | 49.19 |
| vibeace | B200MHY+S50M | main-fade-10dB-cn0-66dBHz | [再生](vibeace__32k__B200MHY+S50M__main-fade-10dB-cn0-66dBHz.flac) | 28.80 |
| vibeace | B200MHY+S50M | phase-only-awgn-cn0-66dBHz | [再生](vibeace__32k__B200MHY+S50M__phase-only-awgn-cn0-66dBHz.flac) | 35.27 |
| vibeace | B200MHY+S50M | rayleigh-cn0-60dBHz | [再生](vibeace__32k__B200MHY+S50M__rayleigh-cn0-60dBHz.flac) | 14.95 |
| vibeace | B200MHY | codec | [再生](vibeace__32k__B200MHY__codec.flac) | 67.00 |
| vibeace | B200MHY | ideal | [再生](vibeace__32k__B200MHY__ideal.flac) | 67.00 |

## 原音

- [demo](demo__32k__reference.flac)
- [fishin](fishin__32k__reference.flac)
- [vibeace](vibeace__32k__reference.flac)
