# 現行サンプル音声 — 48 kHz モニター

**全デジタル主系・副系に標準アッテネータを含む現行設定の音声です。** 各10秒。保存したFLACを読み戻して波形SNRを再測定しています。

[命名規則](../NAMING.md) · [設定表](../../docs/PROFILES.md) · [全音源の設定・測定値・SHA-256](../../docs/results/samples.json)

2系統は主系・副系とも独立のチャンネルで、電力を分け合わない（C/N0は同じ値）。それ以外の48 kHz音声は主系1系統です。`codec` は通信路なし、`ideal` は雑音なしのシンボル送受信。AWGN等は同期既知のシミュレーションです。

`M700-base` は実際の基本層を保持し、拡張層の事後確率だけを0.5にした比較音源です。標準アッテネータを含みます。`R10` / `R12` はY仮数幅の比較条件です。

波形SNRは原音との差であり、聴感の点数ではありません。

| 音源 | 構成 | 条件 | 試聴 | 波形SNR dB |
|---|---|---|---|---:|
| demo | M700+SUB100-48K | awgn-cn0-65dBHz | [再生](demo__48k__M700+SUB100-48K__awgn-cn0-65dBHz.flac) | 28.83 |
| demo | M700+SUB100-48K | awgn-cn0-70dBHz | [再生](demo__48k__M700+SUB100-48K__awgn-cn0-70dBHz.flac) | 31.17 |
| demo | M700+SUB100-48K | awgn-cn0-75dBHz | [再生](demo__48k__M700+SUB100-48K__awgn-cn0-75dBHz.flac) | 36.34 |
| demo | M700+SUB100-48K | awgn-cn0-80dBHz | [再生](demo__48k__M700+SUB100-48K__awgn-cn0-80dBHz.flac) | 40.30 |
| demo | M700-base | codec | [再生](demo__48k__M700-base__codec.flac) | 26.10 |
| demo | M700M | awgn-cn0-65dBHz | [再生](demo__48k__M700M__awgn-cn0-65dBHz.flac) | 23.38 |
| demo | M700M | awgn-cn0-70dBHz | [再生](demo__48k__M700M__awgn-cn0-70dBHz.flac) | 24.01 |
| demo | M700M | codec | [再生](demo__48k__M700M__codec.flac) | 24.27 |
| demo | M700 | awgn-cn0-65dBHz | [再生](demo__48k__M700__awgn-cn0-65dBHz.flac) | 25.25 |
| demo | M700 | awgn-cn0-70dBHz | [再生](demo__48k__M700__awgn-cn0-70dBHz.flac) | 29.77 |
| demo | M700 | awgn-cn0-75dBHz | [再生](demo__48k__M700__awgn-cn0-75dBHz.flac) | 35.38 |
| demo | M700 | awgn-cn0-80dBHz | [再生](demo__48k__M700__awgn-cn0-80dBHz.flac) | 40.25 |
| demo | M700 | codec | [再生](demo__48k__M700__codec.flac) | 40.40 |
| fishin | M700-base | codec | [再生](fishin__48k__M700-base__codec.flac) | 24.61 |
| fishin | M700M | awgn-cn0-65dBHz | [再生](fishin__48k__M700M__awgn-cn0-65dBHz.flac) | 28.52 |
| fishin | M700M | awgn-cn0-70dBHz | [再生](fishin__48k__M700M__awgn-cn0-70dBHz.flac) | 32.20 |
| fishin | M700M | codec | [再生](fishin__48k__M700M__codec.flac) | 53.01 |
| fishin | M700 | awgn-cn0-65dBHz | [再生](fishin__48k__M700__awgn-cn0-65dBHz.flac) | 25.35 |
| fishin | M700 | awgn-cn0-70dBHz | [再生](fishin__48k__M700__awgn-cn0-70dBHz.flac) | 28.50 |
| fishin | M700 | awgn-cn0-75dBHz | [再生](fishin__48k__M700__awgn-cn0-75dBHz.flac) | 35.40 |
| fishin | M700 | awgn-cn0-80dBHz | [再生](fishin__48k__M700__awgn-cn0-80dBHz.flac) | 48.11 |
| fishin | M700 | codec | [再生](fishin__48k__M700__codec.flac) | 49.79 |
| vibeace | M700-base | codec | [再生](vibeace__48k__M700-base__codec.flac) | 30.23 |
| vibeace | M700M | awgn-cn0-65dBHz | [再生](vibeace__48k__M700M__awgn-cn0-65dBHz.flac) | 32.33 |
| vibeace | M700M | awgn-cn0-70dBHz | [再生](vibeace__48k__M700M__awgn-cn0-70dBHz.flac) | 36.41 |
| vibeace | M700M | codec | [再生](vibeace__48k__M700M__codec.flac) | 63.50 |
| vibeace | M700 | awgn-cn0-65dBHz | [再生](vibeace__48k__M700__awgn-cn0-65dBHz.flac) | 28.71 |
| vibeace | M700 | awgn-cn0-70dBHz | [再生](vibeace__48k__M700__awgn-cn0-70dBHz.flac) | 34.36 |
| vibeace | M700 | awgn-cn0-75dBHz | [再生](vibeace__48k__M700__awgn-cn0-75dBHz.flac) | 40.97 |
| vibeace | M700 | awgn-cn0-80dBHz | [再生](vibeace__48k__M700__awgn-cn0-80dBHz.flac) | 55.85 |
| vibeace | M700 | codec | [再生](vibeace__48k__M700__codec.flac) | 60.34 |

## 原音

- [demo](demo__48k__reference.flac)
- [fishin](fishin__48k__reference.flac)
- [vibeace](vibeace__48k__reference.flac)
