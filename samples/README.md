# サンプル音声（GraceFM）

ファイル名の読み方は[命名規則](NAMING.md)。各10秒・32 kHz、劣化音は24bit FLAC。`tools/samples/make_samples.py` で生成し、`tools/samples/sample_catalog.py` で検証してこのファイルを書く。設定・測定値・SHA-256は[音源一覧JSON](index.json)。

## マトリクス

素材 3（demo・piano・percussion）× 形 2（モノラル・ステレオ）。モノラル形は (L+R)/2、ステレオ形は原音のまま。2系統は主系・副系とも独立のチャンネルで、電力を分け合わない（C/N0は同じ値）。

| 軸 | 内容 |
|---|---|
| 主系 | モノラル形: B200M・B200MY / ステレオ形: B200・B200Y |
| 副系 | なし / SUB50M |
| 条件 | コーデックだけ（副系なしのみ）、白色雑音 C/N0 54・57・60・66・80、レイリーフェージング（C/N0 60）、主系の周波数だけ10dB低下（C/N0 66） |
| アナログFM | モノラル形だけ、上の通信路条件 |

## 電波の強さ

| C/N0 | C/N（180kHz） |
|---|---|
| 80 dB-Hz | 27.4 dB |
| 66 dB-Hz | 13.4 dB |
| 60 dB-Hz | 7.4 dB |
| 57 dB-Hz | 4.4 dB |
| 54 dB-Hz | 1.4 dB |

66 dB-Hz は5m・室内の保守的な見積もり（SPEC 付録D）。通信路は白色雑音のみ、または系統ごとに独立なレイリーフェージング（時定数100ms、FMも同じ変動）、主系の周波数だけ10dB低下。同期・等化は理想で、FMのゴーストは含まない。

## モノラル形（波形SNR dB、保存したFLACと原音の差）

### demo

| 構成 | codec | awgn54 | awgn57 | awgn60 | awgn66 | awgn80 | rayleigh60 | main_minus10db66 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| B200M | [63.4](demo-mono__32k__B200M__codec.flac) | [0.8](demo-mono__32k__B200M__awgn-cn0-54dBHz.flac) | [11.4](demo-mono__32k__B200M__awgn-cn0-57dBHz.flac) | [25.7](demo-mono__32k__B200M__awgn-cn0-60dBHz.flac) | [33.7](demo-mono__32k__B200M__awgn-cn0-66dBHz.flac) | [63.4](demo-mono__32k__B200M__awgn-cn0-80dBHz.flac) | [4.9](demo-mono__32k__B200M__rayleigh-cn0-60dBHz.flac) | [6.0](demo-mono__32k__B200M__main-fade-10dB-cn0-66dBHz.flac) |
| B200M+SUB50M | — | [18.6](demo-mono__32k__B200M+SUB50M__awgn-cn0-54dBHz.flac) | [30.9](demo-mono__32k__B200M+SUB50M__awgn-cn0-57dBHz.flac) | [39.4](demo-mono__32k__B200M+SUB50M__awgn-cn0-60dBHz.flac) | [41.2](demo-mono__32k__B200M+SUB50M__awgn-cn0-66dBHz.flac) | [63.4](demo-mono__32k__B200M+SUB50M__awgn-cn0-80dBHz.flac) | [15.3](demo-mono__32k__B200M+SUB50M__rayleigh-cn0-60dBHz.flac) | [31.1](demo-mono__32k__B200M+SUB50M__main-fade-10dB-cn0-66dBHz.flac) |
| B200MY | [63.4](demo-mono__32k__B200MY__codec.flac) | [3.7](demo-mono__32k__B200MY__awgn-cn0-54dBHz.flac) | [18.0](demo-mono__32k__B200MY__awgn-cn0-57dBHz.flac) | [28.4](demo-mono__32k__B200MY__awgn-cn0-60dBHz.flac) | [34.1](demo-mono__32k__B200MY__awgn-cn0-66dBHz.flac) | [54.2](demo-mono__32k__B200MY__awgn-cn0-80dBHz.flac) | [6.2](demo-mono__32k__B200MY__rayleigh-cn0-60dBHz.flac) | [13.0](demo-mono__32k__B200MY__main-fade-10dB-cn0-66dBHz.flac) |
| B200MY+SUB50M | — | [19.4](demo-mono__32k__B200MY+SUB50M__awgn-cn0-54dBHz.flac) | [31.7](demo-mono__32k__B200MY+SUB50M__awgn-cn0-57dBHz.flac) | [35.9](demo-mono__32k__B200MY+SUB50M__awgn-cn0-60dBHz.flac) | [39.4](demo-mono__32k__B200MY+SUB50M__awgn-cn0-66dBHz.flac) | [54.3](demo-mono__32k__B200MY+SUB50M__awgn-cn0-80dBHz.flac) | [16.1](demo-mono__32k__B200MY+SUB50M__rayleigh-cn0-60dBHz.flac) | [32.6](demo-mono__32k__B200MY+SUB50M__main-fade-10dB-cn0-66dBHz.flac) |
| FM | — | [2.1](demo-mono__32k__FM__awgn-cn0-54dBHz.flac) | [9.4](demo-mono__32k__FM__awgn-cn0-57dBHz.flac) | [22.3](demo-mono__32k__FM__awgn-cn0-60dBHz.flac) | [34.2](demo-mono__32k__FM__awgn-cn0-66dBHz.flac) | [38.9](demo-mono__32k__FM__awgn-cn0-80dBHz.flac) | [2.7](demo-mono__32k__FM__rayleigh-cn0-60dBHz.flac) | [6.5](demo-mono__32k__FM__main-fade-10dB-cn0-66dBHz.flac) |

