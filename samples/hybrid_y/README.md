# 現行サンプル音声 — 32 kHz Y系

**全デジタル主系・副系に標準アッテネータを含む現行設定の音声です。** 各10秒。保存したFLACを読み戻して波形SNRを再測定しています。

[命名規則](../NAMING.md) · [設定表](../../docs/PROFILES.md) · [全音源の設定・測定値・SHA-256](../../docs/results/samples.json)

2系統は主系・副系とも独立のチャンネルで、電力を分け合わない（C/N0は同じ値）。それ以外の48 kHz音声は主系1系統です。`codec` は通信路なし、`ideal` は雑音なしのシンボル送受信。AWGN等は同期既知のシミュレーションです。

`M700-base` は実際の基本層を保持し、拡張層の事後確率だけを0.5にした比較音源です。標準アッテネータを含みます。`R10` / `R12` はY仮数幅の比較条件です。

波形SNRは原音との差であり、聴感の点数ではありません。

| 音源 | 構成 | 条件 | 試聴 | 波形SNR dB |
|---|---|---|---|---:|
| demo | B200Y+SUB100 | awgn-cn0-54dBHz | [再生](demo__32k__B200Y+SUB100__awgn-cn0-54dBHz.flac) | 14.91 |
| demo | B200Y+SUB100 | awgn-cn0-57dBHz | [再生](demo__32k__B200Y+SUB100__awgn-cn0-57dBHz.flac) | 21.07 |
| demo | B200Y+SUB100 | awgn-cn0-60dBHz | [再生](demo__32k__B200Y+SUB100__awgn-cn0-60dBHz.flac) | 31.83 |
| demo | B200Y+SUB100 | awgn-cn0-66dBHz | [再生](demo__32k__B200Y+SUB100__awgn-cn0-66dBHz.flac) | 37.25 |
| demo | B200Y+SUB100 | awgn-cn0-80dBHz | [再生](demo__32k__B200Y+SUB100__awgn-cn0-80dBHz.flac) | 50.59 |
| demo | B200Y+SUB100 | main-fade-10dB-cn0-66dBHz | [再生](demo__32k__B200Y+SUB100__main-fade-10dB-cn0-66dBHz.flac) | 26.06 |
| demo | B200Y+SUB100 | phase-only-awgn-cn0-66dBHz | [再生](demo__32k__B200Y+SUB100__phase-only-awgn-cn0-66dBHz.flac) | 28.06 |
| demo | B200Y+SUB100 | rayleigh-cn0-60dBHz | [再生](demo__32k__B200Y+SUB100__rayleigh-cn0-60dBHz.flac) | 13.63 |
| demo | B200Y | codec | [再生](demo__32k__B200Y__codec.flac) | 62.94 |
| demo | B200Y | ideal | [再生](demo__32k__B200Y__ideal.flac) | 62.94 |
| fishin | B200MY+SUB50M | awgn-cn0-54dBHz | [再生](fishin__32k__B200MY+SUB50M__awgn-cn0-54dBHz.flac) | 13.26 |
| fishin | B200MY+SUB50M | awgn-cn0-57dBHz | [再生](fishin__32k__B200MY+SUB50M__awgn-cn0-57dBHz.flac) | 19.18 |
| fishin | B200MY+SUB50M | awgn-cn0-60dBHz | [再生](fishin__32k__B200MY+SUB50M__awgn-cn0-60dBHz.flac) | 21.91 |
| fishin | B200MY+SUB50M | awgn-cn0-66dBHz | [再生](fishin__32k__B200MY+SUB50M__awgn-cn0-66dBHz.flac) | 27.10 |
| fishin | B200MY+SUB50M | awgn-cn0-80dBHz | [再生](fishin__32k__B200MY+SUB50M__awgn-cn0-80dBHz.flac) | 40.73 |
| fishin | B200MY+SUB50M | main-fade-10dB-cn0-66dBHz | [再生](fishin__32k__B200MY+SUB50M__main-fade-10dB-cn0-66dBHz.flac) | 17.86 |
| fishin | B200MY+SUB50M | phase-only-awgn-cn0-66dBHz | [再生](fishin__32k__B200MY+SUB50M__phase-only-awgn-cn0-66dBHz.flac) | 15.80 |
| fishin | B200MY+SUB50M | rayleigh-cn0-60dBHz | [再生](fishin__32k__B200MY+SUB50M__rayleigh-cn0-60dBHz.flac) | 14.81 |
| fishin | B200MY | codec | [再生](fishin__32k__B200MY__codec.flac) | 52.63 |
| fishin | B200MY | ideal | [再生](fishin__32k__B200MY__ideal.flac) | 52.63 |
| vibeace | B200MY+SUB50M | awgn-cn0-54dBHz | [再生](vibeace__32k__B200MY+SUB50M__awgn-cn0-54dBHz.flac) | 18.28 |
| vibeace | B200MY+SUB50M | awgn-cn0-57dBHz | [再生](vibeace__32k__B200MY+SUB50M__awgn-cn0-57dBHz.flac) | 29.67 |
| vibeace | B200MY+SUB50M | awgn-cn0-60dBHz | [再生](vibeace__32k__B200MY+SUB50M__awgn-cn0-60dBHz.flac) | 33.55 |
| vibeace | B200MY+SUB50M | awgn-cn0-66dBHz | [再生](vibeace__32k__B200MY+SUB50M__awgn-cn0-66dBHz.flac) | 38.27 |
| vibeace | B200MY+SUB50M | awgn-cn0-80dBHz | [再生](vibeace__32k__B200MY+SUB50M__awgn-cn0-80dBHz.flac) | 52.68 |
| vibeace | B200MY+SUB50M | main-fade-10dB-cn0-66dBHz | [再生](vibeace__32k__B200MY+SUB50M__main-fade-10dB-cn0-66dBHz.flac) | 29.34 |
| vibeace | B200MY+SUB50M | phase-only-awgn-cn0-66dBHz | [再生](vibeace__32k__B200MY+SUB50M__phase-only-awgn-cn0-66dBHz.flac) | 29.06 |
| vibeace | B200MY+SUB50M | rayleigh-cn0-60dBHz | [再生](vibeace__32k__B200MY+SUB50M__rayleigh-cn0-60dBHz.flac) | 19.77 |
| vibeace | B200MY | codec | [再生](vibeace__32k__B200MY__codec.flac) | 62.88 |
| vibeace | B200MY | ideal | [再生](vibeace__32k__B200MY__ideal.flac) | 62.88 |

## 原音

- [demo](demo__32k__reference.flac)
- [fishin](fishin__32k__reference.flac)
- [vibeace](vibeace__32k__reference.flac)
