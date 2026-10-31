# サンプル音声（GraceFM）

ファイル名の読み方は[命名規則](NAMING.md)。各10秒・32 kHz、劣化音は24bit FLAC。`tools/samples/make_samples.py` で生成し、`tools/samples/sample_catalog.py` で検証してこのファイルを書く。設定・測定値・SHA-256は[音源一覧JSON](index.json)。

## マトリクス

素材 3（demo・piano・percussion）のモノラル形（(L+R)/2）。2系統は主系・副系とも独立のチャンネルで、電力を分け合わない（C/N0は同じ値）。

| 軸 | 内容 |
|---|---|
| 主系 | B200M（32 kHz） |
| 副系 | SUB50M |
| 条件 | 白色雑音 C/N0 54・57・60・66・80 |
| アナログFM | 32 kHzのモノラル形だけ、上の通信路条件 |

## 電波の強さ

| C/N0 | C/N（180kHz） |
|---|---|
| 80 dB-Hz | 27.4 dB |
| 66 dB-Hz | 13.4 dB |
| 60 dB-Hz | 7.4 dB |
| 57 dB-Hz | 4.4 dB |
| 54 dB-Hz | 1.4 dB |

66 dB-Hz は5m・室内の保守的な見積もり（SPEC 付録D）。通信路は白色雑音のみ。同期・等化は理想で、FMのゴーストは含まない。

## モノラル形・32 kHz（波形SNR dB、保存したFLACと原音の差）

### demo

| 構成 | awgn54 | awgn57 | awgn60 | awgn66 | awgn80 |
|---|---:|---:|---:|---:|---:|
| B200M+SUB50M | [18.6](demo-mono__32k__B200M+SUB50M__awgn-cn0-54dBHz.flac) | [30.2](demo-mono__32k__B200M+SUB50M__awgn-cn0-57dBHz.flac) | [39.3](demo-mono__32k__B200M+SUB50M__awgn-cn0-60dBHz.flac) | [40.8](demo-mono__32k__B200M+SUB50M__awgn-cn0-66dBHz.flac) | [59.5](demo-mono__32k__B200M+SUB50M__awgn-cn0-80dBHz.flac) |
| FM | [2.1](demo-mono__32k__FM__awgn-cn0-54dBHz.flac) | [9.4](demo-mono__32k__FM__awgn-cn0-57dBHz.flac) | [22.3](demo-mono__32k__FM__awgn-cn0-60dBHz.flac) | [34.2](demo-mono__32k__FM__awgn-cn0-66dBHz.flac) | [38.9](demo-mono__32k__FM__awgn-cn0-80dBHz.flac) |

### piano

| 構成 | awgn54 | awgn57 | awgn60 | awgn66 | awgn80 |
|---|---:|---:|---:|---:|---:|
| B200M+SUB50M | [15.4](piano-mono__32k__B200M+SUB50M__awgn-cn0-54dBHz.flac) | [23.5](piano-mono__32k__B200M+SUB50M__awgn-cn0-57dBHz.flac) | [30.2](piano-mono__32k__B200M+SUB50M__awgn-cn0-60dBHz.flac) | [32.7](piano-mono__32k__B200M+SUB50M__awgn-cn0-66dBHz.flac) | [52.6](piano-mono__32k__B200M+SUB50M__awgn-cn0-80dBHz.flac) |
| FM | [6.5](piano-mono__32k__FM__awgn-cn0-54dBHz.flac) | [14.1](piano-mono__32k__FM__awgn-cn0-57dBHz.flac) | [26.8](piano-mono__32k__FM__awgn-cn0-60dBHz.flac) | [41.6](piano-mono__32k__FM__awgn-cn0-66dBHz.flac) | [54.2](piano-mono__32k__FM__awgn-cn0-80dBHz.flac) |

### percussion

| 構成 | awgn54 | awgn57 | awgn60 | awgn66 | awgn80 |
|---|---:|---:|---:|---:|---:|
| B200M+SUB50M | [16.3](percussion-mono__32k__B200M+SUB50M__awgn-cn0-54dBHz.flac) | [26.1](percussion-mono__32k__B200M+SUB50M__awgn-cn0-57dBHz.flac) | [34.0](percussion-mono__32k__B200M+SUB50M__awgn-cn0-60dBHz.flac) | [36.0](percussion-mono__32k__B200M+SUB50M__awgn-cn0-66dBHz.flac) | [55.6](percussion-mono__32k__B200M+SUB50M__awgn-cn0-80dBHz.flac) |
| FM | [1.2](percussion-mono__32k__FM__awgn-cn0-54dBHz.flac) | [8.5](percussion-mono__32k__FM__awgn-cn0-57dBHz.flac) | [21.2](percussion-mono__32k__FM__awgn-cn0-60dBHz.flac) | [34.5](percussion-mono__32k__FM__awgn-cn0-66dBHz.flac) | [44.4](percussion-mono__32k__FM__awgn-cn0-80dBHz.flac) |

## 原音と出典

- [demo-mono (32 kHz)](demo-mono__32k__reference.flac)
- [piano-mono (32 kHz)](piano-mono__32k__reference.flac)
- [percussion-mono (32 kHz)](percussion-mono__32k__reference.flac)

- `demo`：合成した試験信号（全帯域・ステレオ）
- "Emotional piano" by triangelx — [Wikimedia Commons](https://commons.wikimedia.org/wiki/File:Emotional_piano.wav)、CC0 1.0
- "Ceramic Djembe" by RutgerMuller — [Wikimedia Commons](https://commons.wikimedia.org/wiki/File:Ceramic_Djembe.wav)、CC0 1.0

加工したサンプルは [CC BY-NC 4.0](https://creativecommons.org/licenses/by-nc/4.0/)。