### piano

| 構成 | codec | awgn54 | awgn57 | awgn60 | awgn66 | awgn80 | rayleigh60 | main_minus10db66 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| B200M | [53.5](piano-mono__32k__B200M__codec.flac) | [0.6](piano-mono__32k__B200M__awgn-cn0-54dBHz.flac) | [9.6](piano-mono__32k__B200M__awgn-cn0-57dBHz.flac) | [22.1](piano-mono__32k__B200M__awgn-cn0-60dBHz.flac) | [29.3](piano-mono__32k__B200M__awgn-cn0-66dBHz.flac) | [53.5](piano-mono__32k__B200M__awgn-cn0-80dBHz.flac) | [5.3](piano-mono__32k__B200M__rayleigh-cn0-60dBHz.flac) | [5.2](piano-mono__32k__B200M__main-fade-10dB-cn0-66dBHz.flac) |
| B200M+SUB50M | — | [14.1](piano-mono__32k__B200M+SUB50M__awgn-cn0-54dBHz.flac) | [22.7](piano-mono__32k__B200M+SUB50M__awgn-cn0-57dBHz.flac) | [30.7](piano-mono__32k__B200M+SUB50M__awgn-cn0-60dBHz.flac) | [32.9](piano-mono__32k__B200M+SUB50M__awgn-cn0-66dBHz.flac) | [53.5](piano-mono__32k__B200M+SUB50M__awgn-cn0-80dBHz.flac) | [15.2](piano-mono__32k__B200M+SUB50M__rayleigh-cn0-60dBHz.flac) | [20.3](piano-mono__32k__B200M+SUB50M__main-fade-10dB-cn0-66dBHz.flac) |
| B200MY | [54.1](piano-mono__32k__B200MY__codec.flac) | [2.9](piano-mono__32k__B200MY__awgn-cn0-54dBHz.flac) | [15.1](piano-mono__32k__B200MY__awgn-cn0-57dBHz.flac) | [22.6](piano-mono__32k__B200MY__awgn-cn0-60dBHz.flac) | [27.7](piano-mono__32k__B200MY__awgn-cn0-66dBHz.flac) | [42.5](piano-mono__32k__B200MY__awgn-cn0-80dBHz.flac) | [6.3](piano-mono__32k__B200MY__rayleigh-cn0-60dBHz.flac) | [11.3](piano-mono__32k__B200MY__main-fade-10dB-cn0-66dBHz.flac) |
| B200MY+SUB50M | — | [15.0](piano-mono__32k__B200MY+SUB50M__awgn-cn0-54dBHz.flac) | [24.1](piano-mono__32k__B200MY+SUB50M__awgn-cn0-57dBHz.flac) | [27.1](piano-mono__32k__B200MY+SUB50M__awgn-cn0-60dBHz.flac) | [30.5](piano-mono__32k__B200MY+SUB50M__awgn-cn0-66dBHz.flac) | [42.6](piano-mono__32k__B200MY+SUB50M__awgn-cn0-80dBHz.flac) | [15.9](piano-mono__32k__B200MY+SUB50M__rayleigh-cn0-60dBHz.flac) | [23.3](piano-mono__32k__B200MY+SUB50M__main-fade-10dB-cn0-66dBHz.flac) |
| FM | — | [6.5](piano-mono__32k__FM__awgn-cn0-54dBHz.flac) | [14.1](piano-mono__32k__FM__awgn-cn0-57dBHz.flac) | [26.8](piano-mono__32k__FM__awgn-cn0-60dBHz.flac) | [41.6](piano-mono__32k__FM__awgn-cn0-66dBHz.flac) | [54.2](piano-mono__32k__FM__awgn-cn0-80dBHz.flac) | [6.9](piano-mono__32k__FM__rayleigh-cn0-60dBHz.flac) | [11.2](piano-mono__32k__FM__main-fade-10dB-cn0-66dBHz.flac) |

