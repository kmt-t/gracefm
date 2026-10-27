#!/usr/bin/env python3
"""試聴音声を作り直し、検証して索引を書く (make_samples.py → sample_catalog.py)。"""
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]


def run(name):
    env = dict(os.environ, OPENBLAS_NUM_THREADS='1', OMP_NUM_THREADS='1')
    subprocess.run([sys.executable, '-u', str(ROOT / 'tools' / 'samples' / name)], cwd=ROOT, env=env, check=True)


if __name__ == '__main__':
    run('make_samples.py')
    run('sample_catalog.py')
