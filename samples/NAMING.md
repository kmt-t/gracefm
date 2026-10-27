# サンプル音声の命名規則

加工音声は次の順序で命名する。区切りは二重アンダースコア `__`。

`音源-形__サンプリング周波数__構成__条件.flac`

原音は `音源-形__サンプリング周波数__reference.flac` とする。

| 項目 | 表記と意味 |
|---|---|
| 音源 | `demo`、`piano`、`percussion` |
| 形 | `mono`：(L+R)/2 のモノラル、`stereo`：原音のステレオ |
| サンプリング周波数 | `32k`。音声帯域を表す値ではない |
| 構成 | プロファイル名。副系つきは `主系+副系`（例：`B200M+SUB50M`）。アナログFMは `FM`（モノラル形だけ） |
| コーデックのみ | `codec`：通信路なし |
| 白色雑音 | `awgn-cn0-66dBHz`：C/N0が66 dB-Hz。C/NやEs/N0ではない |
| フェージング | `rayleigh-cn0-60dBHz`、`main-fade-10dB-cn0-66dBHz` |

例：

- `piano-mono__32k__reference.flac`：pianoのモノラル形の原音。
- `piano-mono__32k__B200M+SUB50M__awgn-cn0-57dBHz.flac`：モノラル主系＋副系、白色雑音条件。
- `demo-stereo__32k__B200Y__codec.flac`：ステレオ主系B200Yのコーデック単体音声。

生成ツールは `tools/samples/sample_names.py` の共通関数で命名する。全設定・保存後の波形SNR・SHA-256は [音源一覧JSON](../docs/results/samples.json) に記録する。