### percussion

| 構成 | codec | awgn54 | awgn57 | awgn60 | awgn66 | awgn80 | rayleigh60 | main_minus10db66 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| B200M | [57.4](percussion-mono__32k__B200M__codec.flac) | [0.7](percussion-mono__32k__B200M__awgn-cn0-54dBHz.flac) | [11.3](percussion-mono__32k__B200M__awgn-cn0-57dBHz.flac) | [23.4](percussion-mono__32k__B200M__awgn-cn0-60dBHz.flac) | [31.2](percussion-mono__32k__B200M__awgn-cn0-66dBHz.flac) | [57.4](percussion-mono__32k__B200M__awgn-cn0-80dBHz.flac) | [5.3](percussion-mono__32k__B200M__rayleigh-cn0-60dBHz.flac) | [5.7](percussion-mono__32k__B200M__main-fade-10dB-cn0-66dBHz.flac) |
| B200M+SUB50M | — | [16.6](percussion-mono__32k__B200M+SUB50M__awgn-cn0-54dBHz.flac) | [27.8](percussion-mono__32k__B200M+SUB50M__awgn-cn0-57dBHz.flac) | [34.3](percussion-mono__32k__B200M+SUB50M__awgn-cn0-60dBHz.flac) | [36.4](percussion-mono__32k__B200M+SUB50M__awgn-cn0-66dBHz.flac) | [57.4](percussion-mono__32k__B200M+SUB50M__awgn-cn0-80dBHz.flac) | [13.8](percussion-mono__32k__B200M+SUB50M__rayleigh-cn0-60dBHz.flac) | [24.7](percussion-mono__32k__B200M+SUB50M__main-fade-10dB-cn0-66dBHz.flac) |
| B200MY | [58.0](percussion-mono__32k__B200MY__codec.flac) | [3.1](percussion-mono__32k__B200MY__awgn-cn0-54dBHz.flac) | [17.6](percussion-mono__32k__B200MY__awgn-cn0-57dBHz.flac) | [23.9](percussion-mono__32k__B200MY__awgn-cn0-60dBHz.flac) | [30.7](percussion-mono__32k__B200MY__awgn-cn0-66dBHz.flac) | [47.1](percussion-mono__32k__B200MY__awgn-cn0-80dBHz.flac) | [6.5](percussion-mono__32k__B200MY__rayleigh-cn0-60dBHz.flac) | [11.8](percussion-mono__32k__B200MY__main-fade-10dB-cn0-66dBHz.flac) |
| B200MY+SUB50M | — | [16.6](percussion-mono__32k__B200MY+SUB50M__awgn-cn0-54dBHz.flac) | [27.7](percussion-mono__32k__B200MY+SUB50M__awgn-cn0-57dBHz.flac) | [31.2](percussion-mono__32k__B200MY+SUB50M__awgn-cn0-60dBHz.flac) | [34.6](percussion-mono__32k__B200MY+SUB50M__awgn-cn0-66dBHz.flac) | [47.3](percussion-mono__32k__B200MY+SUB50M__awgn-cn0-80dBHz.flac) | [14.9](percussion-mono__32k__B200MY+SUB50M__rayleigh-cn0-60dBHz.flac) | [27.2](percussion-mono__32k__B200MY+SUB50M__main-fade-10dB-cn0-66dBHz.flac) |
| FM | — | [1.2](percussion-mono__32k__FM__awgn-cn0-54dBHz.flac) | [8.5](percussion-mono__32k__FM__awgn-cn0-57dBHz.flac) | [21.2](percussion-mono__32k__FM__awgn-cn0-60dBHz.flac) | [34.5](percussion-mono__32k__FM__awgn-cn0-66dBHz.flac) | [44.4](percussion-mono__32k__FM__awgn-cn0-80dBHz.flac) | [2.0](percussion-mono__32k__FM__rayleigh-cn0-60dBHz.flac) | [5.6](percussion-mono__32k__FM__main-fade-10dB-cn0-66dBHz.flac) |

