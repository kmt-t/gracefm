#!/usr/bin/env python3
"""
現行カタログの階層プロファイルについて、基本層配分を gracefm.layers で再計算して現行値と比べる。

  python tools/report/design_layers.py
"""
import sys
from dataclasses import replace
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from gracefm.framing import HybridLayout, Layout
from gracefm.layers import solve
from gracefm.profiles import PROFILES


def main():
    for p in PROFILES.values():
        if not p.layered:
            continue
        base_m, base_s = solve(p)
        q = replace(p, base_m=base_m, base_s=base_s)
        lay = (HybridLayout if q.hybrid else Layout)(q)
        strong = lay.n_coded + lay.n_base_bits
        weak = lay.n_coef_bits - lay.n_base_bits
        print(f"{p.name:8s} base_m={base_m} base_s={base_s}  強い{strong} 弱い{weak} 差{strong - weak:+d}"
              f"  {'(現行と一致)' if (base_m, base_s) == (p.base_m, p.base_s) else '(現行と異なる)'}")


if __name__ == "__main__":
    main()
