#!/usr/bin/env python3
"""試聴音声を作り直し、検証して索引を書く (make_samples.py → sample_catalog.py)。

原音は先に python tools/eval/fetch_lossless_benchmark_audio.py で eval_audio/lossless/ へ取得する。
評価値 (docs/results/) は作り直さない。作り直すのは samples/ の FLAC、index.json、README.md だけ。
"""
import argparse
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def run(name, *args):
    env = dict(os.environ, OPENBLAS_NUM_THREADS='1', OMP_NUM_THREADS='1')
    subprocess.run([sys.executable, '-u', str(ROOT / 'tools' / 'samples' / name), *args], cwd=ROOT, env=env, check=True)


if __name__ == '__main__':
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--workers', type=int, default=6)
    args = ap.parse_args()
    run('make_samples.py', '--workers', str(args.workers))
    run('sample_catalog.py')