## ステレオ形（波形SNR dB、保存したFLACと原音の差）

### demo

| 構成 | codec | awgn54 | awgn57 | awgn60 | awgn66 | awgn80 | rayleigh60 | main_minus10db66 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| B200 | [62.1](demo-stereo__32k__B200__codec.flac) | [-0.0](demo-stereo__32k__B200__awgn-cn0-54dBHz.flac) | [0.8](demo-stereo__32k__B200__awgn-cn0-57dBHz.flac) | [14.1](demo-stereo__32k__B200__awgn-cn0-60dBHz.flac) | [31.6](demo-stereo__32k__B200__awgn-cn0-66dBHz.flac) | [61.6](demo-stereo__32k__B200__awgn-cn0-80dBHz.flac) | [2.9](demo-stereo__32k__B200__rayleigh-cn0-60dBHz.flac) | [0.1](demo-stereo__32k__B200__main-fade-10dB-cn0-66dBHz.flac) |
| B200+SUB50M | — | [17.4](demo-stereo__32k__B200+SUB50M__awgn-cn0-54dBHz.flac) | [23.2](demo-stereo__32k__B200+SUB50M__awgn-cn0-57dBHz.flac) | [33.0](demo-stereo__32k__B200+SUB50M__awgn-cn0-60dBHz.flac) | [39.4](demo-stereo__32k__B200+SUB50M__awgn-cn0-66dBHz.flac) | [61.7](demo-stereo__32k__B200+SUB50M__awgn-cn0-80dBHz.flac) | [14.1](demo-stereo__32k__B200+SUB50M__rayleigh-cn0-60dBHz.flac) | [25.5](demo-stereo__32k__B200+SUB50M__main-fade-10dB-cn0-66dBHz.flac) |
| B200Y | [62.0](demo-stereo__32k__B200Y__codec.flac) | [0.0](demo-stereo__32k__B200Y__awgn-cn0-54dBHz.flac) | [5.0](demo-stereo__32k__B200Y__awgn-cn0-57dBHz.flac) | [21.5](demo-stereo__32k__B200Y__awgn-cn0-60dBHz.flac) | [31.9](demo-stereo__32k__B200Y__awgn-cn0-66dBHz.flac) | [50.0](demo-stereo__32k__B200Y__awgn-cn0-80dBHz.flac) | [4.0](demo-stereo__32k__B200Y__rayleigh-cn0-60dBHz.flac) | [1.6](demo-stereo__32k__B200Y__main-fade-10dB-cn0-66dBHz.flac) |
| B200Y+SUB50M | — | [17.3](demo-stereo__32k__B200Y+SUB50M__awgn-cn0-54dBHz.flac) | [26.1](demo-stereo__32k__B200Y+SUB50M__awgn-cn0-57dBHz.flac) | [32.1](demo-stereo__32k__B200Y+SUB50M__awgn-cn0-60dBHz.flac) | [36.2](demo-stereo__32k__B200Y+SUB50M__awgn-cn0-66dBHz.flac) | [50.1](demo-stereo__32k__B200Y+SUB50M__awgn-cn0-80dBHz.flac) | [14.4](demo-stereo__32k__B200Y+SUB50M__rayleigh-cn0-60dBHz.flac) | [26.0](demo-stereo__32k__B200Y+SUB50M__main-fade-10dB-cn0-66dBHz.flac) |

