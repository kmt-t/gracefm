# 固定小数点実装（DSP 依存）

`gracefm/` は整数だけで動く。ハードウェアに載せるための参照実装で、**この文書の幅と演算は、想定する DSP（Zynq-7010 の DSP48E1）に依存する**。ハードウェアが変わるときは、DSP に依存する演算を集めた [`gracefm/dsp.py`](../gracefm/dsp.py) の幅と関数を差し替える。

**float は使わない。** `gracefm/` のモジュールには、float のリテラル、float 型、真の除算、浮動小数点の関数を書かない。`tests/test_fixed.py` が検査する。例外は、アナログの通信路を模擬する [`gracefm/channel.py`](../gracefm/channel.py) と、評価の道具 `tools/` で、ハードウェアではない。定数表（フィルタ係数、確率のテーブルなど）は、設計時に [`tools/gen/gen_tables.py`](../tools/gen/gen_tables.py) が浮動小数点で計算して整数にし、[`gracefm/tables.py`](../gracefm/tables.py) に書き出す（ハードウェアでは ROM になる）。

## 1. 想定ハードウェアと制約

| 項目 | 値 | 出典 |
|---|---|---|
| DSP スライス | DSP48E1。Zynq-7010 に 80 スライス | [UG953](https://docs.amd.com/r/2021.1-English/ug953-vivado-7series-libraries/DSP48E1)、[UG479 の写し](https://gitea.federationhq.de/csander/Dissertation/raw/branch/main/bibliography/documents/ug479_7Series_DSP48E1.pdf) |
| 乗算器 | 25 bit × 18 bit の符号つき（A ポート下位 25 bit、B ポート 18 bit） | 同上 |
| プリアダー | 25 bit | 同上 |
| アキュムレータ | 48 bit | 同上 |
| ADC/DAC | I・Q とも 12 bit（AD9363） | [AD9363 データシート](https://www.analog.com:443/media/en/technical-documentation/data-sheets/AD9363.pdf) |

`gracefm/dsp.py` はこの値を `MULT_BITS = 25`、`CONST_BITS = 18`、`ACC_BITS = 48` として持ち、演算（`mac_sq2_inv`、`round_shift`、`shift_signed`、`saturate`、`sq_err_sum` など）はこの幅を前提にする。

## 2. 数値形式

**方針。** 値は 0〜1 の範囲で、固定小数点のフルレンジは 20 bit 強（[SPEC](SPEC.md) 6.1）なので、中間精度を含めて **24 bit 固定小数点**で扱う。IQ は受け取った段階（12 bit の ADC 出力）で 24 bit に変換する。**DSP の都合で精度が下がることは容認する**。64 bit 整数が出るのは、乗算とアキュムレータ（`gracefm/dsp.py`）だけを想定する。

| 量 | 形式 |
|---|---|
| PCM | 符号つき 24 bit 整数（±1 = 2^23） |
| Haar の係数 | 小数 22 bit の整数（±1 = 2^22）。M = (L+R)/2、S = (L−R)/2 を、PCM から最後の 2 bit を四捨五入して作る |
| 1/√2 | 46341 / 65536（17 bit の正の整数。18 bit 符号つきの乗数に収まる） |
| 共有指数 | s = e + 22（係数の整数単位での 2 のべき乗の刻み）。指数範囲は整数の式 `(lev >> 1) + 3 - b` |
| シンボル（IQ） | 小数 22 bit の整数（±1 = 2^22）、配列の形は (n, 2)。ADC の 12 bit は左へ 12 bit シフトして変換 |
| LLR | 符号つき 8 bit の整数（小数 2 bit、±31.75）。正 = 0 らしい |
| ビタビの経路メトリック | 符号つき 14 bit。毎ステップで最大値を引いて正規化し、範囲に飽和させる |
| 確率 | Q15 の整数。LLR から 255 エントリのテーブルで引く |
| 誤差分散 | 対数領域の整数（log2 × 2^8）。融合の重みは 2^(−d/16) の 16 エントリのテーブルで作る |
| フィルタ係数 | 符号つき 18 bit（Q14〜Q17） |

- **精度を落として幅に収める**: Haar 4 段の最低域は、満点の直流で ±2^24 に達し、乗算器の入力（符号つき 25 bit）の上限 2^24 − 1 を 1 だけ超える。この 1 LSB（2^-22）は `saturate` で切る。
- **Haar の演算**: (e ± o)/√2 を、e·C ± o·C をアキュムレータで足し合わせ、四捨五入して 16 bit 右シフトする形で書く。
- **刻みの下限**: アッテネータの半刻みを整数にするため、共有指数の刻みは s ≥ 1 に制限する。デコーダは s ≤ 0 の値が来ても、右シフトで復号する。
- **誤差の二乗和**: エンコーダは、指数とアッテネータの選択で量子化誤差の二乗和を比べる。誤差は 25 bit あるので、量子化刻みに対する相対精度を 8 bit に切り詰めて（`ERR_FRAC_BITS`）18 bit に収めてから二乗する。
- **距離の二乗**: 復調の距離は右シフトして 17 bit にしてから二乗する。

## 3. モジュール

| モジュール | 内容 |
|---|---|
| [`dsp.py`](../gracefm/dsp.py) | DSP に依存する演算（乗算、累積、シフト、飽和、誤差の二乗和） |
| [`codec.py`](../gracefm/codec.py) | M/S、Haar、ブロック浮動小数点の量子化・逆量子化 |
| [`fec.py`](../gracefm/fec.py) | 畳み込み符号、系統符号、CRC、整数ビタビ（乗算なし） |
| [`modem.py`](../gracefm/modem.py) | 変調、軸ごとの max-log LLR、Y 方式の変調・復調、PRBS |
| [`layout.py`](../gracefm/layout.py)、[`framing.py`](../gracefm/framing.py) | ビット配置、送信（pack）と受信（unpack） |
| [`txrx.py`](../gracefm/txrx.py) | 送信機、受信機（確率による仮数の期待値、誤差分散）、2 系統の受信 |
| [`fusion.py`](../gracefm/fusion.py) | 2 系統の帯域ごとの融合（逆分散重み、Q15） |
| [`plc.py`](../gracefm/plc.py) | LPC による補間（整数のレビンソン・ダービン）とクロスフェード |
| [`postfilter.py`](../gracefm/postfilter.py) | 出力段（Lanczos 補間、LPF、再標本化）。係数は整数の表 |
| [`equalizer.py`](../gracefm/equalizer.py)、[`linalg.py`](../gracefm/linalg.py) | 訓練つき MMSE 等化器。通信路の推定と重みの設計を、整数のコレスキー分解で解く |
| [`tables.py`](../gracefm/tables.py) | 定数表（`tools/gen/gen_tables.py` が作る） |
| [`profiles.py`](../gracefm/profiles.py)、[`timing.py`](../gracefm/timing.py) | 設定値（整数と分数）、遅延モデル（分数） |

### 3.1 整数ビタビ

- 軟値は符号つき 8 bit の整数 LLR。枝メトリックは、期待される符号（±1）と 2 つの軟値の和・差だけで作る。**乗算を使わず**、加算・比較・選択だけなので、DSP48E1 の乗算器は要らない。

### 3.2 変調・復調

- 信号点は小数 22 bit の整数。平均エネルギーの正規化は整数の平方根（`isqrt`）で行い、定数は起動時に整数だけで作る。α は整数（5 または 1）。
- LLR は軸ごとに独立な max-log で作る: LLR = (D1 − D0) / (2σ²)。D は、そのビットが 1 / 0 の信号点のうち最も近いものとの距離の二乗。σ²（軸あたりの雑音分散）は、受信点と最寄りの信号点の差の二乗平均から、フレームごとに求める。I と Q の相関は見ない。
- Y 方式の半径は、象限の軸への射影から段を 1/2 刻み（段 6 bit + 小数 1 bit = 7 bit）で推定する。最上位 bit の位相 1 bit と合わせて、Y の仮数は 8 bit である。

### 3.3 等化器

- 通信路は、フレーム先頭の既知のシンボルを使った最小二乗法で推定する。正規方程式（15 タップ）を整数のコレスキー分解で解く。MMSE の重みは、通信路のタップから 11 タップの連立方程式を同じソルバで解いて作り、先読み量（0〜4）は予測誤差が最小のものを選ぶ。FIR は重みを Q14 に縮めて畳み込む。
- 通信路のモデル（RRC の応答、エコー）は評価の道具 [`tools/sim/multipath.py`](../tools/sim/multipath.py) にある。RRC の整合フィルタはまだ実装がなく、シンボル時刻の理想同期を前提にする。

## 4. 検査

| ファイル | 内容 |
|---|---|
| [`tests/test_fixed.py`](../tests/test_fixed.py) | 乗数の幅、Haar が 25 bit に収まること、全プロファイルの SNR、**`gracefm/` に float が無いこと** |
| [`tests/test_fec.py`](../tests/test_fec.py) | 整数ビタビ |
| [`tests/test_gracefm.py`](../tests/test_gracefm.py)、`test_profiles.py`、`test_y.py`、`test_equalizer.py`、`test_baselayer.py` | フレーム、リンク、融合、補間、Y、等化器 |

## 5. 未実装

- 同期（シンボルタイミング、搬送波、AGC）、RRC 整合フィルタ、AD9363 とのインターフェース。
- 暗号化（AES-128-CTR）は、ライブラリの AES が作るキーストリームとの排他的論理和で、`gracefm/crypto.py` にある。AES 自体の回路は設計していない。
