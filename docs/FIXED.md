# 固定小数点実装（DSP 依存）

ハードウェアに載せるための、整数だけで動く参照実装の仕様である。**この文書の幅と演算は、想定する DSP（Zynq-7010 の DSP48E1）に依存する**。ハードウェアが変わるときは、DSP に依存する演算を集めた [`gracefm/dsp.py`](../gracefm/dsp.py) の幅と関数だけを差し替える。

## 1. 想定ハードウェアと制約

| 項目 | 値 | 出典 |
|---|---|---|
| DSP スライス | DSP48E1。Zynq-7010 に 80 スライス | [UG953](https://docs.amd.com/r/2021.1-English/ug953-vivado-7series-libraries/DSP48E1)、[UG479](https://gitea.federationhq.de/csander/Dissertation/raw/branch/main/bibliography/documents/ug479_7Series_DSP48E1.pdf) の写し |
| 乗算器 | 25 bit × 18 bit の符号つき（A ポート下位 25 bit、B ポート 18 bit） | 同上 |
| プリアダー | 25 bit | 同上 |
| アキュムレータ | 48 bit | 同上 |
| ADC/DAC | I・Q とも 12 bit（AD9363） | [AD9363 データシート](https://www.analog.com:443/media/en/technical-documentation/data-sheets/AD9363.pdf) |

`gracefm/dsp.py` はこの値を `MULT_BITS = 25`、`CONST_BITS = 18`、`ACC_BITS = 48` として持ち、演算（`mac_sq2_inv`、`round_shift`、`shift_signed`、`saturate`、`bit_length`）はこの幅を前提にする。

## 2. 数値形式

| 量 | 形式 |
|---|---|
| PCM | 符号つき 24 bit 整数（±1 = 2^23） |
| Haar の係数 | 小数 21 bit の整数（±1 = 2^21）。M = (L+R)/2、S = (L−R)/2 を、PCM から最後の 3 bit を四捨五入して作る |
| 1/√2 | 46341 / 65536（17 bit の正の整数。18 bit 符号つきの乗数に収まる） |
| 共有指数 | s = e + 21（係数の整数単位での 2 のべき乗の刻み） |

- **精度を落として幅に収める**: 係数の小数 bit 数を 21 に決め、Haar 4 段の最低域で最大 ±2^23 に収まるようにした。乗算器の入力（符号つき 25 bit、±2^24 まで）に余裕があり、飽和は起きない設計である。`saturate` は保険として置いている。
- **Haar の演算**: (e ± o)/√2 を、e·C ± o·C をアキュムレータで足し合わせ、四捨五入して 16 bit 右シフトする形で書く。積は 25 + 17 = 42 bit、和は 43 bit で、アキュムレータ（48 bit）に収まる。
- **刻みの下限**: アッテネータの半刻みを整数にするため、共有指数の刻みは s ≥ 1 に制限する。細かい刻み（e < −20）は使わない。デコーダは s ≤ 0 の値が来ても、右シフトで復号する。
- **定数の誤差**: 46341/65536 の相対誤差は約 10⁻⁶ で、Haar の往復（分解と合成）で、満点 2^21（乱数入力 500 ブロック）に対し最大 17 LSB（約 −102 dB）になる。

## 3. 実装と検査

| 項目 | ファイル |
|---|---|
| DSP 依存の演算 | [`gracefm/dsp.py`](../gracefm/dsp.py) |
| 固定小数点コーデック | [`gracefm/fixed.py`](../gracefm/fixed.py)（`encode_block_int`、`decode_block_int`、`roundtrip_int`） |
| 検査 | [`tests/test_fixed.py`](../tests/test_fixed.py)（乗数の幅、Haar が 25 bit に収まること、全プロファイルの SNR） |

`BlockData` は浮動小数点の参照実装と同じ形で、フレーム化・変調以降はそのまま使える。

## 4. 評価（通信路なし、元の音源との比較）

6 素材（piano、percussion、guitar、ambient、trailer、home）10 秒の平均。入力は 24 bit 整数に丸めた元の音源で、ViSQOL と波形 SNR は元の音源に対して測った。

| プロファイル | ViSQOL | 波形 SNR dB |
|---|---:|---:|
| B200M | 4.362 | 53.9 |
| B200MY | 4.367 | 54.5 |
| B200 | 4.417 | 52.5 |
| B200Y | 4.453 | 54.3 |
| M700M | 4.356 | 56.6 |
| M700MY | 4.423 | 57.2 |
| M700 | 3.727 | 50.9 |
| M700Y | 4.464 | 57.0 |

## 5. 未実装

- 12 bit IQ を入力とする受信側（ADC の量子化、AGC、等化器、LLR、ビタビ、融合、LPC 補間）。
- エンコーダの誤差の二乗和（アッテネータと指数の選択に使う）は、64 bit 整数で計算している。アキュムレータ（48 bit）に収まる幅への見直しが必要である。