### piano

| 構成 | codec | awgn54 | awgn57 | awgn60 | awgn66 | awgn80 | rayleigh60 | main_minus10db66 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| B200 | [51.3](piano-stereo__32k__B200__codec.flac) | [0.0](piano-stereo__32k__B200__awgn-cn0-54dBHz.flac) | [0.6](piano-stereo__32k__B200__awgn-cn0-57dBHz.flac) | [11.6](piano-stereo__32k__B200__awgn-cn0-60dBHz.flac) | [26.6](piano-stereo__32k__B200__awgn-cn0-66dBHz.flac) | [51.1](piano-stereo__32k__B200__awgn-cn0-80dBHz.flac) | [2.9](piano-stereo__32k__B200__rayleigh-cn0-60dBHz.flac) | [0.1](piano-stereo__32k__B200__main-fade-10dB-cn0-66dBHz.flac) |
| B200+SUB50M | — | [5.9](piano-stereo__32k__B200+SUB50M__awgn-cn0-54dBHz.flac) | [6.8](piano-stereo__32k__B200+SUB50M__awgn-cn0-57dBHz.flac) | [16.9](piano-stereo__32k__B200+SUB50M__awgn-cn0-60dBHz.flac) | [28.7](piano-stereo__32k__B200+SUB50M__awgn-cn0-66dBHz.flac) | [51.1](piano-stereo__32k__B200+SUB50M__awgn-cn0-80dBHz.flac) | [8.1](piano-stereo__32k__B200+SUB50M__rayleigh-cn0-60dBHz.flac) | [6.3](piano-stereo__32k__B200+SUB50M__main-fade-10dB-cn0-66dBHz.flac) |
| B200Y | [53.8](piano-stereo__32k__B200Y__codec.flac) | [0.0](piano-stereo__32k__B200Y__awgn-cn0-54dBHz.flac) | [3.7](piano-stereo__32k__B200Y__awgn-cn0-57dBHz.flac) | [18.2](piano-stereo__32k__B200Y__awgn-cn0-60dBHz.flac) | [25.5](piano-stereo__32k__B200Y__awgn-cn0-66dBHz.flac) | [40.1](piano-stereo__32k__B200Y__awgn-cn0-80dBHz.flac) | [4.0](piano-stereo__32k__B200Y__rayleigh-cn0-60dBHz.flac) | [1.1](piano-stereo__32k__B200Y__main-fade-10dB-cn0-66dBHz.flac) |
| B200Y+SUB50M | — | [5.9](piano-stereo__32k__B200Y+SUB50M__awgn-cn0-54dBHz.flac) | [9.7](piano-stereo__32k__B200Y+SUB50M__awgn-cn0-57dBHz.flac) | [22.2](piano-stereo__32k__B200Y+SUB50M__awgn-cn0-60dBHz.flac) | [27.8](piano-stereo__32k__B200Y+SUB50M__awgn-cn0-66dBHz.flac) | [40.2](piano-stereo__32k__B200Y+SUB50M__awgn-cn0-80dBHz.flac) | [9.0](piano-stereo__32k__B200Y+SUB50M__rayleigh-cn0-60dBHz.flac) | [7.3](piano-stereo__32k__B200Y+SUB50M__main-fade-10dB-cn0-66dBHz.flac) |

### percussion

