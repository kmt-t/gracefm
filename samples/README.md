# 現行サンプル音声 — 32 kHz 主系・副系

**全デジタル主系・副系に標準アッテネータを含む現行設定の音声です。** 各10秒。保存したFLACを読み戻して波形SNRを再測定しています。

[命名規則](NAMING.md) · [設定表](../docs/PROFILES.md) · [全音源の設定・測定値・SHA-256](../docs/results/samples.json)

32 kHzの2系統は電力50:50。48 kHzの `M700+SUB100-48K` は75:25。それ以外の48 kHz音声は主系1系統です。`codec` は通信路なし、`ideal` は雑音なしのシンボル送受信。AWGN等は同期既知のシミュレーションです。

`M700-base` は実際の基本層を保持し、拡張層の事後確率だけを0.5にした比較音源です。標準アッテネータを含みます。`R10` / `R12` はY仮数幅の比較条件です。

波形SNRは原音との差であり、聴感の点数ではありません。

| 音源 | 構成 | 条件 | 試聴 | 波形SNR dB |
|---|---|---|---|---:|
| demo | B200+SUB100 | awgn-cn0-54dBHz | [再生](demo__32k__B200+SUB100__awgn-cn0-54dBHz.flac) | 8.00 |
| demo | B200+SUB100 | awgn-cn0-57dBHz | [再生](demo__32k__B200+SUB100__awgn-cn0-57dBHz.flac) | 15.34 |
| demo | B200+SUB100 | awgn-cn0-60dBHz | [再生](demo__32k__B200+SUB100__awgn-cn0-60dBHz.flac) | 21.01 |
| demo | B200+SUB100 | awgn-cn0-66dBHz | [再生](demo__32k__B200+SUB100__awgn-cn0-66dBHz.flac) | 40.11 |
| demo | B200+SUB100 | awgn-cn0-80dBHz | [再生](demo__32k__B200+SUB100__awgn-cn0-80dBHz.flac) | 57.86 |
| demo | B200+SUB100 | main-fade-10dB-cn0-66dBHz | [再生](demo__32k__B200+SUB100__main-fade-10dB-cn0-66dBHz.flac) | 25.76 |
| demo | B200+SUB100 | rayleigh-cn0-60dBHz | [再生](demo__32k__B200+SUB100__rayleigh-cn0-60dBHz.flac) | 9.22 |
| demo | B200Y | codec | [再生](demo__32k__B200Y__codec.flac) | 62.94 |
| demo | B200 | codec | [再生](demo__32k__B200__codec.flac) | 62.17 |
| fishin | B200M+SUB50M | awgn-cn0-54dBHz | [再生](fishin__32k__B200M+SUB50M__awgn-cn0-54dBHz.flac) | 9.82 |
| fishin | B200M+SUB50M | awgn-cn0-57dBHz | [再生](fishin__32k__B200M+SUB50M__awgn-cn0-57dBHz.flac) | 12.45 |
| fishin | B200M+SUB50M | awgn-cn0-60dBHz | [再生](fishin__32k__B200M+SUB50M__awgn-cn0-60dBHz.flac) | 19.18 |
| fishin | B200M+SUB50M | awgn-cn0-66dBHz | [再生](fishin__32k__B200M+SUB50M__awgn-cn0-66dBHz.flac) | 32.36 |
| fishin | B200M+SUB50M | awgn-cn0-80dBHz | [再生](fishin__32k__B200M+SUB50M__awgn-cn0-80dBHz.flac) | 55.34 |
| fishin | B200M+SUB50M | main-fade-10dB-cn0-66dBHz | [再生](fishin__32k__B200M+SUB50M__main-fade-10dB-cn0-66dBHz.flac) | 14.00 |
| fishin | B200M+SUB50M | rayleigh-cn0-60dBHz | [再生](fishin__32k__B200M+SUB50M__rayleigh-cn0-60dBHz.flac) | 10.47 |
| fishin | B200M | codec | [再生](fishin__32k__B200M__codec.flac) | 57.32 |
| fishin | FM | awgn-cn0-54dBHz | [再生](fishin__32k__FM__awgn-cn0-54dBHz.flac) | 4.02 |
| fishin | FM | awgn-cn0-57dBHz | [再生](fishin__32k__FM__awgn-cn0-57dBHz.flac) | 11.42 |
| fishin | FM | awgn-cn0-60dBHz | [再生](fishin__32k__FM__awgn-cn0-60dBHz.flac) | 24.07 |
| fishin | FM | awgn-cn0-66dBHz | [再生](fishin__32k__FM__awgn-cn0-66dBHz.flac) | 38.16 |
| fishin | FM | awgn-cn0-80dBHz | [再生](fishin__32k__FM__awgn-cn0-80dBHz.flac) | 51.16 |
| fishin | FM | main-fade-10dB-cn0-66dBHz | [再生](fishin__32k__FM__main-fade-10dB-cn0-66dBHz.flac) | 8.44 |
| fishin | FM | rayleigh-cn0-60dBHz | [再生](fishin__32k__FM__rayleigh-cn0-60dBHz.flac) | 4.65 |
| vibeace | B200M+SUB50M | awgn-cn0-54dBHz | [再生](vibeace__32k__B200M+SUB50M__awgn-cn0-54dBHz.flac) | 12.98 |
| vibeace | B200M+SUB50M | awgn-cn0-57dBHz | [再生](vibeace__32k__B200M+SUB50M__awgn-cn0-57dBHz.flac) | 17.83 |
| vibeace | B200M+SUB50M | awgn-cn0-60dBHz | [再生](vibeace__32k__B200M+SUB50M__awgn-cn0-60dBHz.flac) | 27.65 |
| vibeace | B200M+SUB50M | awgn-cn0-66dBHz | [再生](vibeace__32k__B200M+SUB50M__awgn-cn0-66dBHz.flac) | 41.37 |
| vibeace | B200M+SUB50M | awgn-cn0-80dBHz | [再生](vibeace__32k__B200M+SUB50M__awgn-cn0-80dBHz.flac) | 63.05 |
| vibeace | B200M+SUB50M | main-fade-10dB-cn0-66dBHz | [再生](vibeace__32k__B200M+SUB50M__main-fade-10dB-cn0-66dBHz.flac) | 23.28 |
| vibeace | B200M+SUB50M | rayleigh-cn0-60dBHz | [再生](vibeace__32k__B200M+SUB50M__rayleigh-cn0-60dBHz.flac) | 13.67 |
| vibeace | B200M | codec | [再生](vibeace__32k__B200M__codec.flac) | 65.78 |
| vibeace | FM | awgn-cn0-54dBHz | [再生](vibeace__32k__FM__awgn-cn0-54dBHz.flac) | 2.81 |
| vibeace | FM | awgn-cn0-57dBHz | [再生](vibeace__32k__FM__awgn-cn0-57dBHz.flac) | 10.20 |
| vibeace | FM | awgn-cn0-60dBHz | [再生](vibeace__32k__FM__awgn-cn0-60dBHz.flac) | 22.85 |
| vibeace | FM | awgn-cn0-66dBHz | [再生](vibeace__32k__FM__awgn-cn0-66dBHz.flac) | 36.62 |
| vibeace | FM | awgn-cn0-80dBHz | [再生](vibeace__32k__FM__awgn-cn0-80dBHz.flac) | 50.66 |
| vibeace | FM | main-fade-10dB-cn0-66dBHz | [再生](vibeace__32k__FM__main-fade-10dB-cn0-66dBHz.flac) | 7.27 |
| vibeace | FM | rayleigh-cn0-60dBHz | [再生](vibeace__32k__FM__rayleigh-cn0-60dBHz.flac) | 3.53 |