| 構成 | codec | awgn54 | awgn57 | awgn60 | awgn66 | awgn80 | rayleigh60 | main_minus10db66 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| B200 | [56.6](percussion-stereo__32k__B200__codec.flac) | [0.0](percussion-stereo__32k__B200__awgn-cn0-54dBHz.flac) | [0.6](percussion-stereo__32k__B200__awgn-cn0-57dBHz.flac) | [12.6](percussion-stereo__32k__B200__awgn-cn0-60dBHz.flac) | [29.2](percussion-stereo__32k__B200__awgn-cn0-66dBHz.flac) | [56.5](percussion-stereo__32k__B200__awgn-cn0-80dBHz.flac) | [3.3](percussion-stereo__32k__B200__rayleigh-cn0-60dBHz.flac) | [0.1](percussion-stereo__32k__B200__main-fade-10dB-cn0-66dBHz.flac) |
| B200+SUB50M | — | [12.9](percussion-stereo__32k__B200+SUB50M__awgn-cn0-54dBHz.flac) | [15.7](percussion-stereo__32k__B200+SUB50M__awgn-cn0-57dBHz.flac) | [25.6](percussion-stereo__32k__B200+SUB50M__awgn-cn0-60dBHz.flac) | [34.4](percussion-stereo__32k__B200+SUB50M__awgn-cn0-66dBHz.flac) | [56.5](percussion-stereo__32k__B200+SUB50M__awgn-cn0-80dBHz.flac) | [11.5](percussion-stereo__32k__B200+SUB50M__rayleigh-cn0-60dBHz.flac) | [15.6](percussion-stereo__32k__B200+SUB50M__main-fade-10dB-cn0-66dBHz.flac) |
| B200Y | [57.7](percussion-stereo__32k__B200Y__codec.flac) | [0.0](percussion-stereo__32k__B200Y__awgn-cn0-54dBHz.flac) | [4.1](percussion-stereo__32k__B200Y__awgn-cn0-57dBHz.flac) | [20.4](percussion-stereo__32k__B200Y__awgn-cn0-60dBHz.flac) | [28.5](percussion-stereo__32k__B200Y__awgn-cn0-66dBHz.flac) | [44.6](percussion-stereo__32k__B200Y__awgn-cn0-80dBHz.flac) | [4.3](percussion-stereo__32k__B200Y__rayleigh-cn0-60dBHz.flac) | [1.2](percussion-stereo__32k__B200Y__main-fade-10dB-cn0-66dBHz.flac) |
| B200Y+SUB50M | — | [12.7](percussion-stereo__32k__B200Y+SUB50M__awgn-cn0-54dBHz.flac) | [17.6](percussion-stereo__32k__B200Y+SUB50M__awgn-cn0-57dBHz.flac) | [28.4](percussion-stereo__32k__B200Y+SUB50M__awgn-cn0-60dBHz.flac) | [32.6](percussion-stereo__32k__B200Y+SUB50M__awgn-cn0-66dBHz.flac) | [44.9](percussion-stereo__32k__B200Y+SUB50M__awgn-cn0-80dBHz.flac) | [12.1](percussion-stereo__32k__B200Y+SUB50M__rayleigh-cn0-60dBHz.flac) | [16.3](percussion-stereo__32k__B200Y+SUB50M__main-fade-10dB-cn0-66dBHz.flac) |

## 原音と出典

- [demo-mono](demo-mono__32k__reference.flac)
- [demo-stereo](demo-stereo__32k__reference.flac)
- [piano-mono](piano-mono__32k__reference.flac)
- [piano-stereo](piano-stereo__32k__reference.flac)
- [percussion-mono](percussion-mono__32k__reference.flac)
- [percussion-stereo](percussion-stereo__32k__reference.flac)

- `demo`：合成した試験信号（全帯域・ステレオ）
- "Emotional piano" by triangelx — [Wikimedia Commons](https://commons.wikimedia.org/wiki/File:Emotional_piano.wav)、CC0 1.0
- "Ceramic Djembe" by RutgerMuller — [Wikimedia Commons](https://commons.wikimedia.org/wiki/File:Ceramic_Djembe.wav)、CC0 1.0

加工したサンプルは [CC BY-NC 4.0](https://creativecommons.org/licenses/by-nc/4.0/)。