## 原音

- [demo](demo__32k__reference.flac)
- [fishin](fishin__32k__reference.flac)
- [vibeace](vibeace__32k__reference.flac)

## その他の試聴

[48 kHzモニター](monitor/README.md) · [32 kHz Y系](hybrid_y/README.md) · [48 kHz Y系・高域試験](monitor_y/README.md)

## 楽曲の出典とライセンス

[librosa/data](https://github.com/librosa/data) 収録の音源を、抜粋・サンプリング周波数の変換・音量の正規化・本方式による符号化と復号で加工。元の楽曲は CC BY 3.0、加工したサンプルは [CC BY-NC 4.0](https://creativecommons.org/licenses/by-nc/4.0/)（元の楽曲の出典表示を含む）。

- **"Let's Go Fishin'" by Karissa Hobbs** — [Free Music Archive](https://freemusicarchive.org/music/Karissa_Hobbs/Age_of_Flowers/09_Lets_Go_Fishin)、[CC BY 3.0](https://creativecommons.org/licenses/by/3.0/)
- **"Vibe Ace" by Kevin MacLeod** — [Free Music Archive](https://freemusicarchive.org/music/Kevin_MacLeod/Jazz_Sampler/Vibe_Ace)、[CC BY 3.0](https://creativecommons.org/licenses/by/3.0/)
- `demo_*`：合成した試験信号（全帯域・ステレオ）
